from django.urls import path
from . import scenario_views as views
 
urlpatterns = [
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
]