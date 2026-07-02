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
 
    # Brand colors - Matching the reference invoice style
    PRIMARY_COLOR   = colors.HexColor("#0f3d64")   # Dark blue for company name
    SECONDARY_COLOR = colors.HexColor("#f8f9fa")   # Light gray
    TEXT_COLOR      = colors.HexColor("#333333")   # Dark gray/black
    MUTED_COLOR     = colors.HexColor("#888888")   # Gray
    ACCENT_COLOR    = colors.HexColor("#00a651")   # Green for FBR and borders
 
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
            fontSize  = 20,
            leading   = 24,
            fontName  = "Helvetica-Bold",
            textColor = self.PRIMARY_COLOR,
            spaceAfter = 8,
        )
        header_style = ParagraphStyle(
            "HeaderStyle",
            parent    = styles["Normal"],
            fontSize  = 8,
            textColor = self.TEXT_COLOR,
            leading   = 12,
        )
        label_style = ParagraphStyle(
            "LabelStyle",
            parent    = styles["Normal"],
            fontSize  = 7,
            textColor = self.MUTED_COLOR,
            textTransform = "uppercase",
        )
        section_style = ParagraphStyle(
            "SectionStyle",
            parent    = styles["Normal"],
            fontSize  = 8,
            fontName  = "Helvetica-Bold",
            textColor = self.ACCENT_COLOR,
            spaceBefore = 4,
            spaceAfter = 4,
            textTransform = "uppercase",
        )
 
        # ── TOP GREEN BAR ──────────────────────────────────────────────
        story.append(HRFlowable(
            width="100%", thickness=4,
            color=self.ACCENT_COLOR, spaceAfter=8 * mm, spaceBefore=0
        ))

        # ── HEADER ROW: Company info + FBR Info ───────────────────
        completed = self.sale.completed_at or timezone.now()
 
        # Top Left Info
        company_info = [
            Paragraph(f"<b>{self.company.business_name.upper()}</b>", title_style),
            Paragraph(f"NTN {self.company.ntn}", label_style),
            Spacer(1, 6 * mm)
        ]
        
        info_data = [
            [Paragraph("INVOICE NUMBER", label_style), Paragraph(f"<b>{self.sale.sale_number}</b>", header_style)],
            [Paragraph("INVOICE DATE", label_style), Paragraph(completed.strftime('%d %b %Y'), header_style)],
        ]
        
        if self.sale.fbr_invoice_number:
            info_data.append([
                Paragraph("FBR INVOICE", label_style),
                Paragraph(f"<b>{self.sale.fbr_invoice_number}</b>", ParagraphStyle("FBRInv", parent=header_style, textColor=self.ACCENT_COLOR))
            ])
            status_badge = Paragraph(
                "<b>FBR VALIDATED</b>", 
                ParagraphStyle("Badge", fontSize=7, textColor=self.ACCENT_COLOR, alignment=TA_CENTER)
            )
            # Create a simple badge-like appearance using a Table
            badge_table = Table([[status_badge]], colWidths=[30 * mm], rowHeights=[6 * mm])
            badge_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e6f6eb")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ROUNDEDCORNERS", (0, 0), (-1, -1), [3, 3, 3, 3])
            ]))
            info_data.append([Paragraph("STATUS", label_style), badge_table])
        
        info_table = Table(info_data, colWidths=[width * 0.15, width * 0.35])
        info_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        company_info.append(info_table)
 
        # Top Right Info (FBR Logo and QR)
        fbr_right = []
        if self.sale.fbr_qr_code:
            qr_buffer = _generate_qr_image(self.sale.fbr_qr_code)
            qr_img = Image(qr_buffer, width=28 * mm, height=28 * mm)
            
            # Use the actual FBR logo image from the project folder
            try:
                fbr_logo = Image("/home/ali-raza/fbr_pos_project/fbr_digital_invoice.png", width=34 * mm, height=26 * mm)
            except Exception:
                # Fallback if image isn't found
                fbr_logo = Paragraph("<b>FBR LOGO MISSING</b>", ParagraphStyle("F1", fontSize=10, textColor=colors.red))
            
            qr_table_data = [
                [fbr_logo, qr_img],
                [Paragraph("FBR DIGITAL INVOICING", ParagraphStyle("q1", fontSize=6, textColor=self.MUTED_COLOR, alignment=TA_CENTER)),
                 Paragraph("SCAN TO VERIFY", ParagraphStyle("q2", fontSize=6, textColor=self.MUTED_COLOR, alignment=TA_CENTER))]
            ]
            qr_table = Table(qr_table_data, colWidths=[38 * mm, 32 * mm])
            qr_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            fbr_right.append(qr_table)
 
        header_table = Table(
            [[company_info, fbr_right]],
            colWidths=[width * 0.60, width * 0.40],
        )
        header_table.setStyle(TableStyle([
            ("VALIGN",     (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 4 * mm))
 
        # ── Light gray divider ──────────────────────────────────────────────
        col_style   = ParagraphStyle("ColHead", fontSize=8, fontName="Helvetica-Bold", textColor=self.MUTED_COLOR, alignment=TA_CENTER)
        cell_style  = ParagraphStyle("Cell", fontSize=9, alignment=TA_LEFT, textColor=self.TEXT_COLOR)
        right_style = ParagraphStyle("CellR", fontSize=9, alignment=TA_RIGHT, textColor=self.TEXT_COLOR)

        items_data = [[
            Paragraph("#",              col_style),
            Paragraph("HS Code",       col_style),
            Paragraph("Item",          col_style),
            Paragraph("Qty",           col_style),
            Paragraph("Unit",          col_style),
            Paragraph("Rate",          col_style),
            Paragraph("Tax %",         col_style),
            Paragraph("Tax",           col_style),
            Paragraph("Amount",        col_style),
        ]]

        for idx, line in enumerate(self.sale.lines.all(), start=1):
            prod = line.product
            items_data.append([
                Paragraph(f"{idx:02d}", cell_style),
                Paragraph(prod.hs_code or "—", cell_style),
                Paragraph(f"<b>{prod.name}</b>", cell_style),
                Paragraph(f"{line.quantity:g}", right_style),
                Paragraph(prod.unit_of_measure or "—", cell_style),
                Paragraph(f"{line.unit_price:.2f}", right_style),
                Paragraph(line.tax_rate_percent or "—", right_style),
                Paragraph(f"{line.sales_tax_applicable:.2f}", right_style),
                Paragraph(f"<b>{line.line_total:.2f}</b>", right_style),
            ])

        items_table = Table(
            items_data,
            colWidths=[
                width * 0.05,   # #
                width * 0.12,   # HS Code
                width * 0.25,   # Item
                width * 0.07,   # Qty
                width * 0.10,   # Unit
                width * 0.11,   # Rate
                width * 0.07,   # Tax %
                width * 0.11,   # Tax
                width * 0.12,   # Amount
            ],
            repeatRows=1,
        )
        items_table.setStyle(TableStyle([
            # Header row
            ("TEXTCOLOR",     (0, 0), (-1, 0),  self.MUTED_COLOR),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0),  8),
            ("TOPPADDING",    (0, 0), (-1, 0),  8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            # Data rows
            ("FONTSIZE",      (0, 1), (-1, -1), 9),
            ("TEXTCOLOR",     (0, 1), (-1, -1), self.TEXT_COLOR),
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
                "TV", fontSize=10,
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
                Paragraph("", styles["Normal"]),
                Paragraph(label, lbl_style),
                Paragraph(value, val_style),
            ]
 
        totals_data = [
            total_row("Subtotal",  f"{self.sale.subtotal:.2f}"),
        ]
        if float(self.sale.total_discount) > 0:
            totals_data.append(total_row("Discount",  f"-{self.sale.total_discount:.2f}"))
        totals_data.append(total_row("Sales Tax", f"{self.sale.total_tax:.2f}"))
        if float(self.sale.total_fed) > 0:
            totals_data.append(total_row("FED Payable", f"{self.sale.total_fed:.2f}"))
        
        # Add grand total row
        totals_data.append(
            total_row(
                "GRAND TOTAL",
                f"Rs. {self.sale.total_amount:.2f}",
                bold=True,
                color=self.ACCENT_COLOR,
            )
        )
        totals_data.append(total_row("Paid", f"{self.sale.amount_paid:.2f}"))
        balance = max(0, float(self.sale.total_amount) - float(self.sale.amount_paid))
        totals_data.append(total_row("Balance", f"{balance:.2f}"))
 
        totals_table = Table(
            totals_data,
            colWidths=[
                width * 0.05,   # #
                width * 0.12,   # HS Code
                width * 0.25,   # Item
                width * 0.07,   # Qty
                width * 0.10,   # Unit
                width * 0.11,   # Rate
                width * 0.07,   # Tax %
                width * 0.11,   # Tax
                width * 0.12,   # Amount
            ],
        )
        totals_table.setStyle(TableStyle([
            ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",  (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("LINEABOVE",   (-2, -3), (-1, -3), 1, self.MUTED_COLOR),
            ("LINEBELOW",   (-2, -3), (-1, -3), 1, self.MUTED_COLOR),
            ("BACKGROUND",  (-2, -3), (-1, -3), colors.HexColor("#f4fbf6")),
        ]))
        story.append(totals_table)
        story.append(Spacer(1, 8 * mm))
        
        # ── FBR FOOTER ───────────────────────────────────────────────
        story.append(Paragraph("FBR AUTHENTICATION", ParagraphStyle("fbr_auth_h", fontSize=8, fontName="Helvetica-Bold", textColor=self.ACCENT_COLOR, spaceAfter=2)))
        auth_text = f"This invoice was submitted to FBR Digital Invoicing and validated by PRAL on <b>{completed.strftime('%d %b %Y, %H:%M')}</b>. "
        if self.sale.fbr_invoice_number:
            auth_text += f"FBR Invoice Number: <b>{self.sale.fbr_invoice_number}</b>. "
        auth_text += "To verify, scan the QR code with the FBR <b>Tax Asaan</b> app or look the number up at <b>e.fbr.gov.pk</b>. If the number cannot be verified there, the invoice is not authentic."
        story.append(Paragraph(auth_text, ParagraphStyle("fbr_auth", fontSize=7, textColor=self.MUTED_COLOR, leading=10, spaceAfter=4)))
        
        story.append(Paragraph("This is a computer-generated invoice and does not require a physical signature. Errors and omissions excepted. Goods sold are not returnable except under our documented returns policy.", ParagraphStyle("fbr_auth2", fontSize=7, textColor=colors.HexColor("#aaaaaa"), leading=10, spaceAfter=2)))
        story.append(Paragraph("Issued via FBR POS System - FBR Digital Invoicing compliant.", ParagraphStyle("fbr_auth3", fontSize=6, textColor=colors.HexColor("#aaaaaa"), leading=10)))
        
        doc.build(story)
 
    def _save_to_s3(self, receipt_type: str) -> str:
        """Saves PDF buffer to S3 and returns URL."""
        self.buffer.seek(0)
        path       = _s3_path_for_receipt(self.sale, receipt_type)
        saved_path = default_storage.save(path, ContentFile(self.buffer.read()))
        return default_storage.url(saved_path)
