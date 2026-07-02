from django.shortcuts import render

# Create your views here.
"""
========================================================
reports/views.py
 
Five report endpoints:
 
POS SIDE (scoped to requesting user's company):
  GET /api/reports/sales/today/          → today's summary
  GET /api/reports/sales/?from=&to=      → date range sales
  GET /api/reports/products/top/         → top selling products
  GET /api/reports/inventory/            → stock levels + low stock
 
ADMIN SIDE (platform admin only):
  GET /api/reports/admin/invoices/       → all invoices across all companies
  GET /api/reports/admin/activity/       → user activity log
========================================================
"""
 
import logging
from django.db.models import (
    Sum, Count, Avg, F, Q,
    DecimalField, IntegerField,
)
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
 
from common.permissions import IsAdmin, IsClientUser, IsActiveUser
 
logger = logging.getLogger(__name__)
 
 
# ---------------------------------------------------------------------------
# Helper — parse date range from request params
# ---------------------------------------------------------------------------
 
def _parse_date_range(request):
    """
    Parses ?from=YYYY-MM-DD&to=YYYY-MM-DD from request.
    Defaults to today if not provided.
    Returns (date_from, date_to) as date objects.
    """
    today     = timezone.now().date()
    date_from = request.query_params.get("from", str(today))
    date_to   = request.query_params.get("to",   str(today))
 
    try:
        date_from = parse_date(date_from) or today
        date_to   = parse_date(date_to)   or today
    except (ValueError, TypeError):
        date_from = today
        date_to   = today
 
    # Ensure from <= to
    if date_from > date_to:
        date_from, date_to = date_to, date_from
 
    return date_from, date_to
 
 
def _make_datetime_range(date_from, date_to):
    """Convert date range to datetime range covering full days."""
    from datetime import datetime, time
    dt_from = timezone.make_aware(datetime.combine(date_from, time.min))
    dt_to   = timezone.make_aware(datetime.combine(date_to,   time.max))
    return dt_from, dt_to
 
 
# ===========================================================================
# POS REPORTS — scoped to company
# ===========================================================================
 
@api_view(["GET"])
@permission_classes([IsActiveUser])
def sales_today(request):
    """
    GET /api/reports/sales/today/
 
    Today's sales summary for the requesting user's company.
 
    Returns:
        total_sales        → number of completed sales today
        total_revenue      → gross revenue (incl. tax)
        total_subtotal     → revenue excl. tax
        total_tax          → total sales tax collected
        total_discount     → total discounts given
        total_cash         → cash payments today
        total_card         → card payments today
        total_cheque       → cheque payments today
        total_bank         → bank transfer payments today
        average_sale_value → average sale amount
        hourly_breakdown   → sales count + revenue per hour
    """
    from pos.models import Sale, SalePayment, SaleStatus, PaymentMethod
 
    company = request.user.company
    today   = timezone.now().date()
    dt_from, dt_to = _make_datetime_range(today, today)
 
    # Base queryset — completed sales today for this company
    sales_qs = Sale.objects.filter(
        company      = company,
        status       = SaleStatus.COMPLETED,
        completed_at__range = (dt_from, dt_to),
    )
 
    # Aggregate totals
    totals = sales_qs.aggregate(
        total_sales    = Count("id"),
        total_revenue  = Sum("total_amount")   or 0,
        total_subtotal = Sum("subtotal")        or 0,
        total_tax      = Sum("total_tax")       or 0,
        total_discount = Sum("total_discount")  or 0,
        avg_sale       = Avg("total_amount"),
    )
 
    # Payment method breakdown
    payments_qs = SalePayment.objects.filter(
        sale__company      = company,
        sale__status       = SaleStatus.COMPLETED,
        sale__completed_at__range = (dt_from, dt_to),
    )
 
    payment_totals = {}
    for method in PaymentMethod.values:
        total = payments_qs.filter(
            payment_method=method
        ).aggregate(total=Sum("amount"))["total"] or 0
        payment_totals[f"total_{method}"] = float(total)
 
    # Hourly breakdown (for sales trend chart)
    from django.db.models.functions import ExtractHour
    hourly = list(
        sales_qs
        .annotate(hour=ExtractHour("completed_at"))
        .values("hour")
        .annotate(
            count   = Count("id"),
            revenue = Sum("total_amount"),
        )
        .order_by("hour")
    )
 
    # FBR submission summary
    fbr_summary = sales_qs.values(
        "fbr_submission_status"
    ).annotate(count=Count("id"))
 
    return Response({
        "date":             str(today),
        "company":          company.business_name,
        "total_sales":      totals["total_sales"]    or 0,
        "total_revenue":    float(totals["total_revenue"]  or 0),
        "total_subtotal":   float(totals["total_subtotal"] or 0),
        "total_tax":        float(totals["total_tax"]      or 0),
        "total_discount":   float(totals["total_discount"] or 0),
        "average_sale":     float(totals["avg_sale"]       or 0),
        **payment_totals,
        "hourly_breakdown": hourly,
        "fbr_summary":      list(fbr_summary),
    })
 
 
