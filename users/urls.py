from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView
from .views import AdminStaffViewSet, OwnerViewSet, CompanyUserViewSet, MeViewSet, AllUsersViewSet
from .serializers import CustomTokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
 
 
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # Login successful
            from django.contrib.auth import get_user_model
            from companies.models import AuditLog
            User = get_user_model()
            email = request.data.get("email", "")
            try:
                user = User.objects.get(email=email)
                if user.company:
                    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')).split(',')[0]
                    AuditLog.objects.create(
                        company=user.company,
                        user_email=user.email,
                        entity_type="auth",
                        entity_id=str(user.pk),
                        action="login",
                        ip_address=ip
                    )
            except User.DoesNotExist:
                pass
        return response

from rest_framework.permissions import IsAuthenticated
class CustomTokenBlacklistView(TokenBlacklistView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and request.user.is_authenticated and request.user.company:
            from companies.models import AuditLog
            ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')).split(',')[0]
            AuditLog.objects.create(
                company=request.user.company,
                user_email=request.user.email,
                entity_type="auth",
                entity_id=str(request.user.pk),
                action="logout",
                ip_address=ip
            )
        return response
 
 
router = DefaultRouter()
router.register(r"users",          AllUsersViewSet,    basename="user")
router.register(r"admin-users",    AdminStaffViewSet,  basename="admin-user")
router.register(r"owners",         OwnerViewSet,       basename="owner")
router.register(r"company-users",  CompanyUserViewSet, basename="company-user")
router.register(r"me",             MeViewSet,          basename="me")
 
urlpatterns = [
    # JWT endpoints
    path("auth/login/",   CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", TokenRefreshView.as_view(),          name="token_refresh"),
    path("auth/logout/",  CustomTokenBlacklistView.as_view(),        name="token_blacklist"),
 
    # User management endpoints
    path("", include(router.urls)),
]
 
