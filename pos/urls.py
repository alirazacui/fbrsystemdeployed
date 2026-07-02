from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *
from .views import SaleReturnViewSet
from .reports_views import ReportsViewSet

router = DefaultRouter()
router.register(r"categories",    CategoryViewSet,    basename="category")
router.register(r"products",      ProductViewSet,     basename="product")
router.register(r"customers",     CustomerViewSet,    basename="customer")
router.register(r"cash-sessions", CashSessionViewSet, basename="cash-session")
router.register(r"sales",         SaleViewSet,        basename="sale")
router.register(r"returns", SaleReturnViewSet, basename="return")
router.register(r"debit-notes", DebitNoteViewSet, basename="debit-note")
router.register(r"hs-codes", HSCodeViewSet, basename="hs-code")
router.register(r"reports", ReportsViewSet, basename="report")

urlpatterns = [
    path("dashboard/", DashboardStatsView.as_view(), name="dashboard-stats"),
    path("", include(router.urls)),
]