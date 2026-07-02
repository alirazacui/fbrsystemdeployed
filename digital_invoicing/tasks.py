"""
========================================================
digital_invoicing/tasks.py
 
Celery Tasks for FBR Invoice Submission
========================================================
"""
 
import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from . import scenario_tasks

logger = logging.getLogger(__name__)
 
 
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,    # retry after 60 seconds
    name="digital_invoicing.submit_invoice_to_fbr",
)
def submit_invoice_to_fbr(self, sale_id: int):
    """
    Background Celery task — submits a completed sale to FBR.
 
    Called automatically when a sale is completed via SaleViewSet.complete().
    Retries up to 3 times on network failure (per PRAL manual section 4.2).
 
    Args:
        sale_id: Primary key of the Sale to submit
 
    Flow:
        1. Load Sale + Company from DB
        2. Get correct FBR token (sandbox or production)
        3. Build invoice JSON using FBRInvoiceBuilder
        4. POST to FBR via FBRClient
        5. Store fbr_invoice_number + qr_code on Sale
        6. Mark fbr_submission_status = SUCCESS
        On failure:
        7. Store error_code + error_message on Sale
        8. Mark fbr_submission_status = FAILED
        9. Retry up to 3 times on network errors
    """
    from pos.models import Sale, FBRSubmissionStatus
    from .fbr_client import FBRClient, FBRAPIError
    from .invoice_builder import FBRInvoiceBuilder
    from django.utils import timezone
 
    logger.info(f"[FBR Task] Starting submission for Sale ID: {sale_id}")
 
    # ── Load Sale ────────────────────────────────────────────────────
    try:
        sale = Sale.objects.select_related(
            "company", "customer", "original_sale"
        ).prefetch_related("lines").get(pk=sale_id)
    except Sale.DoesNotExist:
        logger.error(f"[FBR Task] Sale {sale_id} not found")
        return
 
    # ── Guard: only submit COMPLETED sales ───────────────────────────
    from pos.models import SaleStatus
    if sale.status != SaleStatus.COMPLETED:
        logger.warning(f"[FBR Task] Sale {sale_id} is not COMPLETED — skipping")
        return
 
    # ── Guard: FBR DI module must be enabled ─────────────────────────
    if not sale.company.module_fbr_di:
        sale.fbr_submission_status = FBRSubmissionStatus.SKIPPED
        sale.save(update_fields=["fbr_submission_status", "updated_at"])
        logger.info(f"[FBR Task] FBR DI not enabled for company — skipping")
        return
 
    # ── Get correct token ────────────────────────────────────────────
    company = sale.company
    is_sandbox = True
    
    if company.fbr_production_token:
        is_sandbox = False
        token = company.fbr_production_token
    elif company.fbr_sandbox_token:
        is_sandbox = True
        token = company.fbr_sandbox_token
    else:
        token = None
 
    if not token:
        error_msg = "No Sandbox or Production token configured."
        logger.error(f"[FBR Task] {error_msg} for company {company.business_name}")
        sale.fbr_submission_status = FBRSubmissionStatus.FAILED
        sale.fbr_error_code        = "NO_TOKEN"
        sale.fbr_error_message     = error_msg
        sale.save(update_fields=[
            "fbr_submission_status", "fbr_error_code",
            "fbr_error_message", "updated_at"
        ])
        return
 
    # ── Build invoice JSON ───────────────────────────────────────────
    try:
        builder = FBRInvoiceBuilder(sale)
        payload = builder.build()
        
        # FBR explicitly requests scenarioId be omitted for live invoices
        if not is_sandbox and "scenarioId" in payload:
            del payload["scenarioId"]
            
        # Print to terminal
        import json
        import json
        print("\n" + "="*50)
        print(f"FBR FINAL SUBMIT TRIGGERED ({'SANDBOX' if is_sandbox else 'PRODUCTION'})")
        print(f"Token: {token}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        print("="*50 + "\n")
        
        logger.debug(f"[FBR Task] Invoice payload built: {payload}")
    except Exception as e:
        logger.error(f"[FBR Task] Failed to build invoice JSON: {e}")
        sale.fbr_submission_status = FBRSubmissionStatus.FAILED
        sale.fbr_error_code        = "BLD_ERR"
        sale.fbr_error_message     = str(e)
        sale.save(update_fields=[
            "fbr_submission_status", "fbr_error_code",
            "fbr_error_message", "updated_at"
        ])
        return
 
    # ── Submit to FBR ────────────────────────────────────────────────
    base_url = company.fbr_sandbox_endpoint if is_sandbox else company.fbr_production_endpoint
    client = FBRClient(token=token, base_url=base_url, is_sandbox=is_sandbox)
 
    import time
    from .models import FBRSubmissionLog
    start_time = time.time()
    
    status_code = None
    http_status = None
    error_message_log = ""
    fbr_invoice_number_log = ""
    raw_response_log = {}
    
    try:
        result = client.submit_invoice(payload)
        latency_ms = int((time.time() - start_time) * 1000)
        http_status = 200
        status_code = "00"
        fbr_invoice_number_log = result.get("fbr_invoice_number", "")
        raw_response_log = result.get("raw_response", {})

        # ── SUCCESS ──────────────────────────────────────────────────
        sale.fbr_submission_status = FBRSubmissionStatus.SUCCESS
        sale.fbr_invoice_number    = result["fbr_invoice_number"]
        # FBR sandbox sometimes returns an empty QR code. Fallback to the invoice number so the user can test the QR feature.
        sale.fbr_qr_code           = result["qr_code"] or result["fbr_invoice_number"]
        sale.fbr_scenario_id       = payload.get("scenarioId", "")
        sale.fbr_submitted_at      = timezone.now()
        sale.fbr_error_code        = ""
        sale.fbr_error_message     = ""
        sale.save(update_fields=[
            "fbr_submission_status",
            "fbr_invoice_number",
            "fbr_qr_code",
            "fbr_scenario_id",
            "fbr_submitted_at",
            "fbr_error_code",
            "fbr_error_message",
            "updated_at",
        ])
        
        from companies.models import AuditLog
        AuditLog.objects.create(
            company=company,
            user_email="system@fbr-worker",
            entity_type="fbr_submission",
            entity_id=str(sale.pk),
            action="submit",
            ip_address="127.0.0.1"
        )
        
        # ── Decrement Stock ONLY on Production FBR Success ──
        if not is_sandbox:
            from django.db import transaction
            with transaction.atomic():
                for line in sale.lines.select_related("product").all():
                    product = line.product
                    if product.track_inventory:
                        product.refresh_from_db()
                        product.current_stock = (
                            float(product.current_stock) - float(line.quantity)
                        )
                        product.save(update_fields=["current_stock", "updated_at"])
                        
        logger.info(
            f"[FBR Task] ✓ Sale {sale_id} submitted. "
            f"FBR Invoice: {result['fbr_invoice_number']}"
        )
 
    except ConnectionError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_message_log = str(e)
        # Network error — retry per PRAL manual section 4.2
        logger.warning(
            f"[FBR Task] Network error for Sale {sale_id}: {e}. "
            f"Retry {self.request.retries + 1}/{self.max_retries}"
        )
        sale.fbr_submission_status = FBRSubmissionStatus.FAILED
        sale.fbr_error_code        = "NET_ERR"
        sale.fbr_error_message     = str(e)
        sale.save(update_fields=[
            "fbr_submission_status", "fbr_error_code",
            "fbr_error_message", "updated_at"
        ])
        
        # Log Submission
        FBRSubmissionLog.objects.create(
            company=company,
            sale=sale,
            environment="sandbox" if is_sandbox else "production",
            endpoint="postinvoicedata_sb" if is_sandbox else "postinvoicedata",
            local_invoice_id=sale.sale_number,
            fbr_invoice_id="",
            status_code="NET_ERR",
            http_status=None,
            attempt=self.request.retries + 1,
            latency_ms=latency_ms,
            error_message=error_message_log,
            request_payload=payload,
            response_payload={}
        )
        
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(
                f"[FBR Task] Max retries exceeded for Sale {sale_id}. "
                f"Manual resubmission required."
            )
 
    except FBRAPIError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        status_code = str(e.error_code)[:10] if e.error_code else "UNK"
        error_message_log = e.message
        raw_response_log = getattr(e, 'raw_response', {})
        http_status = 200 # Usually FBR returns 200 with an error inside
        # FBR returned an error — don't retry (it's a data issue, not network)
        logger.error(
            f"[FBR Task] FBR API error for Sale {sale_id}: "
            f"[{e.error_code}] {e.message}"
        )
        sale.fbr_submission_status = FBRSubmissionStatus.FAILED
        sale.fbr_error_code        = status_code
        sale.fbr_error_message     = e.message
        sale.save(update_fields=[
            "fbr_submission_status", "fbr_error_code",
            "fbr_error_message", "updated_at"
        ])

        from companies.models import AuditLog
        AuditLog.objects.create(
            company=company,
            user_email="system@fbr-worker",
            entity_type="fbr_submission",
            entity_id=str(sale.pk),
            action="fail",
            ip_address="127.0.0.1"
        )
        
    except Exception as e:
        logger.error(f"[FBR Task] Unexpected error for Sale {sale_id}: {e}")
        sale.fbr_submission_status = FBRSubmissionStatus.FAILED
        sale.fbr_error_code        = "UNK_ERR"
        sale.fbr_error_message     = str(e)
        sale.save(update_fields=[
            "fbr_submission_status", "fbr_error_code",
            "fbr_error_message", "updated_at"
        ])

    finally:
        # Save success or FBRAPIError logs
        if not error_message_log and fbr_invoice_number_log:
            FBRSubmissionLog.objects.create(
                company=company,
                sale=sale,
                environment="sandbox" if is_sandbox else "production",
                endpoint="postinvoicedata_sb" if is_sandbox else "postinvoicedata",
                local_invoice_id=sale.sale_number,
                fbr_invoice_id=fbr_invoice_number_log,
                status_code="00",
                http_status=200,
                attempt=self.request.retries + 1,
                latency_ms=latency_ms,
                error_message="",
                request_payload=payload,
                response_payload=raw_response_log
            )
        elif status_code and status_code != "NET_ERR":
            FBRSubmissionLog.objects.create(
                company=company,
                sale=sale,
                environment="sandbox" if is_sandbox else "production",
                endpoint="postinvoicedata_sb" if is_sandbox else "postinvoicedata",
                local_invoice_id=sale.sale_number,
                fbr_invoice_id="",
                status_code=status_code,
                http_status=http_status,
                attempt=self.request.retries + 1,
                latency_ms=latency_ms,
                error_message=error_message_log,
                request_payload=payload,
                response_payload=raw_response_log
            )
 
 
@shared_task(name="digital_invoicing.retry_failed_submissions")
def retry_failed_submissions():
    """
    Periodic task — retries all FAILED FBR submissions.
 
    Runs every 15 minutes via Celery Beat.
    Covers the PRAL manual requirement: "the invoice must be submitted
    again to ensure its successful recording within FBR's digital platform."
 
    Only retries sales that:
    - Are COMPLETED
    - Have fbr_submission_status = FAILED
    - Have module_fbr_di enabled on their company
    - Have a valid token set
    - Were last attempted more than 5 minutes ago
    """
    from pos.models import Sale, SaleStatus, FBRSubmissionStatus
    from django.utils import timezone
    from datetime import timedelta
 
    cutoff = timezone.now() - timedelta(minutes=5)
 
    failed_sales = Sale.objects.filter(
        status=SaleStatus.COMPLETED,
        fbr_submission_status=FBRSubmissionStatus.FAILED,
        company__module_fbr_di=True,
        updated_at__lt=cutoff,
    ).select_related("company")
 
    count = 0
    for sale in failed_sales:
        # Only retry if company has a token
        has_token = (
            sale.company.fbr_production_token
            if sale.company.fbr_production_token
            else sale.company.fbr_sandbox_token
        )
        if has_token:
            submit_invoice_to_fbr.delay(sale.id)
            count += 1
 
    logger.info(f"[FBR Retry Task] Queued {count} failed sales for resubmission")
    return count
 
 
@shared_task(name="digital_invoicing.resubmit_single_sale")
def resubmit_single_sale(sale_id: int):
    """
    Manually triggered resubmission for a single sale.
    Called from the admin UI "Resubmit to FBR" button.
    """
    from pos.models import Sale, FBRSubmissionStatus
    try:
        sale = Sale.objects.get(pk=sale_id)
        # Reset status to pending before resubmitting
        sale.fbr_submission_status = FBRSubmissionStatus.PENDING
        sale.fbr_error_code        = ""
        sale.fbr_error_message     = ""
        sale.save(update_fields=[
            "fbr_submission_status", "fbr_error_code",
            "fbr_error_message", "updated_at"
        ])
        submit_invoice_to_fbr.delay(sale_id)
        logger.info(f"[FBR] Manual resubmission queued for Sale {sale_id}")
    except Sale.DoesNotExist:
        logger.error(f"[FBR] Sale {sale_id} not found for resubmission")