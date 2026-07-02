from django.shortcuts import render

# Create your views here.
"""
========================================================
companies/views.py
========================================================
"""
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.permissions import BasePermission
 
from common.permissions import IsAdmin, IsAdminOrAdminStaff, IsOwnerOrAdmin
from .models import Company
from .serializers import (
    CompanyDetailSerializer,
    CompanyListSerializer,
    CompanyModulesSerializer,
    CompanyPaymentMethodSettingsSerializer,
)


class IsCompanyOwnerOrAdmin(BasePermission):
    """
    Checks that the user is the owner of the specific company object being accessed,
    or is a platform admin.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.is_platform_admin:
            return True
        return (
            request.user.role == "owner"
            and request.user.status == "active"
            and obj.id == request.user.company_id
        )
 
 
class CompanyViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
    # No DestroyModelMixin — companies are never hard-deleted
):
    """
    Admin-only for list/create, Owner or Admin for retrieve/update.
  
    list    GET  /api/companies/
    create  POST /api/companies/
    retrieve GET /api/companies/{id}/
    update  PUT  /api/companies/{id}/
    partial_update PATCH /api/companies/{id}/
    modules PATCH /api/companies/{id}/modules/   ← toggle feature modules
    activate POST /api/companies/{id}/activate/
    deactivate POST /api/companies/{id}/deactivate/
    """
    queryset         = Company.objects.all().order_by("-created_at")
 
    def get_permissions(self):
        if self.action in ["retrieve", "update", "partial_update"]:
            return [IsCompanyOwnerOrAdmin()]
        return [IsAdmin()]
 
    def get_serializer_class(self):
        if self.action == "list":
            return CompanyListSerializer
        if self.action == "modules":
            return CompanyModulesSerializer
        return CompanyDetailSerializer
 
    # ── Custom actions ─────────────────────────────────────────────────
 
    @action(detail=True, methods=["patch"], url_path="modules")
    def modules(self, request, pk=None):
        """PATCH /api/companies/{id}/modules/ — toggle feature modules."""
        company    = self.get_object()
        serializer = CompanyModulesSerializer(company, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
 
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        """POST /api/companies/{id}/activate/"""
        company           = self.get_object()
        company.is_active = True
        company.save(update_fields=["is_active", "updated_at"])
        return Response({"detail": f"'{company.business_name}' has been activated."})
 
    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        """POST /api/companies/{id}/deactivate/"""
        company           = self.get_object()
        company.is_active = False
        company.save(update_fields=["is_active", "updated_at"])
        return Response({"detail": f"'{company.business_name}' has been deactivated."})

    @action(detail=True, methods=["get", "patch"], url_path="payment-settings")
    def payment_settings(self, request, pk=None):
        """GET or PATCH /api/companies/{id}/payment-settings/"""
        company = self.get_object()
        from pos.models import CompanyPaymentMethodSettings
        settings_obj, created = CompanyPaymentMethodSettings.objects.get_or_create(company=company)
        
        if request.method == "GET":
            serializer = CompanyPaymentMethodSettingsSerializer(settings_obj, context={"request": request})
            return Response(serializer.data)
            
        elif request.method == "PATCH":
            serializer = CompanyPaymentMethodSettingsSerializer(
                settings_obj, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
