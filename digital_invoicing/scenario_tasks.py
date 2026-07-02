"""
========================================================
digital_invoicing/scenario_tasks.py
 
Celery Tasks for Sandbox Scenario Auto-Clearing
========================================================
"""
import logging
logger = logging.getLogger(__name__)
 
def _get_assigned_scenarios(company) -> list:
    """Returns list of scenario codes assigned to this company."""
    from companies.models import FBR_SCENARIOS
    return [
        code.upper()
        for code, _ in FBR_SCENARIOS
        if getattr(company, f"fbr_scenario_{code.lower()}", False)
    ]
 
 
from celery import shared_task
 
 
@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    name="digital_invoicing.clear_sandbox_scenarios",
)
def clear_sandbox_scenarios(self, company_id: int):
    """
    Celery task — auto-clears all assigned sandbox scenarios for a company.
 
    Triggered when Admin clicks "Clear All Scenarios" button.
 
    Flow:
        1. Load company and its assigned scenarios
        2. For each scenario → build correct invoice JSON
        3. POST to FBR sandbox
        4. Track which passed and which failed
        5. After all submissions → attempt to fetch production token
        6. If production token received → update company
 
    Returns:
        dict with results summary
    """
    from companies.models import Company
    from .fbr_client import FBRClient, FBRAPIError
    from .scenario_builder import ScenarioInvoiceBuilder, SCENARIO_TEMPLATES
    from .models import ScenarioTestLog
 
    logger.info(f"[Scenarios] Starting auto-clear for Company ID: {company_id}")
 
    # ── Load company ─────────────────────────────────────────────────
    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        logger.error(f"[Scenarios] Company {company_id} not found")
        return {"error": "Company not found"}
 
    # ── Check sandbox token ──────────────────────────────────────────
    if not company.fbr_sandbox_token:
        logger.error(f"[Scenarios] No sandbox token for {company.business_name}")
        return {"error": "No sandbox token set. Add it in the Company admin first."}
 
    # ── Get assigned scenarios ───────────────────────────────────────
    assigned = _get_assigned_scenarios(company)
    if not assigned:
        return {"error": "No scenarios assigned to this company. Tick the scenarios first."}
 
    logger.info(f"[Scenarios] {len(assigned)} scenarios to clear: {assigned}")
 
    client  = FBRClient(token=company.fbr_sandbox_token, base_url=company.fbr_sandbox_endpoint, is_sandbox=True)
    results = {
        "passed":  [],
        "failed":  [],
        "total":   len(assigned),
    }
 
    # ── Submit each scenario ─────────────────────────────────────────
    for scenario_code in assigned:
        logger.info(f"[Scenarios] Submitting {scenario_code}...")
 
        log_entry = ScenarioTestLog.objects.create(
            company=company,
            scenario_code=scenario_code,
            status=ScenarioTestLog.Status.PENDING,
        )

        try:
            builder = ScenarioInvoiceBuilder(company, scenario_code)
            payload = builder.build()
            log_entry.request_payload = payload
            log_entry.save(update_fields=["request_payload"])

            result  = client.submit_invoice(payload)
 
            log_entry.status = ScenarioTestLog.Status.SUCCESS
            log_entry.response_payload = result.get("raw_response", {})
            log_entry.fbr_invoice_number = result.get("fbr_invoice_number", "")
            log_entry.save()

            from digital_invoicing.models import FBRSubmissionLog
            FBRSubmissionLog.objects.create(
                company=company,
                environment="sandbox",
                endpoint="postinvoicedata_sb",
                local_invoice_id=scenario_code,
                fbr_invoice_id=result.get("fbr_invoice_number", ""),
                status_code="00",
                http_status=200,
                attempt=1,
                error_message=""
            )

            results["passed"].append({
                "scenario":         scenario_code,
                "fbr_invoice_no":   result["fbr_invoice_number"],
                "description":      SCENARIO_TEMPLATES.get(
                    scenario_code, {}
                ).get("description", ""),
            })
            logger.info(f"[Scenarios] ✓ {scenario_code} passed — {result['fbr_invoice_number']}")
 
        except FBRAPIError as e:
            log_entry.status = ScenarioTestLog.Status.FAILED
            log_entry.error_message = f"[{e.error_code}] {e.message}"
            log_entry.save()

            from digital_invoicing.models import FBRSubmissionLog
            FBRSubmissionLog.objects.create(
                company=company,
                environment="sandbox",
                endpoint="postinvoicedata_sb",
                local_invoice_id=scenario_code,
                fbr_invoice_id="",
                status_code=str(e.error_code)[:10] if e.error_code else "UNK",
                http_status=200,
                attempt=1,
                error_message=e.message
            )

            results["failed"].append({
                "scenario":    scenario_code,
                "error_code":  e.error_code,
                "error":       e.message,
            })
            logger.error(f"[Scenarios] ✗ {scenario_code} failed: [{e.error_code}] {e.message}")
 
        except Exception as e:
            log_entry.status = ScenarioTestLog.Status.FAILED
            log_entry.error_message = str(e)
            log_entry.save()

            from digital_invoicing.models import FBRSubmissionLog
            FBRSubmissionLog.objects.create(
                company=company,
                environment="sandbox",
                endpoint="postinvoicedata_sb",
                local_invoice_id=scenario_code,
                fbr_invoice_id="",
                status_code="ERROR",
                http_status=500,
                attempt=1,
                error_message=str(e)
            )

            results["failed"].append({
                "scenario": scenario_code,
                "error":    str(e),
            })
            logger.error(f"[Scenarios] ✗ {scenario_code} error: {e}")
 
    # ── Check if all passed — attempt to fetch production token ──────
    results["all_passed"] = len(results["failed"]) == 0
 
    if results["all_passed"]:
        logger.info(f"[Scenarios] All scenarios passed! Fetching production token...")
        try:
            production_token = _fetch_production_token(company, client)
            if production_token:
                company.fbr_production_token  = production_token
                company.fbr_sandbox_complete  = True
                company.save(update_fields=[
                    "fbr_production_token",
                    "fbr_sandbox_complete",
                    "updated_at",
                ])
                results["production_token_issued"] = True
                results["message"] = (
                    "All scenarios cleared! Production token issued and saved. "
                    "Company is now ready for live invoice submission."
                )
                logger.info(
                    f"[Scenarios] ✓ Production token issued for {company.business_name}"
                )
            else:
                results["production_token_issued"] = False
                results["message"] = (
                    "All scenarios passed but production token not yet available. "
                    "FBR may take a few minutes to issue it. Try again shortly."
                )
        except Exception as e:
            results["production_token_issued"] = False
            results["message"] = f"Scenarios passed but error fetching token: {e}"
    else:
        failed_codes = [f["scenario"] for f in results["failed"]]
        results["message"] = (
            f"{len(results['passed'])}/{results['total']} scenarios passed. "
            f"Failed: {', '.join(failed_codes)}. "
            f"Fix the errors and retry the failed scenarios manually."
        )
 
    logger.info(f"[Scenarios] Complete: {results['message']}")
    return results
 
 