@api_view(["GET"])
@permission_classes([IsActiveUser])
def sales_range(request):
    """
    GET /api/reports/sales/?from=2025-01-01&to=2025-01-31
 
    Date range sales report for the requesting user's company.
 
    Returns:
        summary            → totals for the entire period
        daily_breakdown    → sales count + revenue per day
        payment_breakdown  → breakdown by payment method
        fbr_breakdown      → FBR submission status counts
    """
    from pos.models import Sale, SalePayment, SaleStatus, PaymentMethod
 
    company             = request.user.company
    date_from, date_to  = _parse_date_range(request)
    dt_from,   dt_to    = _make_datetime_range(date_from, date_to)
 
    sales_qs = Sale.objects.filter(
        company      = company,
        status       = SaleStatus.COMPLETED,
        completed_at__range = (dt_from, dt_to),
    )
 
    # Overall totals
    totals = sales_qs.aggregate(
        total_sales    = Count("id"),
        total_revenue  = Sum("total_amount"),
        total_subtotal = Sum("subtotal"),
        total_tax      = Sum("total_tax"),
        total_discount = Sum("total_discount"),
        avg_sale       = Avg("total_amount"),
    )
 
    # Daily breakdown
    daily = list(
        sales_qs
        .annotate(date=TruncDate("completed_at"))
        .values("date")
        .annotate(
            count   = Count("id"),
            revenue = Sum("total_amount"),
            tax     = Sum("total_tax"),
        )
        .order_by("date")
    )
    # Convert date objects to strings for JSON
    for row in daily:
        row["date"] = str(row["date"])
        row["revenue"] = float(row["revenue"] or 0)
        row["tax"]     = float(row["tax"]     or 0)
 
    # Payment method breakdown
    payments_qs = SalePayment.objects.filter(
        sale__company      = company,
        sale__status       = SaleStatus.COMPLETED,
        sale__completed_at__range = (dt_from, dt_to),
    )
    payment_breakdown = []
    for method in PaymentMethod.values:
        total = payments_qs.filter(
            payment_method=method
        ).aggregate(total=Sum("amount"))["total"] or 0
        payment_breakdown.append({
            "method": method,
            "total":  float(total),
        })
 
    # FBR status breakdown
    fbr_breakdown = list(
        sales_qs
        .values("fbr_submission_status")
        .annotate(count=Count("id"))
    )
 
    return Response({
        "from":               str(date_from),
        "to":                 str(date_to),
        "company":            company.business_name,
        "total_sales":        totals["total_sales"]    or 0,
        "total_revenue":      float(totals["total_revenue"]  or 0),
        "total_subtotal":     float(totals["total_subtotal"] or 0),
        "total_tax":          float(totals["total_tax"]      or 0),
        "total_discount":     float(totals["total_discount"] or 0),
        "average_sale":       float(totals["avg_sale"]       or 0),
        "daily_breakdown":    daily,
        "payment_breakdown":  payment_breakdown,
        "fbr_breakdown":      fbr_breakdown,
    })
 
 
@api_view(["GET"])
@permission_classes([IsActiveUser])
def top_products(request):
    """
    GET /api/reports/products/top/?from=&to=&limit=10
 
    Top selling products by quantity and revenue.
    Scoped to requesting user's company.
    """
    from pos.models import SaleLine, SaleStatus
 
    company            = request.user.company
    date_from, date_to = _parse_date_range(request)
    dt_from,   dt_to   = _make_datetime_range(date_from, date_to)
    limit              = int(request.query_params.get("limit", 10))
 
    top = list(
        SaleLine.objects
        .filter(
            sale__company      = company,
            sale__status       = SaleStatus.COMPLETED,
            sale__completed_at__range = (dt_from, dt_to),
        )
        .values("product", "product_name")
        .annotate(
            total_quantity = Sum("quantity"),
            total_revenue  = Sum("line_total"),
            total_tax      = Sum("sales_tax_applicable"),
            times_sold     = Count("sale", distinct=True),
        )
        .order_by("-total_quantity")[:limit]
    )
 
    # Convert decimals to float for JSON
    for row in top:
        row["total_quantity"] = float(row["total_quantity"] or 0)
        row["total_revenue"]  = float(row["total_revenue"]  or 0)
        row["total_tax"]      = float(row["total_tax"]      or 0)
 
    return Response({
        "from":     str(date_from),
        "to":       str(date_to),
        "company":  company.business_name,
        "limit":    limit,
        "products": top,
    })
 
 
