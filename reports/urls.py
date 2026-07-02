from django.urls import path
from . import views
 
urlpatterns = [
    # ── POS reports (company-scoped) ──────────────────────────────────
    path("reports/sales/today/",    views.sales_today,       name="sales-today"),
    path("reports/sales/",          views.sales_range,        name="sales-range"),
    path("reports/products/top/",   views.top_products,       name="top-products"),
    path("reports/inventory/",      views.inventory_report,   name="inventory-report"),
 
    # ── Admin reports (platform admin only) ───────────────────────────
    path("reports/admin/invoices/", views.admin_all_invoices, name="admin-invoices"),
    path("reports/admin/activity/", views.admin_user_activity,name="admin-activity"),
     path("reports/export/daily-sales/",   views.export_daily_sales,   name="export-daily"),
    path("reports/export/monthly-sales/", views.export_monthly_sales, name="export-monthly"),
    path("reports/export/product-sales/", views.export_product_sales, name="export-products"),
    path("reports/export/cashier-sales/", views.export_cashier_sales, name="export-cashiers"),
    path("reports/export/fbr-status/",    views.export_fbr_status,    name="export-fbr"),
]
 