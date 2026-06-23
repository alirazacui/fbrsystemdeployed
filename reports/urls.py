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
]
 