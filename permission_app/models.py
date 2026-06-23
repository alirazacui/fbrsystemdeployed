from django.db import models

# Create your models here.
"""
permissions_app/models.py

Two models live here:

  Permission
  ──────────
  A static catalogue of every action that can be granted in the system.
  Each row = one atomic thing a user can do, e.g. "Create Invoice" inside
  the "FBR Digital Invoicing" module.

  Seeded once via a data migration / management command — never created
  at runtime by end users.

  UserPermission
  ──────────────
  A junction table linking a User to a Permission.
  One row = "this specific user has been granted this specific permission."

  Two ceilings stack on top of each other:
    Ceiling 1 — Company modules  →  if module_fbr_di=False on the company,
                                    no FBR DI UserPermission row can exist
                                    for any user in that company.
    Ceiling 2 — Owner bypass     →  Owner is auto-granted every permission
                                    that their company's modules allow.
                                    Platform Admin bypasses BOTH ceilings.

Who creates UserPermission rows?
  • Platform Admin  → creates rows for Admin Staff
  • Owner           → rows auto-created by signal when Owner user is saved
  • Owner           → manually creates/edits rows for Manager/Cashier/Salesperson

Signal (at the bottom of this file):
  post_save on User — when a new Owner is created, auto-create UserPermission
  rows for every Permission whose module_field is enabled on their company.
"""

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class PermissionAction(models.TextChoices):
    """
    The six atomic actions a permission can grant.
    These are the column labels in the UI checkbox grid.
    """
    VIEW    = "view",    _("View")
    CREATE  = "create",  _("Create")
    EDIT    = "edit",    _("Edit")
    DELETE  = "delete",  _("Delete")
    EXPORT  = "export",  _("Export")
    APPROVE = "approve", _("Approve")


class PermissionModule(models.TextChoices):
    """
    Every module that can appear as a permission group in the UI.

    IMPORTANT: each value here maps 1-to-1 with a module_* BooleanField
    on the Company model (see `module_field` property on Permission below).

    UI groups checkboxes by this module, so the admin sees:
      ┌─ FBR Digital Invoicing ───────────────────────────────┐
      │  ☑ View   ☑ Create   ☑ Edit   ☐ Delete   ☑ Export   │
      └────────────────────────────────────────────────────────┘
      ┌─ Inventory ────────────────────────────────────────────┐
      │  ☑ View   ☐ Create   ☐ Edit   ☐ Delete   ☐ Export    │
      └────────────────────────────────────────────────────────┘
    """
    # --- Sales & FBR ---
    SALES_INVOICING       = "sales_invoicing",       _("Sales Invoicing")
    FBR_DI                = "fbr_di",                _("FBR Digital Invoicing")
    CUSTOMER_DB           = "customer_db",           _("Customer Database")
    FBR_REGISTERED_BUYER  = "fbr_registered_buyer",  _("FBR Registered Buyer")

    # --- Operations ---
    RETURNS               = "returns",               _("Returns & Debit/Credit Notes")
    FBR_AMENDMENTS        = "fbr_amendments",        _("Manual FBR Amendments")
    CHEQUE_BANK_TRANSFER  = "cheque_bank_transfer",  _("Cheque & Bank Transfer")
    CUSTOMER_DISPLAY      = "customer_display",      _("Customer-Facing Display")
    HARDWARE_INTEGRATION  = "hardware_integration",  _("Hardware Integration")

    # --- Inventory ---
    INVENTORY             = "inventory",             _("Inventory Tracking")
    WAREHOUSING           = "warehousing",           _("Warehousing")

    # --- Multi-location (reserved) ---
    MULTI_LOCATION        = "multi_location",        _("Multi-Location / Multi-Branch")

    # --- Restaurant / F&B ---
    RESTAURANT_FNB        = "restaurant_fnb",        _("Restaurant F&B")
    DINE_IN               = "dine_in",               _("Dine-In")
    TAKEAWAY              = "takeaway",              _("Takeaway")
    DELIVERY              = "delivery",              _("Delivery")
    TABLE_FLOOR_MAP       = "table_floor_map",       _("Table & Floor Map")
    KITCHEN_DISPLAY       = "kitchen_display",       _("Kitchen Display / KDS")

    # --- Insights ---
    BASIC_REPORTS         = "basic_reports",         _("Basic Reports")
    ADVANCED_REPORTS      = "advanced_reports",      _("Advanced Reports")
    AUDIT_LOGS            = "audit_logs",            _("Audit Logs")

    # --- User Management (platform-level, always visible to Admin) ---
    USER_MANAGEMENT       = "user_management",       _("User Management")
    COMPANY_MANAGEMENT    = "company_management",    _("Company Management")


