from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.db import models
from .models import FBRSubmissionLog
from common.permissions import IsAdmin

class FBRSubmissionAdminViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsAdmin]

    def list(self, request):
        qs = FBRSubmissionLog.objects.select_related('company').order_by('-created_at')
        
        # Optional search by local_invoice_id, company name, fbr_invoice_id
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                models.Q(local_invoice_id__icontains=search) |
                models.Q(fbr_invoice_id__icontains=search) |
                models.Q(company__business_name__icontains=search)
            )

        # Basic pagination if needed
        limit = int(request.query_params.get("limit", 100))
        offset = int(request.query_params.get("offset", 0))
        total = qs.count()
        qs = qs[offset:offset+limit]

        results = []
        for log in qs:
            results.append({
                "id": log.id,
                "created_at": log.created_at.strftime("%B %d, %Y, %I:%M %p"),
                "company_name": log.company.business_name,
                "local_invoice_id": log.local_invoice_id or "-",
                "fbr_invoice_id": log.fbr_invoice_id or "-",
                "endpoint": log.endpoint,
                "environment": log.environment,
                "status_code": log.status_code or "-",
                "http_status": log.http_status or "-",
                "attempt": log.attempt,
                "latency_ms": log.latency_ms or 0,
                "sale_id": log.sale_id
            })
            
        return Response({"count": total, "results": results})

    def retrieve(self, request, pk=None):
        try:
            log = FBRSubmissionLog.objects.select_related('company').get(pk=pk)
        except FBRSubmissionLog.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        return Response({
            "id": log.id,
            "created_at": log.created_at.strftime("%B %d, %Y, %I:%M %p"),
            "company_name": log.company.business_name,
            "local_invoice_id": log.local_invoice_id or "-",
            "fbr_invoice_id": log.fbr_invoice_id or "-",
            "endpoint": log.endpoint,
            "environment": log.environment,
            "status_code": log.status_code or "-",
            "http_status": log.http_status or "-",
            "attempt": log.attempt,
            "latency_ms": log.latency_ms or 0,
            "error_message": log.error_message or "-",
            "request_payload": log.request_payload,
            "response_payload": log.response_payload,
            "sale_id": log.sale_id
        })
