"""Le coffre natif est un service externe ; aucun repli fichier n'est permis."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cahpp_app.horizon.credentials import Credentials, SERVICE


class Settings:
    def __init__(self, **values):
        self.values = values

    def value(self, key, default=None, **kwargs):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def remove(self, key):
        self.values.pop(key, None)

    def sync(self):
        pass

    def status(self):
        return 0


class Vault:
    def __init__(self):
        self.values = {}

    def get_password(self, service, account):
        return self.values.get((service, account))

    def set_password(self, service, account, token):
        self.values[service, account] = token

    def delete_password(self, service, account):
        self.values.pop((service, account), None)


class CredentialsTest(unittest.TestCase):
    def setUp(self):
        self.vault = Vault()
        self.settings = Settings(**{"mobile/url": "https://relay.test"})
        self.patch = patch("cahpp_app.horizon.credentials.native_backend", return_value=self.vault)
        self.mock_backend = self.patch.start()
        self.addCleanup(self.patch.stop)
        self.profile = Path(tempfile.gettempdir()) / "horizon-credentials-test"

    def credentials(self, settings=None, profile=None):
        return Credentials(profile or self.profile, settings or self.settings)

    def test_only_an_opaque_reference_is_persisted_and_secret_can_be_reloaded(self):
        first = self.credentials()
        self.assertTrue(first.store("secret-test", "https://relay.test", remember=True))
        self.assertNotIn("secret-test", str(self.settings.values))
        self.assertNotIn("secret-test", str(first.diagnostic()))
        self.assertEqual(self.credentials().load(), "secret-test")

    def test_legacy_plaintext_migrates_only_after_a_verified_secure_write(self):
        self.settings.setValue("mobile/token", "legacy-secret")
        first = self.credentials()
        self.assertEqual(first.load(), "legacy-secret")
        self.assertNotIn("mobile/token", self.settings.values)
        self.assertTrue(first.remembered)
        self.assertEqual(self.credentials().load(), "legacy-secret")

    def test_unavailable_vault_migrates_legacy_to_session_without_another_plaintext_copy(self):
        self.mock_backend.return_value = None
        self.settings.setValue("mobile/token", "legacy-secret")
        first = self.credentials()
        self.assertEqual(first.load(), "legacy-secret")
        self.assertNotIn("mobile/token", self.settings.values)
        self.assertNotIn("mobile/credential_id", self.settings.values)
        self.assertFalse(first.remembered)
        self.assertIn("session", first.warning)
        self.assertEqual(self.credentials().load(), "")

    def test_a_failed_or_unverified_write_never_claims_the_secret_was_remembered(self):
        for method in ("set_password", "get_password"):
            with self.subTest(method=method), patch.object(self.vault, method, side_effect=RuntimeError("secret-test")):
                first = self.credentials()
                self.assertFalse(first.store("secret-test", "https://relay.test", remember=True))
                self.assertNotIn("secret-test", str(self.settings.values))
                self.assertEqual(first.token, "secret-test")
                self.assertNotIn("secret-test", first.warning)

    def test_forgetting_removes_reference_and_native_secret(self):
        first = self.credentials()
        first.store("secret-test", "https://relay.test", remember=True)
        first.store("secret-test", "https://relay.test", remember=False)
        self.assertEqual(first.token, "secret-test")
        self.assertEqual(self.vault.values, {})
        self.assertNotIn("mobile/credential_id", self.settings.values)

    def test_copied_profile_never_reads_or_deletes_the_original_vault_entry(self):
        first = self.credentials()
        first.store("original-secret", "https://relay.test", remember=True)
        copied_settings = Settings(**self.settings.values)
        copied = self.credentials(copied_settings, self.profile / "copy")
        self.assertEqual(copied.load(), "")
        copied.store("copy-secret", "https://relay.test", remember=True)
        self.assertEqual(self.vault.get_password(SERVICE, first.account("https://relay.test")), "original-secret")

    def test_changing_relay_does_not_reuse_the_other_relays_key(self):
        first = self.credentials()
        first.store("old-secret", "https://relay.test", remember=True)
        first.store("new-secret", "https://other.test", remember=True)
        self.settings.setValue("mobile/url", "https://other.test")
        self.assertEqual(self.credentials().load(), "new-secret")
        self.assertIsNone(self.vault.get_password(SERVICE, first.account("https://relay.test")))

    def test_existing_secure_entry_survives_a_temporarily_unavailable_vault(self):
        first = self.credentials()
        first.store("secret-test", "https://relay.test", remember=True)
        self.mock_backend.return_value = None
        offline = self.credentials()
        self.assertEqual(offline.load(), "")
        self.assertIn("mobile/credential_id", self.settings.values)
        self.mock_backend.return_value = self.vault
        self.assertEqual(self.credentials().load(), "secret-test")

    def test_settings_write_failure_is_reported(self):
        with patch.object(self.settings, "status", return_value=1):
            with self.assertRaisesRegex(ValueError, "paramètres"):
                self.credentials().store("secret-test", "https://relay.test", remember=True)
