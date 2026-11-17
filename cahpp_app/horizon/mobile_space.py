"""Identité de l'espace collaboratif exposé par le relais mobile."""

from uuid import UUID


class WorkspaceBindingRequired(ValueError):
    def __init__(self, counts):
        self.counts = counts
        super().__init__(
            "Le relais contient des données antérieures à l’isolation des espaces. "
            "Vérifiez leur origine puis utilisez « Rattacher le relais à cette base… » "
            "dans les paramètres Android. Aucune opération n’a été envoyée."
        )


def checked_identity(identity):
    if not isinstance(identity, dict) or identity.get("protocol") != 4:
        raise ValueError("Mettez à jour Horizon Server avant de synchroniser cette version.")
    try:
        instance = str(UUID(identity["instance_id"]))
        workspace = str(UUID(identity["workspace_id"])) if identity.get("workspace_id") else ""
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("L’identité renvoyée par le relais est invalide.") from exc
    return instance, workspace


def connect_workspace(relay, workspace_id, *, adopt_existing=False):
    expected = str(UUID(workspace_id))
    identity = relay.call("identity")
    instance, actual = checked_identity(identity)
    if actual and actual != expected:
        raise ValueError(
            "Ce relais appartient à une autre base. Aucune commande ni réception "
            "n’a été transférée. Choisissez le relais correspondant à ce partage."
        )
    if not actual:
        counts = identity.get("legacy_counts", {})
        if any(counts.values()) and not adopt_existing:
            raise WorkspaceBindingRequired(counts)
        identity = relay.call("identity", {
            "instance_id": instance, "workspace_id": expected,
            "adopt_existing": adopt_existing,
        })
        instance, actual = checked_identity(identity)
    if actual != expected:
        raise ValueError("Le relais n’a pas confirmé l’identité de cette base.")
    relay.instance_id, relay.workspace_id = instance, actual
    return identity