@shared_task(
    name="digital_invoicing.clear_single_scenario",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def clear_single_scenario(self, company_id: int, scenario_code: str):
    """
    Clears a single scenario manually.
    Used when admin wants to retry one failed scenario.
    """
    from companies.models import Company
    from .fbr_client import FBRClient, FBRAPIError
    from .scenario_builder import ScenarioInvoiceBuilder
    from .models import ScenarioTestLog
 
    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        return {"error": "Company not found"}
 
    if not company.fbr_sandbox_token:
        return {"error": "No sandbox token set"}
 
    client = FBRClient(token=company.fbr_sandbox_token, base_url=company.fbr_sandbox_endpoint, is_sandbox=True)
 
    log_entry = ScenarioTestLog.objects.create(
        company=company,
        scenario_code=scenario_code,
        status=ScenarioTestLog.Status.PENDING,
    )
 
    try:
        builder = ScenarioInvoiceBuilder(company, scenario_code)
        payload = builder.build()
        log_entry.request_payload = payload
        log_entry.save(update_fields=["request_payload"])

        result  = client.submit_invoice(payload)
        
        log_entry.status = ScenarioTestLog.Status.SUCCESS
        log_entry.response_payload = result.get("raw_response", {})
        log_entry.fbr_invoice_number = result.get("fbr_invoice_number", "")
        log_entry.save()

        from digital_invoicing.models import FBRSubmissionLog
        FBRSubmissionLog.objects.create(
            company=company,
            environment="sandbox",
            endpoint="postinvoicedata_sb",
            local_invoice_id=scenario_code,
            fbr_invoice_id=result.get("fbr_invoice_number", ""),
            status_code="00",
            http_status=200,
            attempt=1,
            error_message=""
        )

        return {
            "scenario":       scenario_code,
            "status":         "passed",
            "fbr_invoice_no": result["fbr_invoice_number"],
        }
    except FBRAPIError as e:
        log_entry.status = ScenarioTestLog.Status.FAILED
        log_entry.error_message = f"[{e.error_code}] {e.message}"
        log_entry.save()

        from digital_invoicing.models import FBRSubmissionLog
        FBRSubmissionLog.objects.create(
            company=company,
            environment="sandbox",
            endpoint="postinvoicedata_sb",
            local_invoice_id=scenario_code,
            fbr_invoice_id="",
            status_code=str(e.error_code)[:10] if e.error_code else "UNK",
            http_status=200,
            attempt=1,
            error_message=e.message
        )

        return {
            "scenario":   scenario_code,
            "status":     "failed",
            "error_code": e.error_code,
            "error":      e.message,
        }
    except Exception as e:
        log_entry.status = ScenarioTestLog.Status.FAILED
        log_entry.error_message = str(e)
        log_entry.save()

        from digital_invoicing.models import FBRSubmissionLog
        FBRSubmissionLog.objects.create(
            company=company,
            environment="sandbox",
            endpoint="postinvoicedata_sb",
            local_invoice_id=scenario_code,
            fbr_invoice_id="",
            status_code="ERROR",
            http_status=500,
            attempt=1,
            error_message=str(e)
        )

        return {
            "scenario": scenario_code,
            "status":   "failed",
            "error":    str(e),
        }
 
 
def _fetch_production_token(company, client: "FBRClient") -> str:
    """
    Attempts to fetch the production token after all scenarios pass.
 
    FBR auto-generates the production token once all scenarios are
    cleared. We need to fetch it from the sandbox environment
    using the getProductionToken endpoint.
 
    Note: If FBR hasn't generated it yet, returns empty string.
    The periodic retry task will keep trying.
    """
    import requests
 
    url = f"{client.base_url}/v1/di/getProductionToken"
    try:
        response = requests.get(
            url,
            headers=client._headers(),
            timeout=30,
        )
        data = response.json()
        error_code = str(data.get("errorCode", ""))
        if error_code == "0":
            token = data.get("productionToken", "")
            return token
        logger.warning(
            f"[Scenarios] Production token not ready yet: "
            f"[{error_code}] {data.get('errorMessage', '')}"
        )
        return ""
    except Exception as e:
        logger.error(f"[Scenarios] Error fetching production token: {e}")
        return ""
