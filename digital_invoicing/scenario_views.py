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
from common.permissions import IsAdmin
 
 
@api_view(["POST"])
@permission_classes([IsAdmin])
def clear_all_scenarios(request, company_id):
    """
    POST /api/fbr/companies/{company_id}/clear-scenarios/
 
    Admin triggers auto-clearing of all assigned sandbox scenarios.
    Runs as a background Celery task.
 
    Returns task ID so frontend can poll for completion.
    """
    from companies.models import Company
    from .scenario_tasks import clear_sandbox_scenarios
 
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
@permission_classes([IsAdmin])
def clear_single_scenario_view(request, company_id):
    """
    POST /api/fbr/companies/{company_id}/clear-scenario/
    Body: {"scenario_code": "SN003"}
 
    Admin manually retries one specific failed scenario.
    """
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
@permission_classes([IsAdmin])
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
