from __future__ import annotations

from collections import defaultdict
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .database import Database
from .local_services import resolve_portable_path
from .paths import RESOURCE_DIR
from .app_logging import log_failure

logger = logging.getLogger(__name__)


BLUE = colors.HexColor("#174A7E")
LIGHT_BLUE = colors.HexColor("#EAF2F8")
MID_BLUE = colors.HexColor("#D5E6F3")
DARK = colors.HexColor("#1F2933")
GREY = colors.HexColor("#64748B")
LIGHT_GREY = colors.HexColor("#F6F8FA")

REGULAR_FONT = "Helvetica"
BOLD_FONT = "Helvetica-Bold"
try:
    regular_path = RESOURCE_DIR / "DejaVuSans.ttf"
    bold_path = RESOURCE_DIR / "DejaVuSans-Bold.ttf"
    if regular_path.is_file() and bold_path.is_file():
        pdfmetrics.registerFont(TTFont("CAHPP-Regular", str(regular_path)))
        pdfmetrics.registerFont(TTFont("CAHPP-Bold", str(bold_path)))
        REGULAR_FONT = "CAHPP-Regular"
        BOLD_FONT = "CAHPP-Bold"
except Exception as exc:
    log_failure(logger, "pdf_polices_repli", exc)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))


def _currency(value: object, decimals: int = 2) -> str:
    quantizer = Decimal("1").scaleb(-decimals)
    number = _decimal(value).quantize(quantizer, rounding=ROUND_HALF_UP)
    return f"{number:,.{decimals}f}".replace(",", " ").replace(".", ",") + " €"


def _quantity(value: object) -> str:
    number = _decimal(value)
    if number == number.to_integral():
        return f"{int(number):,}".replace(",", " ")
    return f"{number.normalize()}".replace(".", ",")


def _safe(value: object) -> str:
    return escape(str(value or ""))


def _make_page_footer(footer_text: str, show_page_number: bool):
    def page_footer(canvas, document) -> None:
        if not footer_text and not show_page_number:
            return
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D9E2EC"))
        canvas.line(18 * mm, 13 * mm, 192 * mm, 13 * mm)
        canvas.setFont(REGULAR_FONT, 8)
        canvas.setFillColor(GREY)
        if footer_text:
            canvas.drawString(18 * mm, 8 * mm, footer_text[:110])
        if show_page_number:
            canvas.drawRightString(
                192 * mm, 8 * mm, f"Page {canvas.getPageNumber()}"
            )
        canvas.restoreState()

    return page_footer


