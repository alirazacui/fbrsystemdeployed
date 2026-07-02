"""
========================================================
digital_invoicing/scenario_views.py
 
API endpoint for triggering scenario clearing
Add to digital_invoicing/views.py and urls.py
========================================================
"""
 
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status as http_status
from common.permissions import IsOwnerOrAdmin
 
 
@api_view(["POST"])
@permission_classes([IsOwnerOrAdmin])
def clear_all_scenarios(request, company_id):
    """
    POST /api/fbr/companies/{company_id}/clear-scenarios/
 
    Admin triggers auto-clearing of all assigned sandbox scenarios.
    Runs as a background Celery task.
 
    Returns task ID so frontend can poll for completion.
    """
    if not request.user.is_platform_admin and str(company_id) != str(request.user.company_id):
        return Response(
            {"detail": "You do not have permission to access this company's scenarios."},
            status=http_status.HTTP_403_FORBIDDEN
        )

    from companies.models import Company
    from .scenario_tasks import clear_sandbox_scenarios, _get_assigned_scenarios
 
    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        return Response(
            {"error": "Company not found"},
            status=http_status.HTTP_404_NOT_FOUND,
        )
 
    if company.fbr_sandbox_complete:
        return Response(
            {
                "message": (
                    f"Sandbox already complete for {company.business_name}. "
                    f"Production token is already set."
                )
            }
        )
 
    if not company.fbr_sandbox_token:
        return Response(
            {"error": "No sandbox token set for this company. Add it first."},
            status=http_status.HTTP_400_BAD_REQUEST,
        )
 
    assigned = _get_assigned_scenarios(company)
    if not assigned:
        return Response(
            {
                "error": (
                    "No scenarios assigned. "
                    "Tick the scenario checkboxes on the Company record first."
                )
            },
            status=http_status.HTTP_400_BAD_REQUEST,
        )
 
    # Queue the Celery task
    task = clear_sandbox_scenarios.delay(company_id)
 
    return Response({
        "message":    f"Clearing {len(assigned)} scenarios for {company.business_name}...",
        "task_id":    task.id,
        "scenarios":  assigned,
        "note":       "Poll /api/fbr/task-status/{task_id}/ to check progress.",
    })
 
 
@api_view(["POST"])
@permission_classes([IsOwnerOrAdmin])
def clear_single_scenario_view(request, company_id):
    """
    POST /api/fbr/companies/{company_id}/clear-scenario/
    Body: {"scenario_code": "SN003"}
 
    Admin manually retries one specific failed scenario.
    """
    if not request.user.is_platform_admin and str(company_id) != str(request.user.company_id):
        return Response(
            {"detail": "You do not have permission to access this company's scenarios."},
            status=http_status.HTTP_403_FORBIDDEN
        )

    from .scenario_tasks import clear_single_scenario
 
    scenario_code = request.data.get("scenario_code", "").upper()
    if not scenario_code:
        return Response(
            {"error": "scenario_code is required"},
            status=http_status.HTTP_400_BAD_REQUEST,
        )
 
    task = clear_single_scenario.delay(company_id, scenario_code)
    return Response({
        "message":  f"Retrying {scenario_code}...",
        "task_id":  task.id,
    })
 
 
@api_view(["GET"])
@permission_classes([IsOwnerOrAdmin])
def task_status(request, task_id):
    """
    GET /api/fbr/task-status/{task_id}/
 
    Polls Celery task status.
    Frontend uses this to show progress to admin.
    """
    from celery.result import AsyncResult
    result = AsyncResult(task_id)
    return Response({
        "task_id": task_id,
        "status":  result.status,    # PENDING, STARTED, SUCCESS, FAILURE
        "result":  result.result if result.ready() else None,
    })
 
 