# Mapping: PermissionModule value → Company.module_* field name
# Used by the ceiling check — if company.module_field is False,
# no permission in that module can be granted.
MODULE_TO_COMPANY_FIELD: dict[str, str] = {
    PermissionModule.SALES_INVOICING      : "module_sales_invoicing",
    PermissionModule.FBR_DI               : "module_fbr_di",
    PermissionModule.CUSTOMER_DB          : "module_customer_db",
    PermissionModule.FBR_REGISTERED_BUYER : "module_fbr_registered_buyer",
    PermissionModule.RETURNS              : "module_returns",
    PermissionModule.FBR_AMENDMENTS       : "module_fbr_amendments",
    PermissionModule.CHEQUE_BANK_TRANSFER : "module_cheque_bank_transfer",
    PermissionModule.CUSTOMER_DISPLAY     : "module_customer_display",
    PermissionModule.HARDWARE_INTEGRATION : "module_hardware_integration",
    PermissionModule.INVENTORY            : "module_inventory",
    PermissionModule.WAREHOUSING          : "module_warehousing",
    PermissionModule.MULTI_LOCATION       : "module_multi_location",
    PermissionModule.RESTAURANT_FNB       : "module_restaurant_fnb",
    PermissionModule.DINE_IN              : "module_dine_in",
    PermissionModule.TAKEAWAY             : "module_takeaway",
    PermissionModule.DELIVERY             : "module_delivery",
    PermissionModule.TABLE_FLOOR_MAP      : "module_table_floor_map",
    PermissionModule.KITCHEN_DISPLAY      : "module_kitchen_display",
    PermissionModule.BASIC_REPORTS        : "module_basic_reports",
    PermissionModule.ADVANCED_REPORTS     : "module_advanced_reports",
    PermissionModule.AUDIT_LOGS           : "module_audit_logs",
    # Platform-only modules — no Company field; Admin always has these
    PermissionModule.USER_MANAGEMENT      : None,
    PermissionModule.COMPANY_MANAGEMENT   : None,
}


# ---------------------------------------------------------------------------
# Permission — the static catalogue
# ---------------------------------------------------------------------------

class Permission(models.Model):
    """
    One row = one atomic action a user can be granted.

    Examples after seeding:
      module=FBR_DI,   action=CREATE  → "Create FBR Digital Invoice"
      module=INVENTORY, action=EXPORT → "Export Inventory"
      module=USER_MANAGEMENT, action=DELETE → "Delete User"

    This table is populated once via a data migration.
    End users never create or delete rows here.
    """

    module = models.CharField(
        max_length=40,
        choices=PermissionModule.choices,
        verbose_name=_("Module"),
        help_text=_("The feature area this permission belongs to. Used for UI grouping."),
    )

    action = models.CharField(
        max_length=10,
        choices=PermissionAction.choices,
        verbose_name=_("Action"),
        help_text=_("The atomic operation being granted."),
    )

    codename = models.CharField(
        max_length=60,
        unique=True,
        verbose_name=_("Codename"),
        help_text=_(
            "Machine-readable identifier used in code checks. "
            "Auto-built as '{module}.{action}', e.g. 'fbr_di.create'. "
            "Never shown in the UI."
        ),
    )

    label = models.CharField(
        max_length=100,
        verbose_name=_("Label"),
        help_text=_("Human-readable name shown in the permission UI, e.g. 'Create FBR Digital Invoice'."),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Optional longer explanation shown as a tooltip in the permission panel."),
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_(
            "Inactive permissions are hidden from the UI and cannot be granted. "
            "Use this instead of deleting — deletion would break existing UserPermission rows."
        ),
    )

    class Meta:
        verbose_name        = _("Permission")
        verbose_name_plural = _("Permissions")
        ordering            = ["module", "action"]
        unique_together     = [("module", "action")]   # belt-and-suspenders alongside codename unique
        indexes = [
            models.Index(fields=["module"],   name="perm_module_idx"),
            models.Index(fields=["codename"], name="perm_codename_idx"),
        ]

    def __str__(self):
        return f"{self.get_module_display()} → {self.get_action_display()}"

    def save(self, *args, **kwargs):
        # Auto-build codename from module + action if not set
        if not self.codename:
            self.codename = f"{self.module}.{self.action}"
        super().save(*args, **kwargs)

    @property
    def module_field(self) -> str | None:
        """
        Returns the Company BooleanField name that gates this permission,
        or None if this is a platform-only permission (user/company management).

        Used by the ceiling check:
            if permission.module_field and not getattr(company, permission.module_field):
                # company doesn't have this module — permission cannot be granted
        """
        return MODULE_TO_COMPANY_FIELD.get(self.module)


# ---------------------------------------------------------------------------
# UserPermission — the junction table
# ---------------------------------------------------------------------------

