"""Application atomique des catalogues complets, évolutions et instantanés."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from ..database import CATALOG_REVIEW_SQL

from .formats import (
    CATALOG_FIELDS,
    KNOWN_UPDATE_TYPES,
    NUMERIC_FIELDS,
    TEXT_FIELDS,
    CatalogImportError,
    CatalogWorkbook,
    ImportOptions,
    ImportPreview,
    ImportResult,
    sha256,
    period_value,
)


def _settings(connection):
    return {
        row["key"]: row["value"]
        for row in connection.execute("SELECT key, value FROM settings")
    }


def _save_settings(connection, values):
    connection.executemany(
        "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        values.items(),
    )


def _previous_result(row):
    return ImportResult(
        import_id=row["id"],
        filename=row["filename"],
        row_count=row["row_count"],
        added_count=row["added_count"],
        updated_count=row["updated_count"],
        missing_count=row["missing_count"],
        already_imported=True,
        mode=row["mode"],
        period=row["period"],
        deactivated_count=row["deactivated_count"],
        review_count=row["review_count"],
        warnings=tuple(json.loads(row["warnings_json"])),
        file_hash=row["file_hash"],
        previous_catalog_hash=row["previous_catalog_hash"],
    )


def _policy(connection, mode, period, missing_count, *, source_hash=""):
    settings = _settings(connection)
    warnings, confirmations = [], []
    if mode == "delta":
        base = connection.execute(
            "SELECT 1 FROM imports WHERE mode IN ('full','snapshot') LIMIT 1"
        ).fetchone()
        products = connection.execute(
            "SELECT 1 FROM products WHERE source='CAHPP' LIMIT 1"
        ).fetchone()
        if not base or not products:
            raise CatalogImportError(
                "Une base CAHPP complète est nécessaire avant les évolutions mensuelles. Importez d'abord votre dernier catalogue complet."
            )
        latest = settings.get("catalog_effective_period", "")
        if not latest:
            confirmations.append("baseline")
            warnings.append(
                "Confirmez que la base complète inclut les évolutions jusqu'au mois précédant ce fichier. Sa période n'est pas connue du logiciel."
            )
        elif period < latest:
            raise CatalogImportError(
                f"Mise à jour {period} antérieure au catalogue {latest}. Aucun retour en arrière n'a été effectué."
            )
        elif period == latest:
            confirmations.append("revision")
            warnings.append(
                "Un fichier différent a déjà été appliqué pour ce mois. Confirmez qu'il s'agit d'une révision plus récente fournie par CAHPP."
            )
        else:
            year, month = map(int, latest.split("-"))
            following = f"{year + (month == 12):04d}-{month % 12 + 1:02d}"
            if period != following:
                raise CatalogImportError(
                    f"Mois manquant après {latest} : importez d'abord les évolutions de {following}, puis les suivantes dans l'ordre."
                )
        warnings.append(
            "Les articles absents sont conservés. Les conditionnements manquants ou modifiés devront être vérifiés avant commande."
        )
    elif mode == "snapshot":
        latest = settings.get("catalog_effective_period", "")
        if latest and (not period or period < latest):
            raise CatalogImportError(
                "Le catalogue partagé est plus ancien que les mises à jour locales. Synchronisez avec le poste qui possède la version la plus récente."
            )
        local = connection.execute(
            "SELECT mode,file_hash,previous_catalog_hash FROM imports ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if (
            local
            and local["mode"] == "delta"
            and local["file_hash"] != source_hash
            and local["previous_catalog_hash"]
            == settings.get("collaboration_catalog_hash", "")
        ):
            confirmations.append("snapshot_replacement")
            warnings.append(
                "Des évolutions locales n'ont pas été publiées. Ce catalogue partagé les remplacera ; conservez le fichier local pour le réappliquer ensuite si nécessaire."
            )
    elif mode == "full":
        if settings.get("catalog_effective_period"):
            confirmations.append("replacement")
            warnings.append(
                "Vérifiez que ce catalogue complet est plus récent que les évolutions déjà appliquées ("
                + settings["catalog_effective_period"]
                + "). Il remplacera les données CAHPP courantes."
            )
        active = connection.execute(
            "SELECT COUNT(*) FROM products WHERE source='CAHPP' AND active=1"
        ).fetchone()[0]
        if missing_count > max(20, active * 0.10):
            if "replacement" not in confirmations:
                confirmations.append("replacement")
            warnings.append(
                f"Ce catalogue complet retirerait {missing_count} articles actifs. Vérifiez qu'il contient bien la base complète et non un extrait."
            )
    return tuple(warnings), tuple(confirmations)


def _approve(confirmations, options):
    for name, approved in (
        ("baseline", options.confirm_baseline),
        ("revision", options.allow_revision),
        ("replacement", options.confirm_full_replacement),
        ("snapshot_replacement", options.confirm_snapshot_replacement),
    ):
        if name in confirmations and not approved:
            raise CatalogImportError(
                {
                    "baseline": "Confirmez d'abord la période de votre base complète avant cette première évolution mensuelle.",
                    "revision": "Confirmez explicitement la révision du même mois avant de remplacer ses valeurs.",
                    "replacement": "Le retrait massif d'articles nécessite une confirmation de catalogue complet.",
                    "snapshot_replacement": "Confirmez le remplacement des évolutions locales non publiées avant d'appliquer le catalogue partagé.",
                }[name]
            )


class CatalogImporter:
    def __init__(self, database):
        self.database = database

    def inspect_file(self, path: Path | str) -> ImportPreview:
        path = Path(path)
        digest = sha256(path)
        with self.database.connect() as connection:
            previous = connection.execute(
                "SELECT * FROM imports WHERE file_hash=?", (digest,)
            ).fetchone()
            if previous:
                return ImportPreview(
                    previous["mode"],
                    previous["filename"],
                    digest,
                    previous["row_count"],
                    previous["period"],
                    already_imported=True,
                )
            connection.execute("PRAGMA temp_store=FILE")
            connection.execute(
                "CREATE TEMP TABLE preview_codes(code TEXT PRIMARY KEY) WITHOUT ROWID"
            )
            periods = set()
            count = 0
            with CatalogWorkbook(path) as book:
                for number, row in book.rows():
                    try:
                        connection.execute(
                            "INSERT INTO preview_codes VALUES (?)", (row["code_cahpp"],)
                        )
                    except sqlite3.IntegrityError:
                        raise CatalogImportError(
                            f"Ligne {number} : code CAHPP dupliqué ({row['code_cahpp']}). Aucun import effectué."
                        ) from None
                    count += 1
                    if book.mode == "delta":
                        periods.add(row["period"])
                        if len(periods) > 1:
                            raise CatalogImportError(
                                "Le fichier contient plusieurs mois d'évolution. Fournissez un fichier par mois."
                            )
                if not count:
                    raise CatalogImportError(
                        "Le fichier ne contient aucun article. La base existante est conservée."
                    )
                period = (
                    next(iter(periods))
                    if periods
                    else book.metadata.get("effective_period", "")
                )
                if period:
                    period = period_value(period)
                missing = (
                    connection.execute(
                        "SELECT COUNT(*) FROM products p WHERE source='CAHPP' AND active=1 AND NOT EXISTS (SELECT 1 FROM preview_codes s WHERE s.code=p.code_cahpp)"
                    ).fetchone()[0]
                    if book.mode in {"full", "snapshot"}
                    else 0
                )
                warnings, confirmations = _policy(
                    connection,
                    book.mode,
                    period,
                    missing,
                    source_hash=book.metadata.get("source_sha256", ""),
                )
                result = ImportPreview(
                    book.mode,
                    book.metadata.get("source_name", path.name),
                    digest,
                    count,
                    period,
                    warnings,
                    confirmations,
                )
            if sha256(path) != digest:
                raise CatalogImportError(
                    "Le fichier a changé pendant sa lecture. Fermez-le dans Excel et recommencez."
                )
            return result

    def import_file(
        self,
        path: Path | str,
        progress=None,
        *,
        options: ImportOptions | None = None,
        preview: ImportPreview | None = None,
    ) -> ImportResult:
        path = Path(path)
        options = options or ImportOptions()
        progress = progress or (lambda current, total, message: None)
        progress(0, 100, "Vérification du format et du contenu…")
        preview = preview or self.inspect_file(path)
        if sha256(path) != preview.file_hash:
            raise CatalogImportError(
                "Le fichier a changé depuis sa confirmation. Relancez l'import."
            )
        with self.database.connect() as connection:
            previous = connection.execute(
                "SELECT * FROM imports WHERE file_hash=?", (preview.file_hash,)
            ).fetchone()
            if previous:
                return _previous_result(previous)
        _approve(preview.confirmations, options)
        self.database.prepare_catalog_statistics()
        connection = self.database.connect()
        try:
            connection.execute("PRAGMA temp_store=FILE")
            stage_fields = (*CATALOG_FIELDS, "active", "review_token", "review_reason")
            declarations = [
                f"{name} {'REAL' if name in NUMERIC_FIELDS else 'INTEGER' if name == 'active' else 'TEXT'}"
                for name in stage_fields
            ]
            connection.execute(
                "CREATE TEMP TABLE incoming ("
                + ",".join(declarations)
                + ", PRIMARY KEY(code_cahpp)) WITHOUT ROWID"
            )
            with CatalogWorkbook(path) as book:
                if book.mode != preview.mode:
                    raise CatalogImportError("Le format du fichier a changé.")
                provided = set(book.header)
                metadata = dict(book.metadata)
                batch = []
                for _, row in book.rows():
                    if book.mode == "delta" and row["period"] != preview.period:
                        raise CatalogImportError("La période du fichier a changé.")
                    batch.append(tuple(row.get(name) for name in stage_fields))
                    if len(batch) >= 1000:
                        connection.executemany(
                            "INSERT INTO incoming VALUES ("
                            + ",".join("?" for _ in stage_fields)
                            + ")",
                            batch,
                        )
                        batch.clear()
                if batch:
                    connection.executemany(
                        "INSERT INTO incoming VALUES ("
                        + ",".join("?" for _ in stage_fields)
                        + ")",
                        batch,
                    )
            if sha256(path) != preview.file_hash:
                raise CatalogImportError(
                    "Le fichier a changé pendant sa lecture. Aucun changement appliqué."
                )
            connection.commit()  # Seule la table temporaire a été remplie.
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT * FROM imports WHERE file_hash=?", (preview.file_hash,)
            ).fetchone()
            if previous:
                return _previous_result(previous)
            count = connection.execute("SELECT COUNT(*) FROM incoming").fetchone()[0]
            if not count:
                raise CatalogImportError("Catalogue vide refusé.")
            missing = (
                connection.execute(
                    "SELECT COUNT(*) FROM products p WHERE source='CAHPP' AND active=1 AND NOT EXISTS (SELECT 1 FROM incoming s WHERE s.code_cahpp=p.code_cahpp)"
                ).fetchone()[0]
                if preview.mode in {"full", "snapshot"}
                else 0
            )
            warnings, confirmations = _policy(
                connection,
                preview.mode,
                preview.period,
                missing,
                source_hash=metadata.get("source_sha256", ""),
            )
            _approve(confirmations, options)
            collision = connection.execute(
                "SELECT p.code_cahpp FROM products p JOIN incoming s ON s.code_cahpp=p.code_cahpp WHERE p.source<>'CAHPP' LIMIT 1"
            ).fetchone()
            if collision:
                raise CatalogImportError(
                    f"Le code {collision[0]} appartient à un article local. Conflit à résoudre avant import."
                )
            settings = _settings(connection)
            progress(60, 100, "Comparaison et application des évolutions…")
            self._suppliers(connection)
            now = datetime.now().isoformat(timespec="microseconds")
            import_id = connection.execute(
                "INSERT INTO imports(filename,file_hash,imported_at,row_count,mode,period,previous_catalog_hash) VALUES (?,?,?,?,?,?,?)",
                (
                    preview.filename,
                    preview.file_hash,
                    now,
                    count,
                    preview.mode,
                    preview.period,
                    settings.get("collaboration_catalog_hash", ""),
                ),
            ).lastrowid
            resolved = self._resolved(preview, provided)
            join = "FROM incoming s LEFT JOIN products p ON p.code_cahpp=s.code_cahpp"
            added = connection.execute(
                "SELECT COUNT(*) " + join + " WHERE p.id IS NULL"
            ).fetchone()[0]
            difference = " OR ".join(
                f"p.{key} IS NOT ({value})"
                for key, value in resolved.items()
                if key != "code_cahpp"
            )
            updated = connection.execute(
                "SELECT COUNT(*) "
                + join
                + " WHERE p.id IS NOT NULL AND ("
                + difference
                + ")"
            ).fetchone()[0]
            deactivated = (
                missing
                + connection.execute(
                    "SELECT COUNT(*) "
                    + join
                    + " WHERE p.active=1 AND ("
                    + resolved["active"]
                    + ")=0"
                ).fetchone()[0]
            )
            connection.execute(
                f"""INSERT INTO price_history(product_id,import_id,recorded_at,unit_price,conditionnement,qml)
                    SELECT p.id, ?, ?, {resolved["unit_price"]}, {resolved["conditionnement"]}, {resolved["qml"]}
                    {join} WHERE p.id IS NOT NULL AND
                    (p.unit_price IS NOT ({resolved["unit_price"]}) OR p.conditionnement IS NOT ({resolved["conditionnement"]}) OR p.qml IS NOT ({resolved["qml"]}))""",
                (import_id, now),
            )
            columns = list(resolved) + [
                "supplier_id",
                "source",
                "last_seen_import_id",
                "created_at",
                "updated_at",
            ]
            values = list(resolved.values()) + [
                "m.supplier_id",
                "'CAHPP'",
                "?",
                "?",
                "?",
            ]
            connection.execute(
                "INSERT INTO products("
                + ",".join(columns)
                + ") SELECT "
                + ",".join(values)
                + " "
                + join
                + " JOIN supplier_map m ON m.name=s.supplier_name WHERE 1 ON CONFLICT(code_cahpp) DO UPDATE SET "
                + ",".join(
                    f"{name}=excluded.{name}"
                    for name in columns
                    if name not in {"code_cahpp", "source", "created_at"}
                ),
                (import_id, now, now),
            )
            if preview.mode in {"full", "snapshot"}:
                connection.execute(
                    "UPDATE products SET active=0,updated_at=? WHERE source='CAHPP' AND last_seen_import_id IS NOT ?",
                    (now, import_id),
                )
            connection.execute(
                """INSERT INTO price_history(product_id,import_id,recorded_at,unit_price,conditionnement,qml)
                SELECT p.id,?,?,p.unit_price,p.conditionnement,p.qml FROM products p
                WHERE p.last_seen_import_id=? AND NOT EXISTS (SELECT 1 FROM price_history h WHERE h.product_id=p.id)""",
                (import_id, now, import_id),
            )
            review = connection.execute(
                "SELECT COUNT(*) FROM products p LEFT JOIN product_overrides po ON po.product_id=p.id WHERE p.active=1 AND "
                + CATALOG_REVIEW_SQL
            ).fetchone()[0]
            connection.execute(
                "UPDATE imports SET added_count=?,updated_count=?,missing_count=?,deactivated_count=?,review_count=?,warnings_json=? WHERE id=?",
                (
                    added,
                    updated,
                    missing,
                    deactivated,
                    review,
                    json.dumps(warnings, ensure_ascii=False),
                    import_id,
                ),
            )
            _save_settings(
                connection,
                {
                    "catalog_effective_period": preview.period,
                    "catalog_import_mode": preview.mode,
                },
            )
            progress(88, 100, "Actualisation de l'index de recherche…")
            if not self.database.rebuild_search(connection):
                raise CatalogImportError(
                    "L'index de recherche n'a pas pu être reconstruit. L'import entier a été annulé ; les données précédentes sont conservées."
                )
            # Le dernier point d'annulation précède le commit : une fermeture
            # ne doit pas signaler un échec après une mise à jour déjà validée.
            progress(100, 100, "Validation de la mise à jour…")
            connection.commit()
            return ImportResult(
                import_id,
                preview.filename,
                count,
                added,
                updated,
                missing,
                mode=preview.mode,
                period=preview.period,
                deactivated_count=deactivated,
                review_count=review,
                warnings=warnings,
                file_hash=preview.file_hash,
                previous_catalog_hash=settings.get("collaboration_catalog_hash", ""),
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
            # Un import annulé ne doit pas laisser croire que le cache FTS est vérifié.
            self.database._fts_verified = False
            self.database._search_stats_prepared = False

    @staticmethod
    def _suppliers(connection):
        connection.execute(
            "CREATE TEMP TABLE supplier_map(name TEXT PRIMARY KEY,supplier_id INTEGER)"
        )
        for incoming in connection.execute(
            "SELECT supplier_name,MIN(supplier_cahpp_id) AS code FROM incoming GROUP BY supplier_name"
        ).fetchall():
            name, code = incoming
            by_name = connection.execute(
                "SELECT * FROM suppliers WHERE name=?", (name,)
            ).fetchone()
            by_code = (
                connection.execute(
                    "SELECT * FROM suppliers WHERE cahpp_id=? ORDER BY id DESC LIMIT 1",
                    (code,),
                ).fetchone()
                if code
                else None
            )
            if by_name:
                supplier_id = by_name["id"]
                if code:
                    connection.execute(
                        "UPDATE suppliers SET cahpp_id=? WHERE id=?",
                        (code, supplier_id),
                    )
            elif by_code:
                # Une nouvelle dénomination ne doit pas renommer les anciennes
                # commandes. Copier la fiche conserve leurs coordonnées et leur ID.
                fields = (
                    "customer_number",
                    "contact_name",
                    "email",
                    "phone",
                    "address",
                    "website",
                    "franco_ht",
                    "minimum_order_ht",
                    "notes",
                    "updated_at",
                    "updated_by",
                )
                supplier_id = connection.execute(
                    "INSERT INTO suppliers(name,cahpp_id,"
                    + ",".join(fields)
                    + ") VALUES ("
                    + ",".join("?" for _ in range(2 + len(fields)))
                    + ")",
                    (
                        name,
                        code,
                        *(
                            by_code[key]
                            if key in {"franco_ht", "minimum_order_ht"}
                            else (by_code[key] or "")
                            for key in fields
                        ),
                    ),
                ).lastrowid
            else:
                supplier_id = connection.execute(
                    "INSERT INTO suppliers(name,cahpp_id) VALUES (?,?)", (name, code)
                ).lastrowid
            connection.execute(
                "INSERT INTO supplier_map VALUES (?,?)", (name, supplier_id)
            )

    @staticmethod
    def _resolved(preview, provided):
        delta = preview.mode == "delta"
        changed_pack = "(s.update_type IN ('MMC','ARC','SRC') OR instr(UPPER(COALESCE(s.update_state,'')),'CONDITIONNEMENT')>0)"
        resolved = {}
        for name in CATALOG_FIELDS:
            if delta and name not in provided:
                resolved[name] = (
                    f"p.{name}" if name in NUMERIC_FIELDS else f"COALESCE(p.{name},'')"
                )
            elif delta and name in TEXT_FIELDS and name != "code_cahpp":
                resolved[name] = f"COALESCE(NULLIF(s.{name},''),p.{name},'')"
            else:
                resolved[name] = (
                    f"s.{name}" if name in NUMERIC_FIELDS else f"COALESCE(s.{name},'')"
                )
        if delta and "qml" not in provided:
            resolved["qml"] = f"CASE WHEN {changed_pack} THEN NULL ELSE p.qml END"
        if delta:
            resolved["unit_price"] = (
                "CASE WHEN s.active=0 AND s.unit_price IS NULL THEN p.unit_price ELSE s.unit_price END"
            )
            resolved["vat"] = "COALESCE(s.vat,p.vat)"
        resolved["active"] = "COALESCE(s.active,1)"
        valid_pack = (
            f"COALESCE(NULLIF({resolved['conditionnement']},0),{resolved['qml']},0)>0"
        )
        supplied_pack = "COALESCE(NULLIF(s.conditionnement,0),s.qml,0)>0"
        invalid = f"NOT ({valid_pack})"
        invalid_tax = f"(({resolved['active']})=1 AND ({resolved['vat']}) IS NULL)"
        if delta:
            invalid_tax += " OR (s.update_type='MMT' AND s.vat IS NULL)"
        invalid += f" OR ({invalid_tax})"
        unknown = "0"
        if delta:
            # Un changement chiffré doit aussi invalider la vérification de
            # l'ancien colisage et les brouillons préparés avant cet import.
            changed_quantities = (
                f"p.id IS NOT NULL AND ({supplied_pack}) AND "
                f"(p.conditionnement IS NOT ({resolved['conditionnement']}) "
                f"OR p.qml IS NOT ({resolved['qml']}))"
            )
            invalid += f" OR ({changed_pack}) OR ({changed_quantities})"
            known = ",".join("'" + code + "'" for code in sorted(KNOWN_UPDATE_TYPES))
            unknown = f"COALESCE(s.update_type,'') NOT IN ({known})"
            invalid += f" OR ({unknown})"
        prefix = "'" + preview.file_hash + ":' || s.code_cahpp"
        if preview.mode == "snapshot":
            resolved["catalog_review_token"] = "COALESCE(s.review_token,'')"
            resolved["catalog_review_reason"] = "COALESCE(s.review_reason,'')"
        else:
            carried = "COALESCE(p.catalog_review_token,'')" if delta else "''"
            reason = "COALESCE(p.catalog_review_reason,'')" if delta else "''"
            resolved["catalog_review_token"] = (
                f"CASE WHEN {invalid} THEN {prefix} WHEN {supplied_pack} THEN '' ELSE {carried} END"
            )
            resolved["catalog_review_reason"] = (
                f"CASE WHEN {unknown} THEN 'Type d’évolution non reconnu : vérifiez le conditionnement et les tarifs.' WHEN {invalid_tax} THEN 'TVA absente ou modification sans valeur : taux à vérifier.' WHEN {invalid} THEN 'Conditionnement absent ou modifié : quantité à vérifier.' WHEN {supplied_pack} THEN '' ELSE {reason} END"
            )
        return resolved
