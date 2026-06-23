from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PermissionCatalogueViewSet, UserPermissionViewSet
 
router = DefaultRouter()
router.register(r"permissions",      PermissionCatalogueViewSet, basename="permission")
router.register(r"user-permissions", UserPermissionViewSet,      basename="user-permission")
 
urlpatterns = [
    path("", include(router.urls)),
]