@api_view(["GET"])
@permission_classes([IsOwnerOrAdmin])
def list_scenario_logs(request, company_id):
    """
    GET /api/fbr/companies/{company_id}/scenarios/logs/
    Returns the latest log for each assigned scenario.
    """
    if not request.user.is_platform_admin and str(company_id) != str(request.user.company_id):
        return Response(
            {"detail": "You do not have permission to access this company's scenarios."},
            status=http_status.HTTP_403_FORBIDDEN
        )

    from .models import ScenarioTestLog
    from .serializers import ScenarioTestLogSerializer
    
    # Get distinct scenarios. In postgres we can use distinct('scenario_code')
    # but for simplicity, order by -created_at and group in python
    logs = ScenarioTestLog.objects.filter(company_id=company_id).order_by("-created_at")
    
    seen = set()
    latest_logs = []
    for log in logs:
        if log.scenario_code not in seen:
            seen.add(log.scenario_code)
            latest_logs.append(log)
            
    serializer = ScenarioTestLogSerializer(latest_logs, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsOwnerOrAdmin])
def submit_edited_scenario(request, company_id):
    """
    POST /api/fbr/companies/{company_id}/scenarios/submit-edited/
    Body: {"scenario_code": "SN018", "payload": {...}}
    Submits a manually edited JSON payload directly to PRAL.
    """
    if not request.user.is_platform_admin and str(company_id) != str(request.user.company_id):
        return Response(
            {"detail": "You do not have permission to access this company's scenarios."},
            status=http_status.HTTP_403_FORBIDDEN
        )

    from companies.models import Company
    from .fbr_client import FBRClient, FBRAPIError
    from .models import ScenarioTestLog

    scenario_code = request.data.get("scenario_code", "").upper()
    payload = request.data.get("payload")

    if not scenario_code or not payload:
        return Response(
            {"error": "scenario_code and payload are required"},
            status=http_status.HTTP_400_BAD_REQUEST,
        )

    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        return Response({"error": "Company not found"}, status=http_status.HTTP_404_NOT_FOUND)

    if not company.fbr_sandbox_token:
        return Response({"error": "No sandbox token set"}, status=http_status.HTTP_400_BAD_REQUEST)

    client = FBRClient(token=company.fbr_sandbox_token, base_url=company.fbr_sandbox_endpoint, is_sandbox=True)

    log_entry = ScenarioTestLog.objects.create(
        company=company,
        scenario_code=scenario_code,
        status=ScenarioTestLog.Status.PENDING,
        request_payload=payload
    )

    try:
        result = client.submit_invoice(payload)
        
        log_entry.status = ScenarioTestLog.Status.SUCCESS
        log_entry.response_payload = result.get("raw_response", {})
        log_entry.fbr_invoice_number = result.get("fbr_invoice_number", "")
        log_entry.save()

        return Response({
            "message": "Invoice accepted",
            "fbr_invoice_no": result.get("fbr_invoice_number"),
            "raw_response": result.get("raw_response", {})
        })
    except FBRAPIError as e:
        log_entry.status = ScenarioTestLog.Status.FAILED
        log_entry.error_message = f"[{e.error_code}] {e.message}"
        log_entry.save()

        return Response({
            "error_code": e.error_code,
            "error": e.message
        }, status=http_status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        log_entry.status = ScenarioTestLog.Status.FAILED
        log_entry.error_message = str(e)
        log_entry.save()

        return Response({
            "error": str(e)
        }, status=http_status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsOwnerOrAdmin])
def list_scenario_templates(request, company_id):
    """
    GET /api/fbr/companies/{company_id}/scenarios/templates/
    Returns the default compiled JSON payload templates for all assigned scenarios.
    """
    if not request.user.is_platform_admin and str(company_id) != str(request.user.company_id):
        return Response(
            {"detail": "You do not have permission to access this company's scenarios."},
            status=http_status.HTTP_403_FORBIDDEN
        )

    from companies.models import Company
    from .scenario_builder import ScenarioInvoiceBuilder
    from .scenario_tasks import _get_assigned_scenarios

    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        return Response(
            {"error": "Company not found"},
            status=http_status.HTTP_404_NOT_FOUND,
        )

    assigned = _get_assigned_scenarios(company)
    templates = {}
    for scenario_code in assigned:
        try:
            builder = ScenarioInvoiceBuilder(company, scenario_code)
            templates[scenario_code] = builder.build()
        except Exception as e:
            templates[scenario_code] = {"error": f"Failed to build template: {str(e)}"}

    return Response(templates)