def generate_order_pdf(
    database: Database,
    order_id: int,
    output_path: Path | str,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    order, lines = database.get_order(order_id)
    if order["status"] == "Brouillon":
        database.validate_catalog_lines([dict(line) for line in lines])
    settings = database.get_settings()
    pdf_title = settings.get("pdf_title", "").strip() or "BON DE COMMANDE"
    footer_text = settings.get("pdf_footer_text", "").strip()
    show_page_number = settings.get("pdf_show_page_number", "1") != "0"

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=f"{pdf_title.title()} {order['order_number']}",
        author=settings.get("establishment_name") or "Commandes CAHPP",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "BodyCAHPP",
        parent=styles["BodyText"],
        fontName=REGULAR_FONT,
        fontSize=9,
        leading=12,
        textColor=DARK,
    )
    small = ParagraphStyle(
        "SmallCAHPP",
        parent=body,
        fontSize=8,
        leading=10,
        textColor=GREY,
    )
    heading = ParagraphStyle(
        "HeadingCAHPP",
        parent=styles["Heading1"],
        fontName=BOLD_FONT,
        fontSize=17,
        leading=21,
        textColor=BLUE,
        spaceAfter=4,
    )
    subtitle = ParagraphStyle(
        "SubtitleCAHPP",
        parent=body,
        fontName=BOLD_FONT,
        fontSize=10,
        leading=13,
        textColor=DARK,
    )
    cell = ParagraphStyle(
        "CellCAHPP",
        parent=body,
        fontSize=7.5,
        leading=9.5,
    )
    cell_center = ParagraphStyle(
        "CellCenterCAHPP",
        parent=cell,
        alignment=TA_CENTER,
    )
    cell_right = ParagraphStyle(
        "CellRightCAHPP",
        parent=cell,
        alignment=TA_RIGHT,
    )
    header_cell = ParagraphStyle(
        "HeaderCellCAHPP",
        parent=cell_center,
        fontName=BOLD_FONT,
        textColor=colors.white,
    )

    story = []
    logo_value = settings.get("logo_path") or ""
    logo_path = resolve_portable_path(logo_value) if logo_value else Path()
    logo = ""
    if logo_path.is_file():
        try:
            logo = Image(str(logo_path), width=28 * mm, height=20 * mm, kind="proportional")
        except Exception as exc:
            log_failure(logger, "pdf_logo_ignore", exc)
            logo = ""
    establishment_lines = [
        settings.get("establishment_name", ""),
        settings.get("establishment_subtitle", ""),
        settings.get("address_line1", ""),
        settings.get("address_line2", ""),
        settings.get("postal_city", ""),
    ]
    establishment = "<br/>".join(_safe(item) for item in establishment_lines if item)
    administrative = []
    if settings.get("finess"):
        administrative.append(f"FINESS : {_safe(settings['finess'])}")
    if settings.get("siret"):
        administrative.append(f"SIRET : {_safe(settings['siret'])}")
    if settings.get("ape"):
        administrative.append(f"APE : {_safe(settings['ape'])}")
    contact = " - ".join(
        _safe(item)
        for item in (settings.get("phone"), settings.get("email"))
        if item
    )
    identity_parts = [
        Paragraph(establishment or "Établissement à renseigner", subtitle),
    ]
    if administrative:
        identity_parts.append(Paragraph(" - ".join(administrative), small))
    if contact:
        identity_parts.append(Paragraph(contact, small))
    identity_table = Table([[part] for part in identity_parts], colWidths=[112 * mm])
    identity_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    if logo:
        header_table = Table(
            [[logo, identity_table]],
            colWidths=[36 * mm, 138 * mm],
            hAlign="LEFT",
        )
    else:
        header_table = Table(
            [[identity_table]],
            colWidths=[174 * mm],
            hAlign="LEFT",
        )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.extend([header_table, Spacer(1, 7 * mm)])

    order_date = datetime.fromisoformat(order["order_date"]).strftime("%d/%m/%Y")
    title_table = Table(
        [
            [
                Paragraph(_safe(pdf_title), heading),
                Paragraph(
                    f"<b>{_safe(order['order_number'])}</b><br/>Date : {order_date}",
                    ParagraphStyle(
                        "OrderMeta",
                        parent=body,
                        alignment=TA_RIGHT,
                        fontSize=9,
                        leading=13,
                    ),
                ),
            ]
        ],
        colWidths=[110 * mm, 64 * mm],
    )
    title_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.extend([title_table, Spacer(1, 4 * mm)])

    supplier_details = [f"<b>{_safe(order['supplier_name'])}</b>"]
    if order["customer_number"]:
        supplier_details.append(
            f"N° client : {_safe(order['customer_number'])}"
        )
    if order["supplier_email"]:
        supplier_details.append(_safe(order["supplier_email"]))
    if order["supplier_phone"]:
        supplier_details.append(_safe(order["supplier_phone"]))
    supplier_text = "<br/>".join(supplier_details)
    supplier_box = Table(
        [
            [
                Paragraph("FOURNISSEUR", small),
                Paragraph(supplier_text, body),
            ]
        ],
        colWidths=[34 * mm, 140 * mm],
    )
    supplier_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), MID_BLUE),
                ("BACKGROUND", (1, 0), (1, -1), LIGHT_BLUE),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8CDDC")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8CDDC")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([supplier_box, Spacer(1, 5 * mm)])

    table_data = [
        [
            Paragraph("Désignation", header_cell),
            Paragraph("Référence", header_cell),
            Paragraph("Cartons", header_cell),
            Paragraph("Unités / carton", header_cell),
            Paragraph("PU HT", header_cell),
            Paragraph("Total HT", header_cell),
        ]
    ]
    for line in lines:
        designation = line["designation"]
        table_data.append(
            [
                Paragraph(_safe(designation), cell),
                Paragraph(_safe(line["supplier_ref"]), cell_center),
                Paragraph(_quantity(line["cartons"]), cell_center),
                Paragraph(_quantity(line["units_per_carton"]), cell_center),
                Paragraph(_currency(line["unit_price"], 4), cell_right),
                Paragraph(_currency(line["total_ht"]), cell_right),
            ]
        )

    line_table = Table(
        table_data,
        colWidths=[
            70 * mm,
            28 * mm,
            15 * mm,
            20 * mm,
            20 * mm,
            21 * mm,
        ],
        repeatRows=1,
        hAlign="LEFT",
    )
    line_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C4CE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
    ]
    for row_number in range(2, len(table_data), 2):
        line_styles.append(("BACKGROUND", (0, row_number), (-1, row_number), LIGHT_GREY))
    line_table.setStyle(TableStyle(line_styles))
    story.extend([line_table, Spacer(1, 4 * mm)])

    vat_totals: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0"))
    for line in lines:
        rate = _decimal(line["vat"])
        vat_totals[rate] += _decimal(line["total_ht"]) * rate / Decimal("100")

    totals_data = [
        ["Total HT", _currency(order["total_ht"])],
    ]
    for rate, amount in sorted(vat_totals.items()):
        totals_data.append(
            [f"TVA {_quantity(rate)} %", _currency(amount)]
        )
    totals_data.append(["Total TTC", _currency(order["total_ttc"])])
    totals_table = Table(
        [
            [
                Paragraph(f"<b>{_safe(label)}</b>", cell_right),
                Paragraph(f"<b>{_safe(value)}</b>", cell_right),
            ]
            for label, value in totals_data
        ],
        colWidths=[38 * mm, 33 * mm],
        hAlign="RIGHT",
    )
    totals_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
                ("BACKGROUND", (0, -1), (-1, -1), MID_BLUE),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9DB6C8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C7D5DF")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    notes = []
    if order["requester_service"]:
        notes.append(
            Paragraph(
                f"<b>Service / unité destinataire :</b> "
                f"{_safe(order['requester_service'])}",
                body,
            )
        )
    if order["notes"]:
        notes.append(Paragraph(f"<b>Note :</b> {_safe(order['notes'])}", body))
    summary = Table(
        [[notes, totals_table]],
        colWidths=[100 * mm, 74 * mm],
        hAlign="LEFT",
    )
    summary.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 6),
                ("LEFTPADDING", (1, 0), (1, 0), 3),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(KeepTogether(summary))

    page_footer = _make_page_footer(footer_text, show_page_number)
    document.build(
        story,
        onFirstPage=page_footer,
        onLaterPages=page_footer,
    )
    database.update_order_pdf(order_id, str(output_path))
    return output_path
