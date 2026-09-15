"""Generate two test purchase order PDFs for Phase 3 audit checks."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "test_docs"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "POTitle",
            parent=base["Title"],
            fontName="Times-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1f3d2b"),
            spaceAfter=6,
        ),
        "company": ParagraphStyle(
            "POCompany",
            parent=base["Normal"],
            fontName="Times-Bold",
            fontSize=11,
            leading=14,
        ),
        "body": ParagraphStyle(
            "POBody",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=10,
            leading=13,
        ),
        "label": ParagraphStyle(
            "POLabel",
            parent=base["Normal"],
            fontName="Times-Bold",
            fontSize=10,
            leading=13,
        ),
        "muted": ParagraphStyle(
            "POMuted",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#444444"),
        ),
    }


def build_purchase_order(
    path: Path,
    *,
    po_number: str,
    vendor: str,
    order_date: str,
    description: str,
    quantity: int,
    unit_price: float,
    total: float,
    bill_to: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    document = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=f"Purchase Order {po_number}",
    )

    line_total = quantity * unit_price
    header = Table(
        [
            [
                Paragraph("NORTHBRIDGE PROCUREMENT", styles["company"]),
                Paragraph("PURCHASE ORDER", styles["title"]),
            ],
            [
                Paragraph("18 Harbour Street<br/>Melbourne VIC 3000<br/>Australia", styles["muted"]),
                Paragraph(
                    f"<b>PO Number:</b> {po_number}<br/>"
                    f"<b>Order Date:</b> {order_date}<br/>"
                    f"<b>Payment Terms:</b> Net 30",
                    styles["body"],
                ),
            ],
        ],
        colWidths=[4.0 * inch, 3.0 * inch],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ]
        )
    )

    parties = Table(
        [
            [
                Paragraph("<b>Vendor</b>", styles["label"]),
                Paragraph("<b>Bill To</b>", styles["label"]),
            ],
            [
                Paragraph(
                    f"{vendor}<br/>Accounts Payable<br/>Please supply the goods and services below.",
                    styles["body"],
                ),
                Paragraph(bill_to.replace("\n", "<br/>"), styles["body"]),
            ],
        ],
        colWidths=[3.5 * inch, 3.5 * inch],
    )
    parties.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6eee8")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1f3d2b")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#1f3d2b")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    items = Table(
        [
            ["Description", "Qty", "Unit Price", "Amount"],
            [
                description,
                str(quantity),
                f"${unit_price:.2f}",
                f"${line_total:.2f}",
            ],
        ],
        colWidths=[3.6 * inch, 0.9 * inch, 1.3 * inch, 1.2 * inch],
    )
    items.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3d2b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#1f3d2b")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    totals = Table(
        [
            ["", "Total", f"${total:.2f}"],
        ],
        colWidths=[4.5 * inch, 1.3 * inch, 1.2 * inch],
    )
    totals.setStyle(
        TableStyle(
            [
                ("FONTNAME", (1, 0), (-1, 0), "Times-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("ALIGN", (1, 0), (-1, 0), "RIGHT"),
                ("LINEABOVE", (1, 0), (-1, 0), 1, colors.HexColor("#1f3d2b")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    story = [
        header,
        Spacer(1, 18),
        parties,
        Spacer(1, 18),
        Paragraph("Authorized items", styles["label"]),
        Spacer(1, 6),
        items,
        Spacer(1, 10),
        totals,
        Spacer(1, 24),
        Paragraph(
            "This purchase order is the official authorization to supply the listed items. "
            "Invoice against PO number "
            f"{po_number}. Quote the PO number on all correspondence.",
            styles["muted"],
        ),
    ]
    document.build(story)


def main() -> None:
    matching = OUTPUT_DIR / "po_matching.pdf"
    mismatch = OUTPUT_DIR / "po_mismatch.pdf"

    build_purchase_order(
        matching,
        po_number="12345",
        vendor="DEMO - Sliced Invoices",
        order_date="January 20, 2016",
        description="Web Design",
        quantity=1,
        unit_price=85.00,
        total=93.50,
        bill_to="DEMO - Sliced Invoices\nAccounts Receivable\nMelbourne VIC 3000",
    )
    build_purchase_order(
        mismatch,
        po_number="12345",
        vendor="Sliced Design Studio",
        order_date="January 28, 2016",
        description="Web Design",
        quantity=1,
        unit_price=75.00,
        total=82.50,
        bill_to="DEMO - Sliced Invoices\nAccounts Receivable\nMelbourne VIC 3000",
    )
    print(f"Wrote {matching}")
    print(f"Wrote {mismatch}")


if __name__ == "__main__":
    main()
