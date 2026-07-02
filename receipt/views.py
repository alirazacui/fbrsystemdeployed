from django.shortcuts import render

# Create your views here.
"""
========================================================
receipts/views.py
========================================================
"""
 
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status as http_status
from django.http import HttpResponse
from common.permissions import IsActiveUser
from .generators import *
 
@api_view(["GET"])
@permission_classes([IsActiveUser])
def get_thermal_receipt(request, sale_id):
    """
    GET /api/receipts/{sale_id}/thermal/
 
    Returns URL of thermal receipt PDF.
    Generates if not already generated.
    """
    from pos.models import Sale, SaleStatus
    try:
        sale = Sale.objects.get(
            pk      = sale_id,
            company = request.user.company,
        )
    except Sale.DoesNotExist:
        return Response(
            {"error": "Sale not found or not completed."},
            status=http_status.HTTP_404_NOT_FOUND,
        )
 
    try:
        generator = ThermalReceiptGenerator(sale)
        url       = generator.generate()
        return Response({"url": url, "type": "thermal"})
    except Exception as e:
        logger.error(f"Thermal receipt generation failed for sale {sale_id}: {e}")
        return Response(
            {"error": f"Receipt generation failed: {str(e)}"},
            status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
 
 
@api_view(["GET"])
@permission_classes([IsActiveUser])
def get_a4_invoice(request, sale_id):
    """
    GET /api/receipts/{sale_id}/a4/
 
    Returns URL of A4 invoice PDF.
    """
    from pos.models import Sale, SaleStatus
    try:
        sale = Sale.objects.get(
            pk      = sale_id,
            company = request.user.company,
        )
    except Sale.DoesNotExist:
        return Response(
            {"error": "Sale not found or not completed."},
            status=http_status.HTTP_404_NOT_FOUND,
        )
 
    try:
        generator = A4InvoiceGenerator(sale)
        generator._build_pdf()
        generator.buffer.seek(0)
        response = HttpResponse(generator.buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="invoice_{sale.sale_number or sale.id}.pdf"'
        return response
    except Exception as e:
        logger.error(f"A4 invoice generation failed for sale {sale_id}: {e}")
        return Response(
            {"error": f"Invoice generation failed: {str(e)}"},
            status=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )