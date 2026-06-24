"""
========================================================
receipts/urls.py
========================================================
"""
from django.urls import path
from . import views
 
urlpatterns = [
    path(
        "receipts/<int:sale_id>/thermal/",
        views.get_thermal_receipt,
        name="thermal-receipt",
    ),
    path(
        "receipts/<int:sale_id>/a4/",
        views.get_a4_invoice,
        name="a4-invoice",
    ),
]
