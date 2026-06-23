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
 
from common.permissions import IsAdmin, IsAdminOrAdminStaff
from .models import Company
from .serializers import (
    CompanyDetailSerializer,
    CompanyListSerializer,
    CompanyModulesSerializer,
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
    Admin-only. Manages all client company records.
 
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
    permission_classes = [IsAdmin]
 
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
