"""
common/permissions.py

All DRF permission classes for the platform.

Usage in a ViewSet:
    from common.permissions import IsAdmin, IsOwnerOrAdmin, HasCodename

    class InvoiceViewSet(viewsets.GenericViewSet):
        permission_classes = [IsOwnerOrAdmin, HasCodename("fbr_di.create")]
"""

from rest_framework.permissions import BasePermission


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user_codenames(user) -> set:
    """
    Returns the set of permission codenames the user currently holds.
    Reads from DB — call once per request and cache if needed.

    Platform Admin returns {"*"} — checked with a sentinel in HasCodename.
    Inactive / Suspended returns empty set.
    """
    from permission_app.models import get_user_permission_codenames
    return get_user_permission_codenames(user)


# ---------------------------------------------------------------------------
# Role-based permission classes
# ---------------------------------------------------------------------------

class IsAdmin(BasePermission):
    """
    Allows access only to platform Admin (role='admin').
    Use for endpoints that manage companies, platform users, subscriptions.
    """
    message = "Only platform Admin can perform this action."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.is_platform_admin
        )


class IsAdminOrAdminStaff(BasePermission):
    """
    Allows platform Admin and Admin Staff.
    Use for read-heavy admin app endpoints where staff should also have access.
    """
    message = "Only platform Admin or Admin Staff can perform this action."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.is_platform_user
        )


class IsOwner(BasePermission):
    """
    Allows access only to company Owners.
    Use for endpoints where owners manage their own company's users/permissions.
    """
    message = "Only a company Owner can perform this action."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == "owner"
            and request.user.status == "active"
        )


class IsOwnerOrAdmin(BasePermission):
    """
    Allows platform Admin OR the company Owner.
    Most common pattern for company-scoped management endpoints.
    """
    message = "Only platform Admin or company Owner can perform this action."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return (
            request.user.is_platform_admin
            or (request.user.role == "owner" and request.user.status == "active")
        )


class IsClientUser(BasePermission):
    """
    Allows any active client user (Owner, Manager, Cashier, Salesperson).
    Use for POS endpoints that any staff member can hit.
    """
    message = "Only active client users can access this endpoint."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.is_client_user
            and request.user.status == "active"
            and request.user.company_id is not None
        )


class IsActiveUser(BasePermission):
    """
    Base check: user must be authenticated and active.
    Stack this with other permission classes.
    """
    message = "Your account is inactive or suspended."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.status == "active"
        )


# ---------------------------------------------------------------------------
# Module ceiling check
# ---------------------------------------------------------------------------

class CompanyModuleEnabled(BasePermission):
    """
    Checks that a specific module is enabled on the requesting user's company.

    Usage:
        class InventoryViewSet(...):
            permission_classes = [IsClientUser, CompanyModuleEnabled("module_inventory")]

    Platform Admin always passes (bypasses ceiling).
    """
    message = "Your company does not have access to this module."

    def __init__(self, module_field: str):
        self.module_field = module_field

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        # Platform Admin bypasses everything
        if request.user.is_platform_admin:
            return True
        return request.user.can_access_module(self.module_field)


# ---------------------------------------------------------------------------
# Codename-based permission check
# ---------------------------------------------------------------------------

class HasCodename(BasePermission):
    """
    Checks that the user has been granted a specific permission codename.

    Usage:
        permission_classes = [IsActiveUser, HasCodename("fbr_di.create")]

    Platform Admin always passes.
    Owner passes if their company has the module (auto-granted on creation).
    Others must have an explicit UserPermission row.
    """

    def __init__(self, codename: str):
        self.codename = codename
        self.message  = f"You do not have the '{codename}' permission."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # Platform Admin bypasses all checks
        if request.user.is_platform_admin:
            return True

        codenames = _get_user_codenames(request.user)

        # Sentinel check for platform admin (belt-and-suspenders)
        if "*" in codenames:
            return True

        return self.codename in codenames


# ---------------------------------------------------------------------------
# Object-level: same company guard
# ---------------------------------------------------------------------------

class IsSameCompany(BasePermission):
    """
    Object-level permission — prevents a user from accessing another
    company's records.

    Usage:
        def get_queryset(self):
            # Filter at queryset level first (more efficient)
            return SomeModel.objects.filter(company=self.request.user.company)

        # Then add this as a safety net at object level:
        permission_classes = [IsClientUser, IsSameCompany]

    Platform Admin bypasses this (can see all companies).
    """
    message = "You do not have access to this record."

    def has_object_permission(self, request, view, obj):
        if request.user.is_platform_admin:
            return True
        # obj must have a company_id attribute
        obj_company_id = getattr(obj, "company_id", None) or getattr(obj, "company", None)
        return obj_company_id == request.user.company_id