@api_view(["GET"])
@permission_classes([IsActiveUser])
def inventory_report(request):
    """
    GET /api/reports/inventory/?low_stock_only=true
 
    Current stock levels for all products.
    Optionally filter to only show low stock items.
    Scoped to requesting user's company.
    """
    from pos.models import Product
 
    company        = request.user.company
    low_stock_only = request.query_params.get("low_stock_only", "false").lower() == "true"
 
    qs = Product.objects.filter(
        company      = company,
        is_active    = True,
        track_inventory = True,
    ).select_related("category").order_by("name")
 
    if low_stock_only:
        # Filter products where current_stock <= low_stock_threshold
        qs = qs.filter(
            current_stock__lte=F("low_stock_threshold"),
            low_stock_threshold__gt=0,
        )
 
    products = []
    for p in qs:
        products.append({
            "id":                  p.pk,
            "name":                p.name,
            "sku":                 p.sku,
            "barcode":             p.barcode,
            "category":            p.category.name if p.category else None,
            "current_stock":       float(p.current_stock),
            "low_stock_threshold": float(p.low_stock_threshold),
            "is_low_stock":        p.is_low_stock,
            "unit_of_measure":     p.unit_of_measure,
            "selling_price":       float(p.selling_price),
        })
 
    # Summary counts
    total_products   = qs.count()
    low_stock_count  = sum(1 for p in products if p["is_low_stock"])
    out_of_stock     = sum(1 for p in products if p["current_stock"] <= 0)
 
    return Response({
        "company":         company.business_name,
        "total_tracked":   total_products,
        "low_stock_count": low_stock_count,
        "out_of_stock":    out_of_stock,
        "low_stock_only":  low_stock_only,
        "products":        products,
    })
 
 
# ===========================================================================
# ADMIN REPORTS — platform admin only, all companies
# ===========================================================================
 
@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_all_invoices(request):
    """
    GET /api/reports/admin/invoices/?from=&to=&company=&fbr_status=&page=
 
    All invoices across ALL companies.
    Admin portal only.
 
    Filters:
        from        → completed_at from date
        to          → completed_at to date
        company     → filter by company ID
        fbr_status  → filter by FBR submission status
        page        → pagination (20 per page)
    """
    from pos.models import Sale, SaleStatus
 
    date_from, date_to = _parse_date_range(request)
    dt_from,   dt_to   = _make_datetime_range(date_from, date_to)
 
    qs = Sale.objects.filter(
        status       = SaleStatus.COMPLETED,
        completed_at__range = (dt_from, dt_to),
    ).select_related("company", "customer", "cashier").order_by("-completed_at")
 
    # Optional filters
    company_id = request.query_params.get("company")
    fbr_status = request.query_params.get("fbr_status")
 
    if company_id:
        qs = qs.filter(company_id=company_id)
    if fbr_status:
        qs = qs.filter(fbr_submission_status=fbr_status)
 
    # Pagination
    page      = int(request.query_params.get("page", 1))
    page_size = 20
    offset    = (page - 1) * page_size
    total     = qs.count()
    qs        = qs[offset:offset + page_size]
 
    invoices = []
    for sale in qs:
        invoices.append({
            "id":                    sale.pk,
            "sale_number":           sale.sale_number,
            "company_id":            sale.company_id,
            "company_name":          sale.company.business_name,
            "company_ntn":           sale.company.ntn,
            "customer_name":         sale.customer.name,
            "customer_ntn_cnic":     sale.customer.ntn_cnic,
            "cashier_email":         sale.cashier.email,
            "total_amount":          float(sale.total_amount),
            "total_tax":             float(sale.total_tax),
            "fbr_submission_status": sale.fbr_submission_status,
            "fbr_invoice_number":    sale.fbr_invoice_number,
            "fbr_scenario_id":       sale.fbr_scenario_id,
            "completed_at":          sale.completed_at.isoformat() if sale.completed_at else None,
        })
 
    # Platform-wide summary totals
    all_totals = Sale.objects.filter(
        status=SaleStatus.COMPLETED,
        completed_at__range=(dt_from, dt_to),
    ).aggregate(
        total_companies = Count("company", distinct=True),
        total_invoices  = Count("id"),
        total_revenue   = Sum("total_amount"),
        total_tax       = Sum("total_tax"),
    )
 
    return Response({
        "from":             str(date_from),
        "to":               str(date_to),
        "page":             page,
        "page_size":        page_size,
        "total_records":    total,
        "total_pages":      (total + page_size - 1) // page_size,
        "platform_summary": {
            "total_companies": all_totals["total_companies"] or 0,
            "total_invoices":  all_totals["total_invoices"]  or 0,
            "total_revenue":   float(all_totals["total_revenue"] or 0),
            "total_tax":       float(all_totals["total_tax"]     or 0),
        },
        "invoices": invoices,
    })
 
 
