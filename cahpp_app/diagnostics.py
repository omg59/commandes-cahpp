from __future__ import annotations

import platform
import sys
import sqlite3
import struct
from datetime import datetime

from .collaboration import CollaborationManager
from .database import Database
from .app_logging import logging_snapshot


def _size(value: object) -> str:
    size = float(value or 0)
    units = ("o", "Kio", "Mio", "Gio")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} Gio"


def _yes_no(value: object) -> str:
    return "OK" if bool(value) else "ÉCHEC"


def build_diagnostic_report(
    database: Database,
    collaboration: CollaborationManager | None,
    version: str,
    last_sync_result: dict[str, object] | None = None,
    last_sync_error: str = "",
    gui_runtime: str | None = None,
) -> str:
    if gui_runtime is None:
        gui_runtime = "Interface : non renseignée (diagnostic du moteur)"
    generated_at = datetime.now().isoformat(timespec="seconds")
    lines = [
        "COMMANDES CAHPP — RAPPORT DE DIAGNOSTIC",
        "=" * 43,
        f"Généré le : {generated_at}",
        f"Version : {version}",
        f"Système : {platform.system()} {platform.release()} ({platform.machine()})",
        f"Python : {platform.python_version()}",
        f"Architecture du processus : {struct.calcsize('P') * 8} bits",
        f"SQLite : {sqlite3.sqlite_version}",
        gui_runtime,
        f"Exécutable compilé : {'oui' if getattr(sys, 'frozen', False) else 'non'}",
        f"Utilisateur : {database.current_user_name}",
        "",
        "BASE LOCALE",
        "-----------",
    ]

    try:
        local = database.diagnostic_snapshot()
    except Exception as exc:
        lines.extend(
            [
                "État : ÉCHEC",
                f"Erreur : {type(exc).__name__}: {exc}",
            ]
        )
        local = {}
    else:
        counts = dict(local.get("counts") or {})
        anomalies = dict(local.get("anomalies") or {})
        search_index = dict(local.get("search_index") or {})
        quick_check = list(local.get("quick_check") or [])
        integrity_ok = quick_check == ["ok"]
        lines.extend(
            [
                f"Chemin : {local.get('path', '')}",
                f"Taille : {_size(local.get('size_bytes'))}",
                f"Journal WAL : {_size(local.get('wal_size_bytes'))}",
                f"Schéma : {local.get('schema_version', '')}",
                f"Mode SQLite : {local.get('journal_mode', '')}",
                f"Recherche plein texte : {_yes_no(local.get('fts_available'))}",
                "Index de recherche : "
                + ("OK" if search_index.get("consistent") else "À RÉPARER"),
                "Articles indexés : "
                f"{search_index.get('indexed', 0)} / "
                f"{search_index.get('products', 0)}",
                "Entrées manquantes/orphelines : "
                f"{search_index.get('missing', 0)} / "
                f"{search_index.get('orphaned', 0)}",
                f"Contenus d'index différents : {search_index.get('mismatched', 0)}",
                f"Test de recherche avec classement : {_yes_no(search_index.get('functional'))}",
                f"Contrôle d'intégrité : {_yes_no(integrity_ok)}",
                f"Articles : {counts.get('products', 0)} "
                f"({counts.get('active_products', 0)} actifs)",
                f"Fournisseurs : {counts.get('suppliers', 0)}",
                f"Commandes : {counts.get('orders', 0)}",
                f"Commandes supprimées mémorisées : {counts.get('deleted_drafts', 0)}",
                f"Commandes archivées : {counts.get('archived_orders', 0)}",
                f"Livraisons en attente : {counts.get('pending_deliveries', 0)}",
                f"Commandes à synchroniser : {counts.get('pending_orders', 0)}",
                f"Publication locale du catalogue en attente : {_yes_no(local.get('catalog_publication_pending'))}",
                "Révisions locales / bases communes en attente : " + ", ".join(f"{r['local_revision']}/{r['base_revision']}" for r in local.get('pending_revision_bases', [])),
                f"Documents liés : {counts.get('attachments', 0)}",
                f"Réceptions enregistrées : {counts.get('receipts', 0)}",
                f"Notes internes : {counts.get('internal_comments', 0)}",
                f"Imports CAHPP : {counts.get('imports', 0)}",
                f"Dernier mois de catalogue confirmé : {local.get('catalog_effective_period') or 'base complète de période non précisée'}",
                f"Articles actifs à vérifier : {counts.get('catalog_reviews', 0)}",
                "Anomalies : "
                + (
                    "aucune"
                    if not any(int(value or 0) for value in anomalies.values())
                    else ", ".join(
                        f"{key}={value}"
                        for key, value in anomalies.items()
                        if int(value or 0)
                    )
                ),
            ]
        )

        if search_index.get("error"):
            lines.append(f"Détail de l'index : {search_index['error']}")
        repair = dict(local.get("last_search_repair") or {})
        lines.extend(
            [
                "",
                "DERNIÈRE RECONSTRUCTION DE L'INDEX",
                "---------------------------------",
            ]
        )
        if repair:
            lines.extend(
                [
                    f"Début : {repair.get('started_at', '')}",
                    f"Fin : {repair.get('finished_at', 'en cours')}",
                    f"Déclenchement : {repair.get('origin', '')}",
                    f"Résultat : {_yes_no(repair.get('success'))}",
                    f"Durée : {repair.get('elapsed_ms', 0)} ms",
                    f"Détail : {repair.get('detail', '')}",
                ]
            )
            if repair.get("success"):
                lines.append(
                    f"Articles reconstruits : {repair.get('indexed', 0)} / {repair.get('products', 0)}"
                )
        else:
            lines.append("Aucune reconstruction depuis ce lancement.")

    preparation = dict(local.get("search_plan_preparation") or {})
    lines.extend(["", "PERFORMANCES DE RECHERCHE", "------------------------"])
    if preparation:
        lines.extend(
            [
                f"Statistiques du planificateur : {_yes_no(preparation.get('success'))}",
                f"Actualisation : {preparation.get('checked_at', '')}",
                f"Durée d'actualisation : {preparation.get('elapsed_ms', 0)} ms",
            ]
        )
        if not preparation.get("success"):
            lines.append(
                f"Erreur : {preparation.get('error_type', '')} / {preparation.get('sqlite_code', '')}"
            )
    else:
        lines.append(
            "Statistiques non recalculées depuis ce lancement (prévu à la première recherche)."
        )
    lines.append("Plan de recherche témoin (sans saisie utilisateur) :")
    lines.extend(f"  {step}" for step in local.get("catalog_search_plan", []))

    lines.extend(["", "COLLABORATION", "-------------"])
    if collaboration is None:
        lines.append("Mode collaboratif : désactivé ou indisponible")
    else:
        try:
            shared = collaboration.diagnostic_snapshot()
        except Exception as exc:
            lines.extend(
                [
                    "Accès au partage : ÉCHEC",
                    f"Erreur : {type(exc).__name__}: {exc}",
                ]
            )
        else:
            integrity = shared.get("catalog_integrity")
            catalog_status = "non publié" if integrity is None else _yes_no(integrity)
            lines.extend(
                [
                    f"Dossier : {shared.get('path', '')}",
                    f"Lecture : {_yes_no(shared.get('readable'))}",
                    f"Écriture : {_yes_no(shared.get('writable'))}",
                    f"Renommage atomique : {_yes_no(shared.get('atomic_rename'))}",
                    f"Identifiant : {shared.get('workspace_id', '')}",
                    "Identifiant cohérent : "
                    f"{_yes_no(shared.get('workspace_matches'))}",
                    f"Commandes partagées : {shared.get('shared_orders', 0)}",
                    f"Révision équipe : {shared.get('team_revision', 0)}",
                    "Catalogue partagé : "
                    f"{shared.get('catalog_version') or 'non publié'}",
                    f"Intégrité du catalogue : {catalog_status}",
                    f"Verrous actifs : {shared.get('active_locks', 0)}",
                    f"Verrous expirés : {shared.get('expired_locks', 0)}",
                    "Utilisateurs actifs : "
                    + (", ".join(shared.get("lock_owners") or []) or "aucun"),
                ]
            )

    lines.extend(["", "DERNIÈRE SYNCHRONISATION", "-----------------------"])
    if last_sync_result:
        orders = dict(last_sync_result.get("orders") or {})
        lines.extend(
            [
                f"Date : {last_sync_result.get('synced_at', '')}",
                f"Commandes reçues : {orders.get('imported', 0)}",
                f"Commandes envoyées : {orders.get('published', 0)}",
                f"Conflits/verrous : {orders.get('conflicts', 0)}",
                "Verrous expirés nettoyés : "
                f"{last_sync_result.get('cleaned_locks', 0)}",
                "Catalogue en attente : "
                + ("oui" if last_sync_result.get("catalog_pending") else "non"),
            ]
        )
    else:
        lines.append("Aucun compte rendu disponible depuis ce lancement.")
    if last_sync_error:
        lines.append(f"Dernière erreur : {last_sync_error}")

    journal = logging_snapshot()
    lines.extend(
        [
            "",
            "JOURNAL TECHNIQUE",
            "-----------------",
            f"Fichier : {journal['path'] or 'non initialisé'}",
            f"État : {journal['error'] or 'OK'}",
            "Événements récents (sans recherche saisie ni données de commande) :",
            *(line.rstrip() for line in journal["recent"]),
        ]
    )
    lines.extend(
        [
            "",
            "Ce rapport ne contient ni ligne de commande, ni tarif, "
            "ni contenu de document.",
            "",
        ]
    )
    return "\n".join(lines)
