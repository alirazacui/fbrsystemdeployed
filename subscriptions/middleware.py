"""
========================================================
subscriptions/middleware.py
 
Subscription enforcement middleware.
Blocks ALL API access for expired/suspended companies.
========================================================
"""
 
from django.http import JsonResponse
from .models import *
 
class SubscriptionMiddleware:
    """
    Checks subscription status on every API request.
 
    Exemptions (always allowed even if expired):
    - /admin/ routes (Django admin)
    - /api/auth/ routes (login/logout)
    - Platform users (Admin, Admin Staff) — never blocked
    - GET /api/reports/admin/ — admin can still see expired companies
 
    For expired companies:
    - Returns HTTP 402 Payment Required
    - Clear message telling owner to contact admin
    """
 
    EXEMPT_PATHS = [
        "/admin/",
        "/api/auth/login/",
        "/api/auth/refresh/",
        "/api/auth/logout/",
    ]
 
    def __init__(self, get_response):
        self.get_response = get_response
 
    def __call__(self, request):
        # Only check authenticated API requests
        if self._should_check(request):
            block, response = self._check_subscription(request)
            if block:
                return response
 
        return self.get_response(request)
 
    def _should_check(self, request) -> bool:
        """Returns True if this request needs subscription checking."""
        path = request.path
 
        # Skip exempt paths
        for exempt in self.EXEMPT_PATHS:
            if path.startswith(exempt):
                return False
 
        # Only check API paths
        if not path.startswith("/api/"):
            return False
 
        # Only check authenticated users
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return False
 
        # Never block platform users
        if request.user.is_platform_user:
            return False
 
        # Must be a client user with a company
        if not request.user.company_id:
            return False
 
        return True
 
    def _check_subscription(self, request) -> tuple[bool, JsonResponse | None]:
        """
        Returns (should_block, response).
        """
        try:
            subscription = CompanySubscription.objects.select_related(
                "plan"
            ).get(
                company = request.user.company,
                status__in = [
                    CompanySubscription.Status.ACTIVE,
                    CompanySubscription.Status.TRIAL,
                    CompanySubscription.Status.EXPIRED,
                    CompanySubscription.Status.SUSPENDED,
                ]
            )
        except CompanySubscription.DoesNotExist:
            # No subscription found — block with clear message
            return True, JsonResponse(
                {
                    "error":   "no_subscription",
                    "message": (
                        "Your company does not have an active subscription. "
                        "Please contact the administrator."
                    ),
                },
                status=402,
            )
 
        # Check if expired
        if not subscription.is_active:
            return True, JsonResponse(
                {
                    "error":          "subscription_expired",
                    "message": (
                        f"Your subscription expired on {subscription.expiry_date}. "
                        f"Please contact your administrator to renew."
                    ),
                    "expiry_date":    str(subscription.expiry_date),
                    "plan":           subscription.plan.name,
                    "days_remaining": subscription.days_remaining,
                },
                status=402,
            )
 
        # Check if suspended
        if subscription.status == CompanySubscription.Status.SUSPENDED:
            return True, JsonResponse(
                {
                    "error":   "account_suspended",
                    "message": (
                        "Your account has been suspended. "
                        "Please contact the platform administrator."
                    ),
                },
                status=403,
            )
 
        # Attach subscription to request for use in views
        request.subscription = subscription
        return False, None
