from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView
from .views import AdminStaffViewSet, OwnerViewSet, CompanyUserViewSet, MeViewSet
from .serializers import CustomTokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
 
 
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
 
 
router = DefaultRouter()
router.register(r"admin-users",    AdminStaffViewSet,  basename="admin-user")
router.register(r"owners",         OwnerViewSet,       basename="owner")
router.register(r"company-users",  CompanyUserViewSet, basename="company-user")
router.register(r"me",             MeViewSet,          basename="me")
 
urlpatterns = [
    # JWT endpoints
    path("auth/login/",   CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", TokenRefreshView.as_view(),          name="token_refresh"),
    path("auth/logout/",  TokenBlacklistView.as_view(),        name="token_blacklist"),
 
    # User management endpoints
    path("", include(router.urls)),
]
 
