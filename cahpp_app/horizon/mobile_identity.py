"""Identité déclarée du téléphone ; l’autorisation reste portée par la clé d’établissement."""
from uuid import UUID


def mobile_actor(database, body):
    actor = body.get("actor")
    if actor is None:
        return database.using_actor("mobile-legacy", "Utilisateur mobile (ancien client)")
    if not isinstance(actor, dict):
        raise ValueError("Identité mobile invalide.")
    try:
        identifier = str(UUID(str(actor["id"])))
        name = actor["name"]
        if identifier != actor["id"] or not isinstance(name, str) or not 1 <= len(name.strip()) <= 150 or any(
                ord(c) < 32 for c in name):
            raise ValueError("Identité mobile invalide.")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Identité mobile invalide.") from exc
    return database.using_actor("mobile-" + identifier, name.strip())
