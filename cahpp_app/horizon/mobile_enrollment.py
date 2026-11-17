"""Clé d’appareil générée sur le PC, empreinte seule conservée au relais."""

import secrets
from uuid import uuid4


def enroll_device(relay, name, device_label, *, device_id=None, token=None):
    key = device_id or str(uuid4())
    secret = token or secrets.token_urlsafe(36)
    result = relay.call("devices/" + key, {"name": name, "label": device_label, "token": secret})
    return result | {"token": secret}

