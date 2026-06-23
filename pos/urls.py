from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet,
    ProductViewSet,
    CustomerViewSet,
    CashSessionViewSet,
    SaleViewSet,
)
from .views import SaleReturnViewSet

router = DefaultRouter()
router.register(r"categories",    CategoryViewSet,    basename="category")
router.register(r"products",      ProductViewSet,     basename="product")
router.register(r"customers",     CustomerViewSet,    basename="customer")
router.register(r"cash-sessions", CashSessionViewSet, basename="cash-session")
router.register(r"sales",         SaleViewSet,        basename="sale")
router.register(r"returns", SaleReturnViewSet, basename="return")
 
urlpatterns = [
    path("", include(router.urls)),
]