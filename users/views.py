from django.shortcuts import render

# Create your views here.
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
 
from common.permissions import (
    IsAdmin,
    IsAdminOrAdminStaff,
    IsOwner,
    IsOwnerOrAdmin,
    IsActiveUser,
)
from .models import User, UserStatus
from .serializers import (
    ChangePasswordSerializer,
    CreateAdminStaffSerializer,
    CreateClientUserSerializer,
    CreateOwnerSerializer,
    UpdateUserStatusSerializer,
    UserDetailSerializer,
    UserListSerializer,
)
 
 
class AdminStaffViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    """
    Platform Admin manages Admin Staff users.
 
    list     GET  /api/admin-users/
    create   POST /api/admin-users/
    retrieve GET  /api/admin-users/{id}/
    update   PUT  /api/admin-users/{id}/
    status   PATCH /api/admin-users/{id}/status/
    """
    permission_classes = [IsAdmin]
 
    def get_queryset(self):
        return User.objects.filter(
            role__in=[User.Role.ADMIN, User.Role.ADMIN_STAFF]
        ).order_by("-date_joined")
 
    def get_serializer_class(self):
        if self.action == "create":
            return CreateAdminStaffSerializer
        if self.action == "status":
            return UpdateUserStatusSerializer
        if self.action == "list":
            return UserListSerializer
        return UserDetailSerializer
 
    @action(detail=True, methods=["patch"], url_path="status")
    def status(self, request, pk=None):
        """PATCH /api/admin-users/{id}/status/"""
        user       = self.get_object()
        serializer = UpdateUserStatusSerializer(
            user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserDetailSerializer(user).data)
 
 
class OwnerViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    """
    Platform Admin creates and manages Owner users.
    On creation, signal auto-grants all company-module permissions.
 
    list     GET  /api/owners/
    create   POST /api/owners/
    retrieve GET  /api/owners/{id}/
    status   PATCH /api/owners/{id}/status/
    """
    permission_classes = [IsAdmin]
 
    def get_queryset(self):
        return User.objects.filter(role=User.Role.OWNER).order_by("-date_joined")
 
    def get_serializer_class(self):
        if self.action == "create":
            return CreateOwnerSerializer
        if self.action == "status":
            return UpdateUserStatusSerializer
        if self.action == "list":
            return UserListSerializer
        return UserDetailSerializer
 
    @action(detail=True, methods=["patch"], url_path="status")
    def status(self, request, pk=None):
        """PATCH /api/owners/{id}/status/"""
        user       = self.get_object()
        serializer = UpdateUserStatusSerializer(
            user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserDetailSerializer(user).data)
 
 
class CompanyUserViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    """
    Owner manages their own company's users (Manager, Cashier, Salesperson).
    All queries are automatically scoped to the requesting owner's company.
 
    list     GET  /api/company-users/
    create   POST /api/company-users/
    retrieve GET  /api/company-users/{id}/
    status   PATCH /api/company-users/{id}/status/
    """
    permission_classes = [IsOwner]
 
    def get_queryset(self):
        return User.objects.filter(
            company  = self.request.user.company,
            role__in = [
                User.Role.MANAGER,
                User.Role.CASHIER,
                User.Role.SALESPERSON,
            ],
        ).order_by("-date_joined")
 
    def get_serializer_class(self):
        if self.action == "create":
            return CreateClientUserSerializer
        if self.action == "status":
            return UpdateUserStatusSerializer
        if self.action == "list":
            return UserListSerializer
        return UserDetailSerializer
    def perform_create(self, serializer):
        """Check subscription user limit before creating staff user."""
        sub = getattr(self.request, "subscription", None)
        if sub:
            can_add, reason = sub.check_user_limit()
            if not can_add:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied(detail=reason)
        serializer.save()
 
    @action(detail=True, methods=["patch"], url_path="status")
    def status(self, request, pk=None):
        """PATCH /api/company-users/{id}/status/"""
        user = self.get_object()
        serializer = UpdateUserStatusSerializer(
            user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserDetailSerializer(user).data)
 
 
class MeViewSet(GenericViewSet):
    """
    Current authenticated user — profile and password.
 
    me          GET   /api/me/
    update_me   PATCH /api/me/update/
    password    POST  /api/me/password/
    """
    permission_classes = [IsActiveUser]
 
    def get_object(self):
        return self.request.user
 
    @action(detail=False, methods=["get"], url_path="")
    def me(self, request):
        """GET /api/me/"""
        serializer = UserDetailSerializer(request.user)
        return Response(serializer.data)
 
    @action(detail=False, methods=["patch"], url_path="update")
    def update_me(self, request):
        """PATCH /api/me/update/"""
        serializer = UserDetailSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
 
    @action(detail=False, methods=["post"], url_path="password")
    def password(self, request):
        """POST /api/me/password/"""
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated successfully."})