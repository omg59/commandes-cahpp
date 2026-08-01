from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


BLUE = "1F6F9F"
LIGHT_BLUE = "E8F2F8"


def _prepare_sheet(sheet, headers: list[str]) -> None:
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=BLUE)
        cell.alignment = Alignment(horizontal="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def _finish_sheet(sheet) -> None:
    sheet.auto_filter.ref = sheet.dimensions
    for index, column in enumerate(sheet.columns, start=1):
        values = [str(cell.value or "") for cell in column]
        width = min(55, max(10, max(len(value) for value in values) + 2))
        sheet.column_dimensions[get_column_letter(index)].width = width
    for row in sheet.iter_rows(min_row=2):
        if row[0].row % 2 == 0:
            for cell in row:
                cell.fill = PatternFill("solid", fgColor=LIGHT_BLUE)


def export_statistics_workbook(
    result: dict[str, object],
    date_from: date,
    date_to: date,
    destination: Path | str,
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = "Synthèse"
    summary = dict(result.get("summary") or {})
    summary_sheet.append(["Statistiques Commandes CAHPP"])
    summary_sheet["A1"].font = Font(bold=True, size=16, color=BLUE)
    summary_sheet.append(["Période", date_from.isoformat(), date_to.isoformat()])
    summary_sheet.append(["Commandes envoyées", summary.get("order_count", 0)])
    summary_sheet.append(["Fournisseurs", summary.get("supplier_count", 0)])
    summary_sheet.append(["Total HT", summary.get("total_ht", 0)])
    summary_sheet.append(["Total TTC", summary.get("total_ttc", 0)])
    summary_sheet.column_dimensions["A"].width = 28
    summary_sheet.column_dimensions["B"].width = 18
    summary_sheet.column_dimensions["C"].width = 18
    summary_sheet["B5"].number_format = '#,##0.00 [$€-fr-FR]'
    summary_sheet["B6"].number_format = '#,##0.00 [$€-fr-FR]'

    supplier_sheet = workbook.create_sheet("Fournisseurs")
    _prepare_sheet(
        supplier_sheet,
        [
            "Fournisseur",
            "Commandes",
            "Total HT",
            "Total TTC",
            "Confirmation moyenne (j)",
            "Livraison moyenne (j)",
            "Commandes à recevoir",
        ],
    )
    for row in result.get("suppliers", []):
        supplier_sheet.append(
            [
                row["supplier_name"],
                row["order_count"],
                row["total_ht"],
                row["total_ttc"],
                row["average_confirmation_days"],
                row["average_delivery_days"],
                row["incomplete_count"],
            ]
        )
    for row in supplier_sheet.iter_rows(min_row=2):
        row[2].number_format = '#,##0.00 [$€-fr-FR]'
        row[3].number_format = '#,##0.00 [$€-fr-FR]'
    _finish_sheet(supplier_sheet)

    product_sheet = workbook.create_sheet("Produits")
    _prepare_sheet(
        product_sheet,
        ["Fournisseur", "Référence", "Désignation", "Cartons", "Unités", "Total HT"],
    )
    for row in result.get("products", []):
        product_sheet.append(
            [
                row["supplier_name"],
                row["supplier_ref"],
                row["designation"],
                row["cartons"],
                row["total_units"],
                row["total_ht"],
            ]
        )
    for row in product_sheet.iter_rows(min_row=2):
        row[5].number_format = '#,##0.00 [$€-fr-FR]'
    _finish_sheet(product_sheet)

    price_sheet = workbook.create_sheet("Écarts de prix")
    _prepare_sheet(
        price_sheet,
        [
            "Fournisseur",
            "Référence",
            "Désignation",
            "Dernière commande",
            "Date",
            "Prix commandé",
            "Prix actuel",
            "Écart",
            "Écart %",
        ],
    )
    for row in result.get("price_variances", []):
        price_sheet.append(
            [
                row["supplier_name"],
                row["supplier_ref"],
                row["designation"],
                row["order_number"],
                row["order_date"],
                row["ordered_price"],
                row["current_price"],
                row["difference"],
                row["difference_percent"],
            ]
        )
    for row in price_sheet.iter_rows(min_row=2):
        for cell in row[5:8]:
            cell.number_format = '#,##0.0000 [$€-fr-FR]'
        row[8].number_format = '0.0%'
        if row[8].value is not None:
            row[8].value = float(row[8].value) / 100
    _finish_sheet(price_sheet)

    workbook.save(destination)
    return destination
