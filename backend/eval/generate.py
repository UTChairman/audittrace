"""Write synthetic invoice and purchase-order PDFs (and degraded scan images)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pymupdf
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from eval.cases import COPIES, DEGRADED, INVOICES, PURCHASE_ORDERS, InvoiceSpec, LineSpec, PurchaseOrderSpec


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "EvalTitle",
            parent=base["Title"],
            fontName="Times-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1f3d2b"),
            spaceAfter=6,
        ),
        "company": ParagraphStyle(
            "EvalCompany",
            parent=base["Normal"],
            fontName="Times-Bold",
            fontSize=12,
            leading=15,
        ),
        "body": ParagraphStyle(
            "EvalBody",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=10,
            leading=13,
        ),
        "label": ParagraphStyle(
            "EvalLabel",
            parent=base["Normal"],
            fontName="Times-Bold",
            fontSize=10,
            leading=13,
        ),
        "muted": ParagraphStyle(
            "EvalMuted",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#444444"),
        ),
    }


def _money(value: float) -> str:
    return f"${value:.2f}"


def _line_table(items: tuple[LineSpec, ...], styles: dict[str, ParagraphStyle]) -> Table:
    rows = [["Description", "Qty", "Unit Price", "Amount"]]
    for item in items:
        label = item.description
        if item.detail:
            label = f"{item.description} — {item.detail}"
        rows.append([label, f"{item.quantity:g}", _money(item.unit_price), _money(item.amount)])
    table = Table(rows, colWidths=[3.6 * inch, 0.9 * inch, 1.3 * inch, 1.2 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3d2b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#1f3d2b")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def write_invoice(path: Path, spec: InvoiceSpec) -> None:
    styles = _styles()
    document = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=f"Invoice {spec.invoice_number}",
    )
    header = Table(
        [
            [
                Paragraph(spec.vendor, styles["company"]),
                Paragraph("TAX INVOICE", styles["title"]),
            ],
            [
                Paragraph(spec.address.replace(", ", "<br/>"), styles["muted"]),
                Paragraph(
                    f"<b>Invoice Number:</b> {spec.invoice_number}<br/>"
                    f"<b>Invoice Date:</b> {spec.invoice_date}<br/>"
                    f"<b>PO Number:</b> {spec.po_number}",
                    styles["body"],
                ),
            ],
        ],
        colWidths=[4.0 * inch, 3.0 * inch],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    totals_rows = [["", "Subtotal", _money(spec.subtotal)]]
    if spec.tax is not None:
        totals_rows.append(["", "Tax", _money(spec.tax)])
    totals_rows.append(["", "Total", _money(spec.total)])
    totals = Table(totals_rows, colWidths=[4.5 * inch, 1.3 * inch, 1.2 * inch])
    totals.setStyle(
        TableStyle(
            [
                ("FONTNAME", (1, -1), (-1, -1), "Times-Bold"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("LINEABOVE", (1, -1), (-1, -1), 1, colors.HexColor("#1f3d2b")),
            ]
        )
    )
    story = [
        header,
        Spacer(1, 18),
        Paragraph("Bill To: Northbridge Procurement, Melbourne VIC 3000", styles["body"]),
        Spacer(1, 14),
        _line_table(spec.line_items, styles),
        Spacer(1, 10),
        totals,
        Spacer(1, 20),
        Paragraph("Please remit in the currency shown. Amounts are marked with $.", styles["muted"]),
    ]
    document.build(story)


def write_purchase_order(path: Path, spec: PurchaseOrderSpec) -> None:
    styles = _styles()
    document = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=f"Purchase Order {spec.po_number}",
    )
    header = Table(
        [
            [
                Paragraph("NORTHBRIDGE PROCUREMENT", styles["company"]),
                Paragraph("PURCHASE ORDER", styles["title"]),
            ],
            [
                Paragraph("18 Harbour Street<br/>Melbourne VIC 3000<br/>Australia", styles["muted"]),
                Paragraph(
                    f"<b>PO Number:</b> {spec.po_number}<br/>"
                    f"<b>Order Date:</b> {spec.order_date}<br/>"
                    f"<b>Payment Terms:</b> Net 30",
                    styles["body"],
                ),
            ],
        ],
        colWidths=[4.0 * inch, 3.0 * inch],
    )
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    vendor = Table(
        [
            [Paragraph("<b>Vendor</b>", styles["label"]), Paragraph("<b>Bill To</b>", styles["label"])],
            [
                Paragraph(f"{spec.vendor}<br/>Please supply the items below.", styles["body"]),
                Paragraph(spec.bill_to.replace("\n", "<br/>"), styles["body"]),
            ],
        ],
        colWidths=[3.5 * inch, 3.5 * inch],
    )
    vendor.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#1f3d2b")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6eee8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    totals = Table(
        [["", "Total", _money(spec.total)]],
        colWidths=[4.5 * inch, 1.3 * inch, 1.2 * inch],
    )
    totals.setStyle(
        TableStyle(
            [
                ("FONTNAME", (1, 0), (-1, 0), "Times-Bold"),
                ("ALIGN", (1, 0), (-1, 0), "RIGHT"),
                ("LINEABOVE", (1, 0), (-1, 0), 1, colors.HexColor("#1f3d2b")),
            ]
        )
    )
    story = [
        header,
        Spacer(1, 18),
        vendor,
        Spacer(1, 18),
        Paragraph("Authorized items", styles["label"]),
        Spacer(1, 6),
        _line_table(spec.line_items, styles),
        Spacer(1, 10),
        totals,
    ]
    document.build(story)


def _render_page(pdf_path: Path, *, rotate: float = 0.0, fade: bool = False) -> pymupdf.Pixmap:
    with pymupdf.open(pdf_path) as doc:
        page = doc.load_page(0)
        matrix = pymupdf.Matrix(200 / 72, 200 / 72)
        if rotate:
            matrix = matrix.prerotate(rotate)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        if fade:
            view = pixmap.samples_mv
            channels = pixmap.n
            for index in range(0, len(view), channels):
                for channel in range(min(3, channels)):
                    view[index + channel] = int(view[index + channel] * 0.45 + 200 * 0.55)
    return pixmap


def write_degraded(source_pdf: Path, dest: Path, kind: str) -> None:
    if kind == "rotate":
        pixmap = _render_page(source_pdf, rotate=3.5)
    else:
        pixmap = _render_page(source_pdf, fade=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(dest))


def generate_all(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in INVOICES:
        path = output_dir / spec.filename
        write_invoice(path, spec)
        written.append(path)
    for spec in PURCHASE_ORDERS:
        path = output_dir / spec.filename
        write_purchase_order(path, spec)
        written.append(path)
    for spec in COPIES:
        source = output_dir / spec.source
        dest = output_dir / spec.filename
        shutil.copyfile(source, dest)
        written.append(dest)
    for spec in DEGRADED:
        dest = output_dir / spec.filename
        write_degraded(output_dir / spec.source, dest, spec.kind)
        written.append(dest)
    return written


def main() -> None:
    from app.config import PROJECT_ROOT

    output_dir = PROJECT_ROOT / "data" / "eval" / "docs"
    paths = generate_all(output_dir)
    print(f"Wrote {len(paths)} files to {output_dir}")


if __name__ == "__main__":
    main()