class UserPermission(models.Model):
    """
    One row = one user has been granted one permission.

    Ceiling rules (enforced in clean() + serializer validation):
    ─────────────────────────────────────────────────────────────
    1. Platform Admin     → no rows needed; bypassed in permission checks
    2. Owner              → rows auto-created by signal for every enabled
                            company module; cannot exceed company modules
    3. Manager/Cashier/
       Salesperson        → rows created by Owner; still capped at company
                            modules (owner can't grant what company doesn't have)
    4. Admin Staff        → rows created by Admin; not capped by any company
                            (they're platform users)

    granted_by tracks who assigned this permission — important for audit.
    """

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,       # deleting a user removes all their permissions
        related_name="user_permissions_custom",
        verbose_name=_("User"),
    )

    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,       # deleting a permission cleans up grants
        related_name="user_permissions",
        verbose_name=_("Permission"),
    )

    granted_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permissions_granted",
        verbose_name=_("Granted By"),
        help_text=_(
            "The user who assigned this permission. "
            "NULL for auto-granted owner permissions (created by signal)."
        ),
    )

    granted_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Granted At"),
    )

    class Meta:
        verbose_name        = _("User Permission")
        verbose_name_plural = _("User Permissions")
        unique_together     = [("user", "permission")]   # a user can't be granted the same permission twice
        ordering            = ["user", "permission__module", "permission__action"]
        indexes = [
            models.Index(fields=["user"],       name="userperm_user_idx"),
            models.Index(fields=["permission"], name="userperm_perm_idx"),
        ]

    def __str__(self):
        return f"{self.user} | {self.permission}"

    def clean(self):
        """
        Model-level validation — called by serializer + Django admin.

        Rules enforced:
        1. Platform Admin never needs UserPermission rows — block creation.
        2. Platform-only permissions (user/company management) can only be
           granted to platform users (Admin Staff).
        3. For client users — the permission's module must be enabled on
           their company. Company is the hard ceiling.
        """
        from django.core.exceptions import ValidationError
        from users.models import User  # local import avoids circular ref

        user = self.user
        perm = self.permission

        # Rule 1 — Admin never needs rows
        if user.role == User.Role.ADMIN:
            raise ValidationError(
                _("Platform Admin bypasses all permission checks. "
                  "Do not create UserPermission rows for Admin users.")
            )

        # Rule 2 — Platform-only permissions only for platform users
        if perm.module_field is None:
            # module_field=None means USER_MANAGEMENT or COMPANY_MANAGEMENT
            if not user.is_platform_user:
                raise ValidationError(
                    _(f"The permission '{perm.label}' is a platform-only permission "
                      f"and cannot be assigned to client users.")
                )
        else:
            # Rule 3 — Client user ceiling check
            if user.is_client_user:
                if not user.company_id:
                    raise ValidationError(
                        _("Client user must belong to a company before permissions can be assigned.")
                    )
                company_has_module = getattr(user.company, perm.module_field, False)
                if not company_has_module:
                    raise ValidationError(
                        _(
                            f"Cannot grant '{perm.label}' — "
                            f"the module '{perm.get_module_display()}' is not enabled "
                            f"for {user.company.business_name}. "
                            f"Enable it on the Company record first."
                        )
                    )


# ---------------------------------------------------------------------------
# Helper — fetch all permissions for a user (used by DRF permission classes)
# ---------------------------------------------------------------------------

def get_user_permission_codenames(user) -> set[str]:
    """
    Returns a set of codenames this user currently holds.

    Usage in a DRF permission class:
        perms = get_user_permission_codenames(request.user)
        if "fbr_di.create" not in perms:
            raise PermissionDenied()

    Platform Admin → returns a sentinel set {"*"} meaning "all".
    Inactive/Suspended → returns empty set (no access at all).
    """
    from users.models import UserStatus  # local import

    # Suspended or inactive = no access
    if user.status != UserStatus.ACTIVE:
        return set()

    # Platform Admin bypasses everything
    if user.is_platform_admin:
        return {"*"}

    return set(
        UserPermission.objects
        .filter(user=user, permission__is_active=True)
        .values_list("permission__codename", flat=True)
    )


# ---------------------------------------------------------------------------
# Signal — auto-grant all company-module permissions to a new Owner
# ---------------------------------------------------------------------------

@receiver(post_save, sender="users.User")
def auto_grant_owner_permissions(sender, instance, created, **kwargs):
    """
    Fires after any User is saved.

    When a BRAND NEW Owner user is created:
      1. Fetch every active Permission whose module is enabled on their company.
      2. Bulk-create UserPermission rows for all of them.
         granted_by=None marks these as system-generated.

    Why signal and not the serializer?
      The serializer only runs on API calls. Using a signal means owner
      permissions are granted regardless of HOW the user is created
      (API, Django admin, management command, test factory).

    Why only `created=True`?
      We don't touch permissions when an existing owner is updated.
      Module changes on a company are handled separately (future task:
      a post_save on Company that syncs owner permissions when modules change).
    """
    if not created:
        return
    if instance.role != "owner":
        return
    if not instance.company_id:
        return  # safety guard — owner must have a company

    company = instance.company

    # Collect all Permission rows whose module is enabled on this company
    permissions_to_grant = []
    for perm in Permission.objects.filter(is_active=True):
        module_field = perm.module_field
        if module_field is None:
            continue   # platform-only permission — skip for client users
        if getattr(company, module_field, False):
            permissions_to_grant.append(
                UserPermission(
                    user=instance,
                    permission=perm,
                    granted_by=None,   # system-generated
                )
            )

    # Bulk-create — ignore conflicts in case signal fires twice
    UserPermission.objects.bulk_create(
        permissions_to_grant,
        ignore_conflicts=True,
    )