from django.urls import path
from . import scenario_views as views
from .admin_views import FBRSubmissionAdminViewSet

urlpatterns = [
    path(
        "admin/fbr-submissions/",
        FBRSubmissionAdminViewSet.as_view({"get": "list"}),
        name="admin-fbr-submissions-list",
    ),
    path(
        "admin/fbr-submissions/<int:pk>/",
        FBRSubmissionAdminViewSet.as_view({"get": "retrieve"}),
        name="admin-fbr-submissions-detail",
    ),
    path(
        "fbr/companies/<int:company_id>/clear-scenarios/",
        views.clear_all_scenarios,
        name="clear-all-scenarios",
    ),
    path(
        "fbr/companies/<int:company_id>/clear-scenario/",
        views.clear_single_scenario_view,
        name="clear-single-scenario",
    ),
    path(
        "fbr/task-status/<str:task_id>/",
        views.task_status,
        name="task-status",
    ),
    path(
        "fbr/companies/<int:company_id>/scenarios/logs/",
        views.list_scenario_logs,
        name="list-scenario-logs",
     ),
    path(
        "fbr/companies/<int:company_id>/scenarios/templates/",
        views.list_scenario_templates,
        name="list-scenario-templates",
    ),
    path(
        "fbr/companies/<int:company_id>/scenarios/submit-edited/",
        views.submit_edited_scenario,
        name="submit-edited-scenario",
    ),
]