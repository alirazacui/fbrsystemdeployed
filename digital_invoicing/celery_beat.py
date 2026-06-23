"""
========================================================
WIRE-UP INSTRUCTIONS
========================================================
 
1. Create the digital_invoicing app:
   python manage.py startapp digital_invoicing
 
2. Create these files inside digital_invoicing/:
   - fbr_client.py      ← FBRClient class (Section 1 above)
   - invoice_builder.py ← FBRInvoiceBuilder class (Section 2 above)
   - tasks.py           ← Celery tasks (Section 3 above)
   - __init__.py        ← empty
 
3. Add to INSTALLED_APPS in settings.py:
   "digital_invoicing",
 
4. Add CELERY_BEAT_SCHEDULE to settings.py (from Section 4 above)
 
5. Install Celery Beat:
   pip install celery[redis] django-celery-beat
   pip freeze > requirements.txt
 
6. Add django_celery_beat to INSTALLED_APPS:
   "django_celery_beat",
 
7. Run migrations:
   python manage.py migrate
 
8. Wire up the task trigger in SaleViewSet.complete()
   Replace the comment "# Actual submission happens in Phase 3" with:
 
   from digital_invoicing.tasks import submit_invoice_to_fbr
   if sale.company.module_fbr_di:
       submit_invoice_to_fbr.delay(sale.id)
 
9. Start Celery worker (new terminal):
   celery -A config worker --loglevel=info
 
10. Start Celery Beat (another new terminal):
    celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
"""
 