from django.shortcuts import render

# Create your views here.
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
 
from common.permissions import IsAdmin, IsOwnerOrAdmin, IsAdminOrAdminStaff
from users.models import User
from .models import Permission, UserPermission
from .serializers import (
    AssignPermissionsSerializer,
    CompanyPermissionPanelSerializer,
    PermissionSerializer,
    UserPermissionSerializer,
)
 
 
class PermissionCatalogueViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    """
    Read-only catalogue of all permissions.
    Admin and Admin Staff can view this.
 
    list     GET /api/permissions/
    retrieve GET /api/permissions/{id}/
    """
    queryset           = Permission.objects.filter(is_active=True).order_by("module", "action")
    serializer_class   = PermissionSerializer
    permission_classes = [IsAdminOrAdminStaff]
 
 
class UserPermissionViewSet(GenericViewSet):
    """
    Manage permission assignments for a specific user.
 
    panel   GET  /api/user-permissions/{user_id}/panel/
            → Returns the full checkbox grid for this user,
              filtered to their company's enabled modules.
 
    assign  POST /api/user-permissions/{user_id}/assign/
            → Replaces this user's permissions with the submitted list.
              Body: {"permission_ids": [1, 3, 7]}
 
    list    GET  /api/user-permissions/{user_id}/list/
            → Raw list of UserPermission rows for this user.
    """
    permission_classes = [IsOwnerOrAdmin]
 
    def _get_target_user(self, user_id):
        """
        Fetch the target user, enforcing that:
        - Admin can manage any user
        - Owner can only manage users in their own company
        """
        try:
            target = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("User not found.")
 
        requesting_user = self.request.user
        if not requesting_user.is_platform_admin:
            # Owner can only touch users in their own company
            if target.company_id != requesting_user.company_id:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("You can only manage users in your own company.")
            # Owner cannot manage another owner or platform users
            if target.role in (User.Role.ADMIN, User.Role.ADMIN_STAFF, User.Role.OWNER):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("You cannot manage permissions for this user.")
 
        return target
 
    @action(detail=False, methods=["get"], url_path=r"(?P<user_id>\d+)/panel")
    def panel(self, request, user_id=None):
        """GET /api/user-permissions/{user_id}/panel/"""
        target     = self._get_target_user(user_id)
        serializer = CompanyPermissionPanelSerializer()
        data       = serializer.to_representation(target)
        return Response(data)
 
    @action(detail=False, methods=["post"], url_path=r"(?P<user_id>\d+)/assign")
    def assign(self, request, user_id=None):
        """POST /api/user-permissions/{user_id}/assign/"""
        target     = self._get_target_user(user_id)
        serializer = AssignPermissionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=target, granted_by=request.user)
        return Response({"detail": f"Permissions updated for {target.email}."})
 
    @action(detail=False, methods=["get"], url_path=r"(?P<user_id>\d+)/list")
    def list_permissions(self, request, user_id=None):
        """GET /api/user-permissions/{user_id}/list/"""
        target = self._get_target_user(user_id)
        qs     = UserPermission.objects.filter(user=target).select_related(
            "permission", "granted_by"
        )
        serializer = UserPermissionSerializer(qs, many=True)
        return Response(serializer.data)