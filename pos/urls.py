from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet,
    ProductViewSet,
    CustomerViewSet,
    CashSessionViewSet,
    SaleViewSet,
)
 
router = DefaultRouter()
router.register(r"categories",    CategoryViewSet,    basename="category")
router.register(r"products",      ProductViewSet,     basename="product")
router.register(r"customers",     CustomerViewSet,    basename="customer")
router.register(r"cash-sessions", CashSessionViewSet, basename="cash-session")
router.register(r"sales",         SaleViewSet,        basename="sale")
 
urlpatterns = [
    path("", include(router.urls)),
]