@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_user_activity(request):
    """
    GET /api/reports/admin/activity/?from=&to=&company=&user=&action=
 
    User activity log across all companies.
    Shows who did what and when.
 
    Since we don't have a dedicated ActivityLog model yet,
    this is built from Sale + CashSession + User data.
 
    Activity types tracked:
        - Sales created / completed / cancelled
        - Cash sessions opened / closed
        - Users created
        - Companies created / activated / deactivated
    """
    from pos.models import Sale, SaleStatus, CashSession, CashSessionStatus
    from users.models import User
 
    date_from, date_to = _parse_date_range(request)
    dt_from,   dt_to   = _make_datetime_range(date_from, date_to)
 
    company_id = request.query_params.get("company")
    user_id    = request.query_params.get("user")
 
    activity = []
 
    # ── Sales activity ────────────────────────────────────────────────
    sales_qs = Sale.objects.filter(
        created_at__range=(dt_from, dt_to),
    ).select_related("company", "cashier", "customer")
 
    if company_id:
        sales_qs = sales_qs.filter(company_id=company_id)
    if user_id:
        sales_qs = sales_qs.filter(cashier_id=user_id)
 
    for sale in sales_qs.order_by("-created_at")[:100]:
        activity.append({
            "timestamp":    sale.created_at.isoformat(),
            "action":       f"Sale {sale.get_status_display()}",
            "user_email":   sale.cashier.email,
            "user_role":    sale.cashier.role,
            "company":      sale.company.business_name,
            "detail":       (
                f"{sale.sale_number} — "
                f"Rs. {sale.total_amount} — "
                f"Customer: {sale.customer.name}"
            ),
            "entity_type":  "sale",
            "entity_id":    sale.pk,
        })
 
    # ── Cash session activity ─────────────────────────────────────────
    sessions_qs = CashSession.objects.filter(
        opened_at__range=(dt_from, dt_to),
    ).select_related("company", "cashier")
 
    if company_id:
        sessions_qs = sessions_qs.filter(company_id=company_id)
    if user_id:
        sessions_qs = sessions_qs.filter(cashier_id=user_id)
 
    for session in sessions_qs.order_by("-opened_at")[:50]:
        activity.append({
            "timestamp":   session.opened_at.isoformat(),
            "action":      "Cash Session Opened",
            "user_email":  session.cashier.email,
            "user_role":   session.cashier.role,
            "company":     session.company.business_name,
            "detail":      f"Opening balance: Rs. {session.opening_balance}",
            "entity_type": "cash_session",
            "entity_id":   session.pk,
        })
        if session.closed_at:
            activity.append({
                "timestamp":   session.closed_at.isoformat(),
                "action":      "Cash Session Closed",
                "user_email":  session.cashier.email,
                "user_role":   session.cashier.role,
                "company":     session.company.business_name,
                "detail":      (
                    f"Closing balance: Rs. {session.closing_balance} | "
                    f"Difference: Rs. {session.cash_difference}"
                ),
                "entity_type": "cash_session",
                "entity_id":   session.pk,
            })
 
    # ── User creation activity ────────────────────────────────────────
    users_qs = User.objects.filter(
        date_joined__range=(dt_from, dt_to),
    ).select_related("company", "created_by")
 
    if company_id:
        users_qs = users_qs.filter(company_id=company_id)
    if user_id:
        users_qs = users_qs.filter(created_by_id=user_id)
 
    for user in users_qs.order_by("-date_joined")[:50]:
        activity.append({
            "timestamp":   user.date_joined.isoformat(),
            "action":      "User Created",
            "user_email":  user.created_by.email if user.created_by else "System",
            "user_role":   user.created_by.role  if user.created_by else "system",
            "company":     user.company.business_name if user.company else "Platform",
            "detail":      f"New {user.get_role_display()}: {user.email}",
            "entity_type": "user",
            "entity_id":   user.pk,
        })
 
    # Sort all activity by timestamp descending
    activity.sort(key=lambda x: x["timestamp"], reverse=True)
 
    return Response({
        "from":          str(date_from),
        "to":            str(date_to),
        "total_events":  len(activity),
        "activity":      activity[:200],   # cap at 200 events per request
    })


