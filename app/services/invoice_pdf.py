"""Demo invoice document (FR-FA-07): an itemised PDF marked as not a tax document."""

from pathlib import Path

from fpdf import FPDF

from app.i18n import t
from app.models import Invoice
from app.services import dates

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
REGULAR = FONT_DIR / "DejaVuSans.ttf"
BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"


def _font(pdf: FPDF) -> str:
    """DejaVu covers Slovak diacritics; fall back to a core font when it is missing."""
    if REGULAR.exists():
        pdf.add_font("DejaVu", "", str(REGULAR))
        pdf.add_font("DejaVu", "B", str(BOLD if BOLD.exists() else REGULAR))
        return "DejaVu"
    return "Helvetica"


def render(invoice: Invoice) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    font = _font(pdf)

    pdf.set_font(font, "B", 16)
    pdf.set_text_color(200, 0, 0)
    pdf.cell(0, 10, t("invoice.pdf.demo_banner"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    title_key = (
        "invoice.pdf.credit_note" if invoice.kind.value == "credit_note" else "invoice.pdf.title"
    )
    pdf.set_font(font, "B", 14)
    pdf.cell(
        0,
        10,
        f"{t(title_key)} {invoice.number or t('invoice.pdf.draft')}",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    pdf.set_font(font, "", 10)
    lines = [
        f"{t('invoice.status')}: {t('invoice.status.' + invoice.status.value)}",
        f"{t('invoice.customer')}: {invoice.customer.display_name} ({invoice.customer.username})",
    ]
    if invoice.customer.billing_name:
        lines.append(f"{t('invoice.pdf.billing')}: {invoice.customer.billing_name}")
    if invoice.issued_at:
        lines.append(
            f"{t('invoice.issued_at')}: {dates.format_date(dates.local_date(invoice.issued_at))}"
        )
    if invoice.cancels is not None:
        lines.append(f"{t('invoice.pdf.cancels')}: {invoice.cancels.number}")
    if invoice.note:
        lines.append(f"{t('orders.note')}: {invoice.note}")
    for line in lines:
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    widths = (100, 20, 30, 30)
    pdf.set_font(font, "B", 10)
    for width, key in zip(
        widths, ("invoice.item", "orders.quantity", "pumps.unit_price", "pumps.total"), strict=True
    ):
        pdf.cell(width, 8, t(key), border=1)
    pdf.ln()
    pdf.set_font(font, "", 10)
    for item in invoice.visible_items:
        pdf.cell(widths[0], 8, item.description[:70], border=1)
        pdf.cell(widths[1], 8, str(item.quantity), border=1, align="R")
        pdf.cell(widths[2], 8, f"{item.unit_price:.2f} €", border=1, align="R")
        pdf.cell(widths[3], 8, f"{item.amount:.2f} €", border=1, align="R")
        pdf.ln()
    pdf.set_font(font, "B", 11)
    pdf.cell(sum(widths[:3]), 9, t("pumps.total"), border=1)
    pdf.cell(widths[3], 9, f"{invoice.total:.2f} €", border=1, align="R")
    pdf.ln(14)

    pdf.set_font(font, "", 9)
    pdf.multi_cell(0, 5, t("invoice.pdf.footer"))
    return bytes(pdf.output())
