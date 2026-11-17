"""Clé PC : coffre natif ou mémoire de la session, jamais un fichier en clair."""

import hashlib
import logging
import os
from pathlib import Path

from ..app_logging import log_failure

logger = logging.getLogger(__name__)
SERVICE = "Horizon/relay-pc"


def native_backend():
    # Imports explicites pour le packaging. Ni backend tiers configurable,
    # ni chainer pouvant choisir un stockage fichier non chiffré.
    candidates = []
    if os.name == "nt":
        from keyring.backends.Windows import WinVaultKeyring

        candidates.append(WinVaultKeyring)
    else:
        from keyring.backends.SecretService import Keyring
        from keyring.backends.kwallet import DBusKeyring

        candidates.extend((Keyring, DBusKeyring))
    for candidate in candidates:
        try:
            if candidate.priority > 0:
                return candidate()
        except Exception as exc:
            log_failure(logger, "coffre_indisponible", exc)
    return None


class Credentials:
    def __init__(self, profile, settings):
        self.profile = Path(profile).resolve()
        self.settings = settings
        self.token = ""
        self.remembered = False
        self.warning = ""
        self.owned_accounts = set()
        try:
            self.backend = native_backend()
        except Exception as exc:
            log_failure(logger, "coffre_initialisation_echec", exc)
            self.backend = None

    def account(self, url):
        value = str(self.profile) + "\n" + url.strip().rstrip("/")
        return hashlib.sha256(value.encode()).hexdigest()

    def sync(self):
        self.settings.sync()
        status = self.settings.status()
        if getattr(status, "value", status) != 0:
            raise ValueError("Impossible de mettre à jour les paramètres locaux de connexion.")

    def load(self, *, fallback=""):
        legacy = self.settings.value("mobile/token", "", type=str)
        if legacy:
            # Vérifier le coffre avant de supprimer le texte historique. En cas
            # d'indisponibilité, conserver uniquement la copie de cette session.
            self.store(legacy, self.settings.value("mobile/url", "", type=str), remember=True)
            self.warning = (self.warning or "L’ancienne clé a été déplacée dans le coffre système.")
            return self.token
        account = self.settings.value("mobile/credential_id", "", type=str)
        if account and account != self.account(self.settings.value("mobile/url", "", type=str)):
            self.settings.remove("mobile/credential_id")
            self.sync()
            self.warning = "Profil déplacé ou copié : saisissez à nouveau la clé pour ce profil."
            account = ""
        if account:
            self.owned_accounts.add(account)
        if account and self.backend:
            try:
                self.token = self.backend.get_password(SERVICE, account) or ""
                self.remembered = bool(self.token)
            except Exception as exc:
                log_failure(logger, "coffre_lecture_echec", exc)
                self.warning = "Le coffre système est inaccessible. Saisissez la clé pour cette session."
        elif account:
            self.warning = "Le coffre système est indisponible. Saisissez la clé pour cette session."
        self.token = self.token or fallback
        return self.token

    def _forget(self, account):
        if not account or not self.backend:
            return
        try:
            if self.backend.get_password(SERVICE, account) is not None:
                self.backend.delete_password(SERVICE, account)
        except Exception as exc:
            log_failure(logger, "coffre_effacement_echec", exc)
            self.warning = "Horizon n’utilisera plus l’ancienne entrée. Son effacement dans le coffre n’a pas pu être confirmé."

    def store(self, token, url, *, remember):
        self.token, self.remembered, self.warning = token, False, ""
        previous = self.settings.value("mobile/credential_id", "", type=str)
        account = self.account(url)
        self.owned_accounts.add(account)
        if remember and self.backend:
            try:
                self.backend.set_password(SERVICE, account, token)
                if self.backend.get_password(SERVICE, account) != token:
                    raise RuntimeError("Vérification du coffre impossible")
                self.settings.setValue("mobile/credential_id", account)
                self.remembered = True
            except Exception as exc:
                log_failure(logger, "coffre_ecriture_echec", exc)
                self.warning = "Mémorisation non confirmée. La clé reste utilisable dans cette session ; aucun fichier en clair n’est créé."
        elif remember:
            self.warning = "Coffre système indisponible : la clé reste uniquement en mémoire pour cette session."
        if not self.remembered:
            self.settings.remove("mobile/credential_id")
            self._forget(account)
        if previous in self.owned_accounts and (previous != account or not self.remembered):
            self._forget(previous)
        self.settings.remove("mobile/token")
        self.sync()
        return self.remembered

    def diagnostic(self):
        return {
            "backend": type(self.backend).__module__ + "." + type(self.backend).__name__ if self.backend else "session",
            "remembered": self.remembered,
        }