from django.utils.dateparse import parse_date
from django.utils import timezone
from datetime import date as date_type
 
 
def _parse_export_params(request):
    """Parse common export parameters from request."""
    today     = timezone.now().date()
    date_from = parse_date(
        request.query_params.get("from", str(today))
    ) or today
    date_to   = parse_date(
        request.query_params.get("to", str(today))
    ) or today
    fmt       = request.query_params.get("format", "excel").lower()
    return date_from, date_to, fmt
 
 
@api_view(["GET"])
@permission_classes([IsActiveUser])
def export_daily_sales(request):
    """
    GET /api/reports/export/daily-sales/?from=&to=&format=excel|pdf
 
    Exports daily sales summary.
    Returns S3 URL of generated file.
    """
    from reports.exporters import DailySalesExporter
    date_from, date_to, fmt = _parse_export_params(request)
    exporter = DailySalesExporter(request.user.company, date_from, date_to)
 
    url = exporter.export_excel() if fmt == "excel" else exporter.export_pdf()
    return Response({"url": url, "format": fmt, "type": "daily_sales"})
 
 
@api_view(["GET"])
@permission_classes([IsActiveUser])
def export_monthly_sales(request):
    """
    GET /api/reports/export/monthly-sales/?year=2025&format=excel|pdf
    """
    from reports.exporters import MonthlySalesExporter
    year     = int(request.query_params.get("year", timezone.now().year))
    fmt      = request.query_params.get("format", "excel").lower()
    exporter = MonthlySalesExporter(request.user.company, year)
 
    url = exporter.export_excel() if fmt == "excel" else exporter.export_pdf()
    return Response({"url": url, "format": fmt, "type": "monthly_sales",
                     "year": year})
 
 
@api_view(["GET"])
@permission_classes([IsActiveUser])
def export_product_sales(request):
    """
    GET /api/reports/export/product-sales/?from=&to=&format=excel|pdf&limit=100
    """
    from reports.exporters import ProductSalesExporter
    date_from, date_to, fmt = _parse_export_params(request)
    limit    = int(request.query_params.get("limit", 100))
    exporter = ProductSalesExporter(
        request.user.company, date_from, date_to, limit
    )
 
    url = exporter.export_excel() if fmt == "excel" else exporter.export_pdf()
    return Response({"url": url, "format": fmt, "type": "product_sales"})
 
 
@api_view(["GET"])
@permission_classes([IsActiveUser])
def export_cashier_sales(request):
    """
    GET /api/reports/export/cashier-sales/?from=&to=&format=excel|pdf
    """
    from reports.exporters import CashierSalesExporter
    date_from, date_to, fmt = _parse_export_params(request)
    exporter = CashierSalesExporter(
        request.user.company, date_from, date_to
    )
 
    url = exporter.export_excel() if fmt == "excel" else exporter.export_pdf()
    return Response({"url": url, "format": fmt, "type": "cashier_sales"})
 
 
@api_view(["GET"])
@permission_classes([IsActiveUser])
def export_fbr_status(request):
    """
    GET /api/reports/export/fbr-status/?from=&to=&format=excel|pdf
    """
    from reports.exporters import FBRStatusExporter
    date_from, date_to, fmt = _parse_export_params(request)
    exporter = FBRStatusExporter(
        request.user.company, date_from, date_to
    )
 
    url = exporter.export_excel() if fmt == "excel" else exporter.export_pdf()
    return Response({"url": url, "format": fmt, "type": "fbr_status"})