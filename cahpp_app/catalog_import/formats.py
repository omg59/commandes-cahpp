"""Contrats d'import explicites. Aucun accès à la base ni déduction de colisage."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from ..numbers import parse_decimal


LEGACY_COLUMNS = (
    "Catalogue",
    "IDFournisseur",
    "NomFournisseur",
    "CodeCahpp",
    "RéférenceArticle",
    "DésignationArticle",
    "ACL",
    "ACL13",
    "CIP13",
    "UCD13",
    "Conditionnement",
    "Qml",
    "TVA",
    "Nom_Classif",
    "Code_Classif",
    "PrixUnitaireCahpp",
    "PrixGAM",
    "EVOLUTION",
    "MAJTYPE",
    "LIBMAJOURETAT",
    "ZONE_FABRICATION",
    "SUBSTANCE_DANGEREUSE",
    "CONDITIONNEMENT_UNITAIRE",
    "MAJMOIS",
    "MarcheGAM",
)
CATALOG_FIELDS = (
    "catalogue",
    "supplier_cahpp_id",
    "supplier_name",
    "code_cahpp",
    "supplier_ref",
    "designation",
    "acl",
    "acl13",
    "cip13",
    "ucd13",
    "conditionnement",
    "qml",
    "vat",
    "classification_name",
    "classification_code",
    "unit_price",
    "gam_price",
    "evolution",
    "update_type",
    "update_state",
    "manufacturing_zone",
    "hazardous",
    "unit_packaging",
    "update_month",
    "gam_market",
)
NUMERIC_FIELDS = {
    "supplier_cahpp_id",
    "conditionnement",
    "qml",
    "vat",
    "unit_price",
    "gam_price",
}
TEXT_FIELDS = set(CATALOG_FIELDS) - NUMERIC_FIELDS
SNAPSHOT_FORMAT = "commandes-cahpp-catalogue-v1"
KNOWN_UPDATE_TYPES = {
    "MPB",
    "ANR",
    "ACM",
    "SCR",
    "IES",
    "SAC",
    "MPH",
    "MMT",
    "MMM",
    "ARE",
    "MMC",
    "AAA",
    "HRE",
    "AAP",
    "SSS",
    "TPF",
    "ARC",
    "SRC",
}


def normalize(value: object) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        unicodedata.normalize("NFKD", str(value if value is not None else ""))
        .encode("ascii", "ignore")
        .decode()
        .lower(),
    )


ALIASES = {
    normalize(label): name for label, name in zip(LEGACY_COLUMNS, CATALOG_FIELDS)
}
for name, labels in {
    "catalogue": ("CODE_CATALOGUE",),
    "supplier_cahpp_id": ("CODE_FOURNISSEUR",),
    "supplier_name": ("NOM_FOURNISSEUR",),
    "supplier_ref": ("REFERENCE",),
    "designation": ("DESIGNATION_FOURNISSEUR",),
    "classification_name": ("CLASSIFICATION",),
    "unit_price": ("PRIXCAHPP",),
    "evolution": ("EVOLUTIONS",),
    "update_month": ("MOIS_MISEAJOUR",),
    "active": ("ARTICLEACTIF",),
    "review_token": ("CAHPP_REVIEW_TOKEN",),
    "review_reason": ("CAHPP_REVIEW_REASON",),
}.items():
    ALIASES.update({normalize(label): name for label in labels})


class CatalogImportError(ValueError):
    """Fichier refusé avant toute modification de données métier."""


@dataclass(frozen=True)
class ImportOptions:
    confirm_baseline: bool = False
    allow_revision: bool = False
    confirm_full_replacement: bool = False
    confirm_snapshot_replacement: bool = False


@dataclass(frozen=True)
class ImportPreview:
    mode: str
    filename: str
    file_hash: str
    row_count: int
    period: str = ""
    warnings: tuple[str, ...] = ()
    confirmations: tuple[str, ...] = ()
    already_imported: bool = False


@dataclass(frozen=True)
class ImportResult:
    import_id: int
    filename: str
    row_count: int
    added_count: int
    updated_count: int
    missing_count: int
    already_imported: bool = False
    mode: str = "full"
    period: str = ""
    deactivated_count: int = 0
    review_count: int = 0
    warnings: tuple[str, ...] = ()
    file_hash: str = ""
    previous_catalog_hash: str = ""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def period_value(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m")
    text = str(value or "").strip().lower()
    for pattern in (r"^(\d{4})[-/](\d{1,2})$", r"^(\d{1,2})[-/](\d{4})$"):
        match = re.fullmatch(pattern, text)
        if match:
            first, second = map(int, match.groups())
            year, month = (first, second) if first > 31 else (second, first)
            if 1900 <= year <= 2200 and 1 <= month <= 12:
                return f"{year:04d}-{month:02d}"
    names = (
        "janvier",
        "fevrier",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "aout",
        "septembre",
        "octobre",
        "novembre",
        "decembre",
    )
    norm = normalize(text)
    for month, name in enumerate(names, 1):
        match = re.fullmatch(name + r"(\d{4})", norm)
        if match:
            return f"{int(match[1]):04d}-{month:02d}"
    raise CatalogImportError(
        "Mois de mise à jour absent ou non reconnu : utilisez un mois et une année."
    )


def text_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@dataclass
class CatalogWorkbook:
    path: Path
    workbook: object = field(init=False, repr=False)
    sheet: object = field(init=False, repr=False)
    header: dict[str, int] = field(init=False)
    header_row: int = field(init=False)
    mode: str = field(init=False)
    metadata: dict[str, str] = field(init=False, default_factory=dict)

    def __enter__(self):
        self.workbook = load_workbook(self.path, read_only=True, data_only=True)
        try:
            if "CAHPP_META" in self.workbook.sheetnames:
                self.metadata = {
                    str(row[0]): text_value(row[1])
                    for row in self.workbook["CAHPP_META"].iter_rows(values_only=True)
                    if len(row) >= 2 and row[0] is not None
                }
                if self.metadata.get("format") != SNAPSHOT_FORMAT:
                    raise CatalogImportError(
                        "Version d'instantané collaboratif non reconnue. Mettez l'application à jour."
                    )
            candidates = []
            for sheet in self.workbook:
                if sheet.title == "CAHPP_META":
                    continue
                for number, row in enumerate(
                    sheet.iter_rows(max_row=10, values_only=True), 1
                ):
                    recognized = [ALIASES.get(normalize(value)) for value in row]
                    if (
                        "code_cahpp" not in recognized
                        or "designation" not in recognized
                    ):
                        continue
                    keys = [key for key in recognized if key]
                    if len(keys) != len(set(keys)):
                        raise CatalogImportError(
                            f"En-têtes ambigus dans la feuille {sheet.title} : plusieurs colonnes désignent le même champ."
                        )
                    candidates.append(
                        (
                            sheet,
                            number,
                            {key: i for i, key in enumerate(recognized) if key},
                        )
                    )
                    break
            if len(candidates) != 1:
                raise CatalogImportError(
                    "Impossible d'identifier un tableau CAHPP unique (code, désignation et en-têtes attendus)."
                )
            self.sheet, self.header_row, self.header = candidates[0]
            monthly = "active" in self.header and "update_month" in self.header
            if self.metadata:
                self.mode = "snapshot"
                required = set(CATALOG_FIELDS) | {
                    "active",
                    "review_token",
                    "review_reason",
                }
            elif (
                normalize(self.sheet.title) == "tarifbasecomplete"
                and set(CATALOG_FIELDS) <= self.header.keys()
            ):
                self.mode = "full"
                required = set(CATALOG_FIELDS)
            elif normalize(self.sheet.title).startswith("evo") or monthly:
                self.mode = "delta"
                required = {
                    "code_cahpp",
                    "designation",
                    "supplier_name",
                    "supplier_cahpp_id",
                    "unit_price",
                    "vat",
                    "active",
                    "update_type",
                    "update_month",
                }
            else:
                self.mode = "full"
                required = set(CATALOG_FIELDS)
            missing = sorted(required - self.header.keys())
            if missing:
                raise CatalogImportError(
                    "Colonnes requises manquantes pour cet import : "
                    + ", ".join(missing)
                )
            if self.mode != "snapshot" and (
                {"review_token", "review_reason"} & self.header.keys()
            ):
                raise CatalogImportError(
                    "Les champs de validation sont réservés aux instantanés de l'application."
                )
            return self
        except Exception:
            self.workbook.close()
            raise

    def __exit__(self, *args):
        self.workbook.close()

    def rows(self):
        for number, values in enumerate(
            self.sheet.iter_rows(min_row=self.header_row + 1, values_only=True),
            self.header_row + 1,
        ):
            if not any(v not in (None, "") for v in values):
                continue
            row = {
                key: values[index] if index < len(values) else None
                for key, index in self.header.items()
            }
            code = text_value(row.get("code_cahpp"))
            if not code:
                raise CatalogImportError(f"Ligne {number} : code CAHPP manquant.")
            for key in row:
                if key in NUMERIC_FIELDS:
                    if row[key] in (None, ""):
                        row[key] = None
                    else:
                        try:
                            n = parse_decimal(
                                row[key],
                                key,
                                minimum=0,
                                maximum=100 if key == "vat" else None,
                            )
                            if key == "supplier_cahpp_id" and n != n.to_integral():
                                raise ValueError(
                                    "Le code fournisseur doit être entier."
                                )
                            row[key] = (
                                int(n) if key == "supplier_cahpp_id" else float(n)
                            )
                            if not math.isfinite(row[key]):
                                raise ValueError("Nombre trop grand.")
                        except ValueError as exc:
                            raise CatalogImportError(
                                f"Ligne {number}, {code}, {key} : {exc}"
                            ) from None
                elif key == "active":
                    # L'ancien TARIF_BASECOMPLETE fournit une colonne réservée
                    # vide : la présence de la référence définit alors l'activité.
                    # Un delta ou instantané exige au contraire un statut explicite.
                    if self.mode == "full" and row[key] in (None, ""):
                        row[key] = 1
                        continue
                    flag = normalize(row[key])
                    if flag not in {
                        "oui",
                        "yes",
                        "true",
                        "1",
                        "non",
                        "no",
                        "false",
                        "0",
                    }:
                        raise CatalogImportError(
                            f"Ligne {number}, {code} : statut ARTICLEACTIF non reconnu."
                        )
                    row[key] = int(flag in {"oui", "yes", "true", "1"})
                elif key == "update_type":
                    row[key] = text_value(row[key]).upper()
                else:
                    row[key] = text_value(row[key])
            if not row.get("supplier_name") or not row.get("designation"):
                raise CatalogImportError(
                    f"Ligne {number}, {code} : fournisseur ou désignation manquant."
                )
            if self.mode == "delta":
                row["period"] = period_value(row["update_month"])
            yield number, row
