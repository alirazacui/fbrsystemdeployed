"""
========================================================
receipts/generators.py
 
Two receipt generators:
  ThermalReceiptGenerator  → 80mm thermal printer format
  A4InvoiceGenerator       → Full A4 formal invoice
 
Both use reportlab and save to S3 via Django's default storage.
 
Usage:
    from receipts.generators import ThermalReceiptGenerator, A4InvoiceGenerator
 
    # Generate thermal receipt
    pdf_url = ThermalReceiptGenerator(sale).generate()
 
    # Generate A4 invoice
    pdf_url = A4InvoiceGenerator(sale).generate()
========================================================
"""
 
import io
import logging
import qrcode
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, inch
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, Image,
)
from reportlab.pdfgen import canvas
 
logger = logging.getLogger(__name__)
 
# ── Thermal receipt dimensions ────────────────────────────────────────────────
THERMAL_WIDTH  = 80 * mm     # 80mm paper width
THERMAL_MARGIN = 4 * mm      # small margins for thermal
 
 
def _generate_qr_image(data: str, size_mm: float = 25) -> io.BytesIO:
    """
    Generates a QR code image as a BytesIO buffer.
    Used for FBR invoice QR code on receipts.
    """
    qr = qrcode.QRCode(
        version           = 1,
        error_correction  = qrcode.constants.ERROR_CORRECT_M,
        box_size          = 4,
        border            = 2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img    = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
 
 
def _s3_path_for_receipt(sale, receipt_type: str) -> str:
    """
    Returns the S3 storage path for a receipt.
    Path: company_{id}/invoices/{year}/{month}/{sale_number}_{type}.pdf
    """
    completed = sale.completed_at or timezone.now()
    year      = completed.strftime("%Y")
    month     = completed.strftime("%m")
    return (
        f"company_{sale.company_id}/invoices/{year}/{month}/"
        f"{sale.sale_number}_{receipt_type}.pdf"
    )
 
 
# ===========================================================================
# THERMAL RECEIPT GENERATOR (80mm)
# ===========================================================================
 
class ThermalReceiptGenerator:
    """
    Generates an 80mm thermal printer receipt PDF.
 
    Layout:
    ┌────────────────────────────┐
    │     COMPANY NAME           │  ← centered, bold
    │     Address, Phone         │  ← centered, small
    │     NTN: 1234567           │
    ├────────────────────────────┤
    │  SALE INVOICE              │
    │  INV-2025-000001           │
    │  Date: 15-Jan-2025 10:30   │
    │  Cashier: ahmed@store.com  │
    │  Customer: Walk-In         │
    ├────────────────────────────┤
    │  Item Name          Qty  Total │
    │  Widget A × 2       2   472  │
    │  Widget B           1   118  │
    ├────────────────────────────┤
    │  Subtotal:          Rs. 500  │
    │  Tax (18%):         Rs. 90   │
    │  Discount:          Rs. 0    │
    │  TOTAL:             Rs. 590  │
    ├────────────────────────────┤
    │  Cash:              Rs. 600  │
    │  Change:            Rs. 10   │
    ├────────────────────────────┤
    │  FBR Invoice: 7000007DI...   │
    │  [QR CODE]                   │
    │  Thank you for shopping!     │
    └────────────────────────────┘
    """
 
    def __init__(self, sale):
        self.sale    = sale
        self.company = sale.company
        self.buffer  = io.BytesIO()
 
    def generate(self, force_regenerate: bool = False) -> str:
    
        if self.sale.receipt_thermal_url and not force_regenerate:
            return self.sale.receipt_thermal_url

        self._build_pdf()
        url = self._save_to_s3("thermal")

        from django.utils import timezone
        self.sale.receipt_thermal_url  = url
        self.sale.receipt_generated_at = timezone.now()
        self.sale.save(update_fields=[
            "receipt_thermal_url",
            "receipt_generated_at",
            "updated_at",
            ])
        return url
 
    def _build_pdf(self):
        """Builds the complete thermal receipt using reportlab canvas."""
        from reportlab.lib.pagesizes import portrait
 
        # Dynamic page height based on content
        estimated_height = self._estimate_height()
        page_size        = (THERMAL_WIDTH, estimated_height)
 
        c = canvas.Canvas(self.buffer, pagesize=page_size)
        width, height = page_size
        y             = height - THERMAL_MARGIN
 
        # ── Helper functions ───────────────────────────────────────────
        def draw_text(text, x, y_pos, font="Helvetica", size=7, align="left"):
            c.setFont(font, size)
            if align == "center":
                c.drawCentredString(width / 2, y_pos, text)
            elif align == "right":
                c.drawRightString(width - THERMAL_MARGIN, y_pos, text)
            else:
                c.drawString(x, y_pos, text)
 
        def draw_line(y_pos):
            c.setLineWidth(0.3)
            c.line(THERMAL_MARGIN, y_pos, width - THERMAL_MARGIN, y_pos)
 
        def next_line(y_pos, spacing=8):
            return y_pos - spacing
 
        # ── Company header ─────────────────────────────────────────────
        draw_text(self.company.business_name.upper(), 0, y, "Helvetica-Bold", 10, "center")
        y = next_line(y, 11)
 
        if self.company.address:
            # wrap long address
            addr = self.company.address[:45]
            draw_text(addr, 0, y, "Helvetica", 6, "center")
            y = next_line(y, 8)
 
        if self.company.phone:
            draw_text(f"Tel: {self.company.phone}", 0, y, "Helvetica", 6, "center")
            y = next_line(y, 8)
 
        draw_text(f"NTN: {self.company.ntn}", 0, y, "Helvetica", 6, "center")
        y = next_line(y, 8)
 
        if self.company.strn:
            draw_text(f"STRN: {self.company.strn}", 0, y, "Helvetica", 6, "center")
            y = next_line(y, 8)
 
        # ── Separator ──────────────────────────────────────────────────
        draw_line(y)
        y = next_line(y, 6)
 
        # ── Invoice info ───────────────────────────────────────────────
        draw_text(self.sale.sale_type.upper(), 0, y, "Helvetica-Bold", 8, "center")
        y = next_line(y, 10)
 
        draw_text(f"Invoice #: {self.sale.sale_number}", THERMAL_MARGIN, y, size=7)
        y = next_line(y)
 
        completed = self.sale.completed_at or timezone.now()
        draw_text(
            f"Date: {completed.strftime('%d-%b-%Y %I:%M %p')}",
            THERMAL_MARGIN, y, size=7
        )
        y = next_line(y)
 
        draw_text(
            f"Cashier: {self.sale.cashier.get_full_name() or self.sale.cashier.email}",
            THERMAL_MARGIN, y, size=7
        )
        y = next_line(y)
 
        draw_text(
            f"Customer: {self.sale.customer.name}",
            THERMAL_MARGIN, y, size=7
        )
        y = next_line(y)
 
        if self.sale.customer.ntn_cnic:
            draw_text(
                f"NTN/CNIC: {self.sale.customer.ntn_cnic}",
                THERMAL_MARGIN, y, size=7
            )
            y = next_line(y)
 
        # ── Separator ──────────────────────────────────────────────────
        draw_line(y)
        y = next_line(y, 6)
 
        # ── Column headers ─────────────────────────────────────────────
        c.setFont("Helvetica-Bold", 7)
        c.drawString(THERMAL_MARGIN, y, "Item")
        c.drawRightString(width - THERMAL_MARGIN, y, "Amount")
        y = next_line(y, 3)
        draw_line(y)
        y = next_line(y, 6)
 
        # ── Line items ─────────────────────────────────────────────────
        for line in self.sale.lines.all():
            c.setFont("Helvetica", 7)
            # Product name (truncate if too long)
            name = line.product_name[:28]
            c.drawString(THERMAL_MARGIN, y, name)
            y = next_line(y, 8)
 
            # Qty × price = total
            detail = (
                f"  {line.quantity} × Rs.{line.unit_price}"
                f"  Tax: Rs.{line.sales_tax_applicable}"
            )
            c.setFont("Helvetica", 6)
            c.drawString(THERMAL_MARGIN, y, detail)
            c.setFont("Helvetica-Bold", 7)
            c.drawRightString(
                width - THERMAL_MARGIN, y,
                f"Rs. {line.line_total:.2f}"
            )
            y = next_line(y, 9)
 
        # ── Separator ──────────────────────────────────────────────────
        draw_line(y)
        y = next_line(y, 6)
 
        # ── Totals ─────────────────────────────────────────────────────
        def draw_total_row(label, value, bold=False):
            nonlocal y
            font = "Helvetica-Bold" if bold else "Helvetica"
            size = 8 if bold else 7
            c.setFont(font, size)
            c.drawString(THERMAL_MARGIN, y, label)
            c.drawRightString(width - THERMAL_MARGIN, y, f"Rs. {value:.2f}")
            y = next_line(y, 9 if bold else 8)
 
        draw_total_row("Subtotal:", float(self.sale.subtotal))
        if float(self.sale.total_discount) > 0:
            draw_total_row("Discount:", float(self.sale.total_discount))
        draw_total_row("Sales Tax:", float(self.sale.total_tax))
        if float(self.sale.total_fed) > 0:
            draw_total_row("FED:", float(self.sale.total_fed))
 
        draw_line(y)
        y = next_line(y, 4)
        draw_total_row("TOTAL:", float(self.sale.total_amount), bold=True)
        draw_line(y)
        y = next_line(y, 6)
 
        # ── Payment breakdown ──────────────────────────────────────────
        for payment in self.sale.payments.all():
            draw_total_row(
                f"{payment.get_payment_method_display()}:",
                float(payment.amount)
            )
 
        if float(self.sale.change_given) > 0:
            draw_total_row("Change:", float(self.sale.change_given))
 
        # ── FBR section ────────────────────────────────────────────────
        if self.sale.fbr_invoice_number:
            y = next_line(y, 4)
            draw_line(y)
            y = next_line(y, 6)
 
            draw_text("FBR VERIFIED INVOICE", 0, y, "Helvetica-Bold", 7, "center")
            y = next_line(y, 9)
 
            # Wrap long FBR invoice number
            fbr_no = self.sale.fbr_invoice_number
            if len(fbr_no) > 30:
                draw_text(fbr_no[:30], 0, y, "Helvetica", 6, "center")
                y = next_line(y, 8)
                draw_text(fbr_no[30:], 0, y, "Helvetica", 6, "center")
                y = next_line(y, 8)
            else:
                draw_text(fbr_no, 0, y, "Helvetica", 6, "center")
                y = next_line(y, 8)
 
            # QR Code
            if self.sale.fbr_qr_code:
                qr_buffer = _generate_qr_image(self.sale.fbr_qr_code, 25)
                qr_size   = 25 * mm
                qr_x      = (width - qr_size) / 2
                y        -= qr_size
                c.drawImage(
                    qr_buffer, qr_x, y,
                    width=qr_size, height=qr_size,
                )
                y = next_line(y, 4)
 
        # ── Footer ─────────────────────────────────────────────────────
        draw_line(y)
        y = next_line(y, 6)
        draw_text("Thank you for your business!", 0, y, "Helvetica", 7, "center")
        y = next_line(y, 8)
        draw_text(
            completed.strftime("Printed: %d-%b-%Y %I:%M %p"),
            0, y, "Helvetica", 6, "center"
        )
 
        c.save()
 
    def _estimate_height(self) -> float:
        """Estimates page height based on number of lines."""
        base_height  = 160 * mm
        lines_height = self.sale.lines.count() * 17 * mm
        qr_height    = 30 * mm if self.sale.fbr_qr_code else 0
        return base_height + lines_height + qr_height
 
    def _save_to_s3(self, receipt_type: str) -> str:
        """Saves PDF buffer to S3 and returns URL."""
        self.buffer.seek(0)
        path = _s3_path_for_receipt(self.sale, receipt_type)
        saved_path = default_storage.save(path, ContentFile(self.buffer.read()))
        return default_storage.url(saved_path)
 
 
# ===========================================================================
# A4 INVOICE GENERATOR
# ===========================================================================
 
class A4InvoiceGenerator:
    """
    Generates a full A4 formal invoice PDF.
 
    Layout:
    ┌──────────────────────────────────────────┐
    │  [LOGO]          SALES INVOICE           │
    │  Company Name    Invoice #: INV-2025-001 │
    │  Address         Date: 15-Jan-2025       │
    │  NTN / STRN      Status: PAID            │
    ├──────────────────────────────────────────┤
    │  BILL TO:                                │
    │  Customer Name   NTN/CNIC: 1234567       │
    │  Address         Type: Registered        │
    ├──────────────────────────────────────────┤
    │  # │ Description │ Qty │ Price │ Tax │ Total │
    │  1 │ Widget A    │  2  │ 200  │ 36 │  236  │
    ├──────────────────────────────────────────┤
    │                  Subtotal:    Rs. 400    │
    │                  Sales Tax:   Rs. 72     │
    │                  Discount:    Rs. 0      │
    │                  TOTAL:       Rs. 472    │
    ├──────────────────────────────────────────┤
    │  Payment: Cash Rs. 500  Change: Rs. 28   │
    ├──────────────────────────────────────────┤
    │  FBR Invoice Number: 7000007DI...        │
    │  [QR CODE]    Scenario: SN002            │
    └──────────────────────────────────────────┘
    """
 
    # Brand colors
    PRIMARY_COLOR   = colors.HexColor("#1a56db")   # blue
    SECONDARY_COLOR = colors.HexColor("#f3f4f6")   # light gray
    TEXT_COLOR      = colors.HexColor("#111827")   # near black
    MUTED_COLOR     = colors.HexColor("#6b7280")   # gray
 
    def __init__(self, sale):
        self.sale    = sale
        self.company = sale.company
        self.buffer  = io.BytesIO()
 
    def generate(self) -> str:
        """
        Generates the A4 invoice PDF and saves to S3.
        Returns the S3 URL.
        """
        self._build_pdf()
        return self._save_to_s3("a4")
 
    def _build_pdf(self):
        """Builds the A4 invoice using reportlab Platypus."""
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize       = A4,
            rightMargin    = 15 * mm,
            leftMargin     = 15 * mm,
            topMargin      = 15 * mm,
            bottomMargin   = 15 * mm,
        )
 
        styles  = getSampleStyleSheet()
        story   = []
        width   = A4[0] - 30 * mm   # usable width
 
        # ── Custom styles ──────────────────────────────────────────────
        title_style = ParagraphStyle(
            "InvoiceTitle",
            parent    = styles["Normal"],
            fontSize  = 22,
            fontName  = "Helvetica-Bold",
            textColor = self.PRIMARY_COLOR,
            alignment = TA_RIGHT,
        )
        header_style = ParagraphStyle(
            "HeaderStyle",
            parent    = styles["Normal"],
            fontSize  = 9,
            textColor = self.TEXT_COLOR,
            leading   = 14,
        )
        label_style = ParagraphStyle(
            "LabelStyle",
            parent    = styles["Normal"],
            fontSize  = 8,
            textColor = self.MUTED_COLOR,
        )
        section_style = ParagraphStyle(
            "SectionStyle",
            parent    = styles["Normal"],
            fontSize  = 9,
            fontName  = "Helvetica-Bold",
            textColor = self.PRIMARY_COLOR,
            spaceBefore = 6,
        )
 
        # ── HEADER ROW: Company info + Invoice title ───────────────────
        completed = self.sale.completed_at or timezone.now()
 
        company_info = [
            Paragraph(
                f"<b>{self.company.business_name}</b>",
                ParagraphStyle("co", fontSize=13, fontName="Helvetica-Bold",
                               textColor=self.TEXT_COLOR)
            ),
            Paragraph(self.company.address or "", header_style),
            Paragraph(f"Phone: {self.company.phone}", header_style) if self.company.phone else Spacer(1, 1),
            Paragraph(f"NTN: {self.company.ntn}", header_style),
        ]
        if self.company.strn:
            company_info.append(Paragraph(f"STRN: {self.company.strn}", header_style))
 
        invoice_info = [
            Paragraph(self.sale.sale_type.upper(), title_style),
            Spacer(1, 4),
            Paragraph(
                f"<b>Invoice #:</b> {self.sale.sale_number}",
                ParagraphStyle("inv", fontSize=9, alignment=TA_RIGHT)
            ),
            Paragraph(
                f"<b>Date:</b> {completed.strftime('%d %B %Y')}",
                ParagraphStyle("inv", fontSize=9, alignment=TA_RIGHT)
            ),
            Paragraph(
                f"<b>Time:</b> {completed.strftime('%I:%M %p')}",
                ParagraphStyle("inv", fontSize=9, alignment=TA_RIGHT)
            ),
            Paragraph(
                f"<b>Status:</b> PAID",
                ParagraphStyle("inv", fontSize=9, alignment=TA_RIGHT,
                               textColor=colors.green)
            ),
        ]
 
        header_table = Table(
            [[company_info, invoice_info]],
            colWidths=[width * 0.55, width * 0.45],
        )
        header_table.setStyle(TableStyle([
            ("VALIGN",     (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 4 * mm))
 
        # ── Blue divider ──────────────────────────────────────────────
        story.append(HRFlowable(
            width="100%", thickness=2,
            color=self.PRIMARY_COLOR, spaceAfter=4 * mm
        ))
 
        # ── BILL TO section ───────────────────────────────────────────
        customer     = self.sale.customer
        cashier_name = (
            self.sale.cashier.get_full_name() or self.sale.cashier.email
        )
 
        bill_left = [
            Paragraph("BILL TO", section_style),
            Paragraph(f"<b>{customer.name}</b>", header_style),
            Paragraph(f"NTN/CNIC: {customer.ntn_cnic or 'N/A'}", header_style),
            Paragraph(
                f"Type: {customer.get_registration_type_display()}",
                header_style
            ),
            Paragraph(f"Address: {customer.address or 'N/A'}", header_style),
        ]
 
        bill_right = [
            Paragraph("SERVED BY", section_style),
            Paragraph(f"<b>{cashier_name}</b>", header_style),
            Paragraph(
                f"Cashier: {self.sale.cashier.email}",
                header_style
            ),
        ]
        if self.sale.cash_session:
            bill_right.append(
                Paragraph(
                    f"Session: #{self.sale.cash_session.pk}",
                    header_style
                )
            )
 
        bill_table = Table(
            [[bill_left, bill_right]],
            colWidths=[width * 0.6, width * 0.4],
        )
        bill_table.setStyle(TableStyle([
            ("VALIGN",      (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND",  (0, 0), (-1, -1), self.SECONDARY_COLOR),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",(0, 0), (-1, -1), 8),
            ("TOPPADDING",  (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
            ("ROUNDEDCORNERS", (0, 0), (-1, -1), [4, 4, 4, 4]),
        ]))
        story.append(bill_table)
        story.append(Spacer(1, 4 * mm))
 
        # ── LINE ITEMS TABLE ──────────────────────────────────────────
        col_style = ParagraphStyle(
            "ColHead", fontSize=8, fontName="Helvetica-Bold",
            textColor=colors.white, alignment=TA_CENTER
        )
        cell_style  = ParagraphStyle("Cell", fontSize=8, alignment=TA_LEFT)
        right_style = ParagraphStyle("CellR", fontSize=8, alignment=TA_RIGHT)
 
        items_data = [[
            Paragraph("#",              col_style),
            Paragraph("Description",   col_style),
            Paragraph("HS Code",       col_style),
            Paragraph("Qty",           col_style),
            Paragraph("Unit Price",    col_style),
            Paragraph("Tax Rate",      col_style),
            Paragraph("Tax Amount",    col_style),
            Paragraph("Total",         col_style),
        ]]
 
        for i, line in enumerate(self.sale.lines.all(), 1):
            items_data.append([
                Paragraph(str(i),                         cell_style),
                Paragraph(line.product_name[:35],         cell_style),
                Paragraph(line.hs_code or "—",           cell_style),
                Paragraph(str(line.quantity),             right_style),
                Paragraph(f"Rs. {line.unit_price:.2f}",  right_style),
                Paragraph(line.tax_rate_percent,          right_style),
                Paragraph(
                    f"Rs. {line.sales_tax_applicable:.2f}", right_style
                ),
                Paragraph(f"Rs. {line.line_total:.2f}",  right_style),
            ])
 
        items_table = Table(
            items_data,
            colWidths=[
                width * 0.04,   # #
                width * 0.25,   # Description
                width * 0.10,   # HS Code
                width * 0.07,   # Qty
                width * 0.12,   # Unit Price
                width * 0.08,   # Tax Rate
                width * 0.12,   # Tax Amount
                width * 0.12,   # Total
            ],
            repeatRows=1,
        )
        items_table.setStyle(TableStyle([
            # Header row
            ("BACKGROUND",    (0, 0), (-1, 0),  self.PRIMARY_COLOR),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0),  8),
            ("TOPPADDING",    (0, 0), (-1, 0),  6),
            ("BOTTOMPADDING", (0, 0), (-1, 0),  6),
            # Data rows
            ("FONTSIZE",      (0, 1), (-1, -1), 8),
            ("TOPPADDING",    (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1),
             [colors.white, self.SECONDARY_COLOR]),
            # Grid
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("LINEBELOW",     (0, 0), (-1, 0),  1,   self.PRIMARY_COLOR),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(items_table)
        story.append(Spacer(1, 4 * mm))
 
        # ── TOTALS ────────────────────────────────────────────────────
        def total_row(label, value, bold=False, color=None):
            lbl_style = ParagraphStyle(
                "TL", fontSize=9,
                fontName="Helvetica-Bold" if bold else "Helvetica",
                alignment=TA_RIGHT,
                textColor=color or self.TEXT_COLOR,
            )
            val_style = ParagraphStyle(
                "TV", fontSize=9,
                fontName="Helvetica-Bold" if bold else "Helvetica",
                alignment=TA_RIGHT,
                textColor=color or self.TEXT_COLOR,
            )
            return [
                Paragraph("", styles["Normal"]),
                Paragraph("", styles["Normal"]),
                Paragraph("", styles["Normal"]),
                Paragraph("", styles["Normal"]),
                Paragraph("", styles["Normal"]),
                Paragraph("", styles["Normal"]),
                Paragraph(label, lbl_style),
                Paragraph(value, val_style),
            ]
 
        totals_data = [
            total_row("Subtotal:",  f"Rs. {self.sale.subtotal:.2f}"),
        ]
        if float(self.sale.total_discount) > 0:
            totals_data.append(
                total_row("Discount:",  f"- Rs. {self.sale.total_discount:.2f}")
            )
        totals_data.append(
            total_row("Sales Tax:", f"Rs. {self.sale.total_tax:.2f}")
        )
        if float(self.sale.total_fed) > 0:
            totals_data.append(
                total_row("FED Payable:", f"Rs. {self.sale.total_fed:.2f}")
            )
        totals_data.append(
            total_row(
                "TOTAL AMOUNT:",
                f"Rs. {self.sale.total_amount:.2f}",
                bold=True,
                color=self.PRIMARY_COLOR,
            )
        )
 
        totals_table = Table(
            totals_data,
            colWidths=[
                width * 0.04,
                width * 0.25,
                width * 0.10,
                width * 0.07,
                width * 0.12,
                width * 0.08,
                width * 0.18,
                width * 0.16,
            ],
        )
        totals_table.setStyle(TableStyle([
            ("LINEABOVE", (6, -1), (-1, -1), 1.5, self.PRIMARY_COLOR),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(totals_table)
        story.append(Spacer(1, 4 * mm))
 
        # ── PAYMENT SECTION ───────────────────────────────────────────
        story.append(HRFlowable(
            width="100%", thickness=0.5,
            color=colors.HexColor("#e5e7eb"), spaceAfter=3 * mm
        ))
        story.append(Paragraph("PAYMENT DETAILS", section_style))
        story.append(Spacer(1, 2 * mm))
 
        payment_rows = []
        for payment in self.sale.payments.all():
            payment_rows.append([
                Paragraph(
                    payment.get_payment_method_display(),
                    header_style
                ),
                Paragraph(
                    f"Rs. {payment.amount:.2f}",
                    ParagraphStyle("pv", fontSize=9, alignment=TA_RIGHT)
                ),
            ])
 
        if float(self.sale.change_given) > 0:
            payment_rows.append([
                Paragraph("Change Given:", header_style),
                Paragraph(
                    f"Rs. {self.sale.change_given:.2f}",
                    ParagraphStyle("pv", fontSize=9, alignment=TA_RIGHT)
                ),
            ])
 
        if payment_rows:
            pay_table = Table(
                payment_rows,
                colWidths=[width * 0.5, width * 0.5],
            )
            pay_table.setStyle(TableStyle([
                ("TOPPADDING",    (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(pay_table)
 
        # ── FBR SECTION ───────────────────────────────────────────────
        if self.sale.fbr_invoice_number:
            story.append(Spacer(1, 4 * mm))
            story.append(HRFlowable(
                width="100%", thickness=0.5,
                color=colors.HexColor("#e5e7eb"), spaceAfter=3 * mm
            ))
 
            fbr_left = [
                Paragraph("FBR VERIFIED INVOICE", section_style),
                Spacer(1, 2 * mm),
                Paragraph(
                    f"<b>FBR Invoice Number:</b>",
                    header_style
                ),
                Paragraph(
                    self.sale.fbr_invoice_number,
                    ParagraphStyle(
                        "fbr_no", fontSize=8,
                        textColor=self.PRIMARY_COLOR, fontName="Helvetica-Bold"
                    )
                ),
                Spacer(1, 2 * mm),
                Paragraph(
                    f"<b>Scenario:</b> {self.sale.fbr_scenario_id or 'N/A'}",
                    header_style
                ),
                Paragraph(
                    f"<b>Submitted:</b> "
                    f"{self.sale.fbr_submitted_at.strftime('%d-%b-%Y %I:%M %p') if self.sale.fbr_submitted_at else 'N/A'}",
                    header_style
                ),
            ]
 
            fbr_right = []
            if self.sale.fbr_qr_code:
                qr_buffer = _generate_qr_image(self.sale.fbr_qr_code)
                qr_img    = Image(qr_buffer, width=28 * mm, height=28 * mm)
                fbr_right.append(qr_img)
                fbr_right.append(
                    Paragraph(
                        "Scan to verify with FBR",
                        ParagraphStyle(
                            "qr_label", fontSize=7,
                            alignment=TA_CENTER, textColor=self.MUTED_COLOR
                        )
                    )
                )
 
            fbr_table = Table(
                [[fbr_left, fbr_right]],
                colWidths=[width * 0.65, width * 0.35],
            )
            fbr_table.setStyle(TableStyle([
                ("VALIGN",       (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND",   (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
                ("LEFTPADDING",  (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING",   (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
                ("BOX",          (0, 0), (-1, -1), 1, self.PRIMARY_COLOR),
            ]))
            story.append(fbr_table)
 
        # ── FOOTER ────────────────────────────────────────────────────
        story.append(Spacer(1, 6 * mm))
        story.append(HRFlowable(
            width="100%", thickness=0.5,
            color=colors.HexColor("#e5e7eb"), spaceAfter=3 * mm
        ))
        story.append(Paragraph(
            "Thank you for your business. This is a computer-generated invoice.",
            ParagraphStyle(
                "footer", fontSize=7, alignment=TA_CENTER,
                textColor=self.MUTED_COLOR
            )
        ))
        story.append(Paragraph(
            f"Generated: {timezone.now().strftime('%d-%b-%Y %I:%M %p')}",
            ParagraphStyle(
                "footer2", fontSize=7, alignment=TA_CENTER,
                textColor=self.MUTED_COLOR
            )
        ))
 
        doc.build(story)
 
    def _save_to_s3(self, receipt_type: str) -> str:
        """Saves PDF buffer to S3 and returns URL."""
        self.buffer.seek(0)
        path       = _s3_path_for_receipt(self.sale, receipt_type)
        saved_path = default_storage.save(path, ContentFile(self.buffer.read()))
        return default_storage.url(saved_path)
