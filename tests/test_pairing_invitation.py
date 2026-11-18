import json
import unittest
from unittest.mock import Mock
from uuid import uuid4

from cahpp_app.horizon.mobile_enrollment import pairing_invitation


class PairingInvitationTest(unittest.TestCase):
    def test_qr_has_the_verified_scope_and_only_the_temporary_code(self):
        device_id = str(uuid4())
        relay = Mock(url="https://relais.example", instance_id=str(uuid4()),
                     workspace_id=str(uuid4()), token="cle-pc-de-test")
        relay.call.return_value = {"device_id": device_id, "name": "Élodie", "code": "x" * 43}
        _, _, _, payload = pairing_invitation(relay, "profil-1", "Élodie", "Téléphone")
        relay.call.assert_called_once_with("pairing", {
            "pc_user_id": "profil-1", "name": "Élodie", "label": "Téléphone",
        })
        self.assertEqual(json.loads(payload), {
            "horizon_pairing": 1, "device_id": device_id, "code": "x" * 43, "name": "Élodie",
            "url": relay.url, "instance_id": relay.instance_id, "workspace_id": relay.workspace_id,
        })
        self.assertTrue(payload.isascii())
        self.assertNotIn(relay.token, payload)
