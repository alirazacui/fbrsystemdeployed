from django.db import models

# Create your models here.
"""
users/models.py

Custom User model for the FBR POS Platform.

Two completely separate user trees — they never cross:

  PLATFORM SIDE (no company)
  ──────────────────────────
  Admin  →  Admin Staff

  CLIENT SIDE (always tied to one Company)
  ─────────────────────────────────────────
  Owner  →  Manager / Cashier / Salesperson

Key rules encoded here
──────────────────────
1. AUTH_USER_MODEL = "users.User"  (set in settings.py — never change this)
2. Platform users  (admin, admin_staff) → company = NULL
3. Client users    (owner, manager, cashier, salesperson) → company = FK to Company
4. Exactly ONE owner per company — enforced by a partial unique index at the DB level
5. Password is set manually by the creator — no auto-generation, no email
6. Three-state account status: active / inactive / suspended
7. No groups, no custom-role creation — individual checkbox permissions only
"""

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from config.storage_backends import user_profile_upload_path


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class UserStatus(models.TextChoices):
    """
    Three-state status replacing the bare is_active boolean.

    ACTIVE    — can log in and use the system normally
    INACTIVE  — soft-disabled by the creator/owner (e.g. staff member left)
                cannot log in; record kept for audit trail
    SUSPENDED — disabled by platform Admin (e.g. non-payment, policy breach)
                owner cannot re-activate; only Admin can lift suspension
    """
    ACTIVE    = "active",    _("Active")
    INACTIVE  = "inactive",  _("Inactive")
    SUSPENDED = "suspended", _("Suspended")


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class CustomUserManager(BaseUserManager):
    """
    Replaces Django's default UserManager.

    - email is the login field (not username)
    - username is kept on the model (AbstractUser requires it) but is
      auto-populated from email so the creator never has to fill it in
    """

    def _create_user(self, email: str, password: str, **extra_fields):
        if not email:
            raise ValueError(_("An email address is required."))
        email = self.normalize_email(email)
        # Keep username in sync with email so AbstractUser internals stay happy
        extra_fields.setdefault("username", email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields):
        """
        Used only for manage.py createsuperuser.
        Always creates a platform Admin (role=ADMIN, no company).
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("status", UserStatus.ACTIVE)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self._create_user(email, password, **extra_fields)

    # ------------------------------------------------------------------
    # Convenience querysets — call these instead of filtering by role
    # everywhere in the codebase
    # ------------------------------------------------------------------

    def platform_users(self):
        """Admin + Admin Staff — no company."""
        return self.filter(role__in=[User.Role.ADMIN, User.Role.ADMIN_STAFF])

    def client_users(self):
        """All users who belong to a company."""
        return self.filter(
            role__in=[
                User.Role.OWNER,
                User.Role.MANAGER,
                User.Role.CASHIER,
                User.Role.SALESPERSON,
            ]
        )

    def active_users(self):
        return self.filter(status=UserStatus.ACTIVE)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class User(AbstractUser):
    """
    Single user table for both platform users and client users.

    Login field : email  (unique)
    username    : mirrors email automatically — required by AbstractUser
                  but never shown in any UI

    Sections
    --------
    1. Role
    2. Company membership
    3. Personal details
    4. Account status
    5. Audit / creator tracking
    6. Timestamps
    """

    # ------------------------------------------------------------------
    # 1. Role
    # ------------------------------------------------------------------

    class Role(models.TextChoices):
        # Platform side — no company
        ADMIN       = "admin",       _("Admin")
        ADMIN_STAFF = "admin_staff", _("Admin Staff")

        # Client side — always belong to a company
        OWNER       = "owner",       _("Owner")
        MANAGER     = "manager",     _("Manager")
        CASHIER     = "cashier",     _("Cashier")
        SALESPERSON = "salesperson", _("Salesperson")

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        verbose_name=_("Role"),
        help_text=_(
            "Determines which app this user can access and what they can do. "
            "Admin / Admin Staff → platform (no company). "
            "Owner / Manager / Cashier / Salesperson → client POS (must have a company)."
        ),
    )

    # ------------------------------------------------------------------
    # 2. Company membership
    # ------------------------------------------------------------------

    company = models.ForeignKey(
        "companies.Company",            # string ref — avoids circular import
        on_delete=models.PROTECT,       # never silently delete a company that has users
        null=True,
        blank=True,
        related_name="users",
        verbose_name=_("Company"),
        help_text=_(
            "NULL for Admin and Admin Staff (platform users). "
            "Required for Owner, Manager, Cashier, Salesperson."
        ),
    )

    # ------------------------------------------------------------------
    # 3. Personal details
    # ------------------------------------------------------------------

    # AbstractUser already provides first_name, last_name — we extend with:
    email = models.EmailField(
        unique=True,
        verbose_name=_("Email Address"),
        help_text=_("Used as the login credential. Must be unique across the entire platform."),
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Phone Number"),
    )
    profile_image = models.ImageField(
    upload_to=user_profile_upload_path,
    blank=True,
    null=True,
    verbose_name=_("Profile Image"),
     )

    # username is inherited from AbstractUser.
    # We keep it but auto-fill it from email so it's never a user-facing field.
    # REQUIRED_FIELDS stays empty; USERNAME_FIELD is email.

    # ------------------------------------------------------------------
    # 4. Account status
    # ------------------------------------------------------------------

    status = models.CharField(
        max_length=20,
        choices=UserStatus.choices,
        default=UserStatus.ACTIVE,
        verbose_name=_("Account Status"),
        help_text=_(
            "ACTIVE → can log in. "
            "INACTIVE → disabled by owner/admin (staff left, etc.). "
            "SUSPENDED → disabled by platform Admin only (non-payment, breach). "
            "Owner cannot lift a suspension — only platform Admin can."
        ),
    )

    # We still keep AbstractUser.is_active in sync with status so Django's
    # built-in auth backend (which checks is_active) works correctly.
    # See the save() override below.

    # ------------------------------------------------------------------
    # 5. Audit / creator tracking
    # ------------------------------------------------------------------

    created_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_users",
        verbose_name=_("Created By"),
        help_text=_(
            "The user who created this account. "
            "NULL for the very first Admin (created via manage.py createsuperuser)."
        ),
    )

    # ------------------------------------------------------------------
    # 6. Timestamps (AbstractUser gives date_joined; we add updated_at)
    # ------------------------------------------------------------------

    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    # ------------------------------------------------------------------
    # Manager & login field
    # ------------------------------------------------------------------

    objects = CustomUserManager()

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = []   # email + password are enough for createsuperuser

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    class Meta:
        verbose_name        = _("User")
        verbose_name_plural = _("Users")
        ordering            = ["-date_joined"]

        indexes = [
            models.Index(fields=["company", "role"], name="user_company_role_idx"),
            models.Index(fields=["status"],           name="user_status_idx"),
            models.Index(fields=["role"],             name="user_role_idx"),
        ]

        constraints = [
            # ----------------------------------------------------------------
            # ONE OWNER PER COMPANY — the most important business rule here.
            #
            # A partial unique index: within rows where role = 'owner',
            # the company_id must be unique.
            # This fires at the database level — even a raw SQL insert can't
            # sneak a second owner in.
            # ----------------------------------------------------------------
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(role="owner"),
                name="unique_owner_per_company",
            ),

            # ----------------------------------------------------------------
            # PLATFORM USERS MUST NOT HAVE A COMPANY
            # ----------------------------------------------------------------
            models.CheckConstraint(
                condition=(
                    # admin & admin_staff → company must be NULL
                    ~models.Q(role__in=["admin", "admin_staff"]) |
                    models.Q(company__isnull=True)
                ),
                name="platform_users_have_no_company",
            ),

            # ----------------------------------------------------------------
            # CLIENT USERS MUST HAVE A COMPANY
            # ----------------------------------------------------------------
            models.CheckConstraint(
                condition=(
                    # owner / manager / cashier / salesperson → company must NOT be NULL
                    ~models.Q(role__in=["owner", "manager", "cashier", "salesperson"]) |
                    models.Q(company__isnull=False)
                ),
                name="client_users_must_have_company",
            ),
        ]

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self):
        company_part = f" @ {self.company.business_name}" if self.company_id else " [Platform]"
        return f"{self.get_full_name() or self.email} ({self.get_role_display()}){company_part}"

    # ------------------------------------------------------------------
    # Save override — keep username + is_active in sync automatically
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        # Mirror email → username so AbstractUser internals never complain
        if not self.username:
            self.username = self.email

        # Keep Django's built-in is_active in sync with our status field.
        # Only ACTIVE maps to is_active=True; inactive and suspended both
        # block login through the standard auth backend.
        self.is_active = (self.status == UserStatus.ACTIVE)

        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Convenience properties — used by permission classes
    # ------------------------------------------------------------------

    @property
    def is_platform_user(self) -> bool:
        """True for Admin and Admin Staff — users who belong to no company."""
        return self.role in (self.Role.ADMIN, self.Role.ADMIN_STAFF)

    @property
    def is_platform_admin(self) -> bool:
        """True only for the top-level Admin — bypasses ALL ceilings."""
        return self.role == self.Role.ADMIN

    @property
    def is_owner(self) -> bool:
        return self.role == self.Role.OWNER

    @property
    def is_client_user(self) -> bool:
        """True for all users who belong to a company."""
        return self.role in (
            self.Role.OWNER,
            self.Role.MANAGER,
            self.Role.CASHIER,
            self.Role.SALESPERSON,
        )

    @property
    def is_active_account(self) -> bool:
        """Readable alias — use this in business logic instead of is_active."""
        return self.status == UserStatus.ACTIVE

    def can_access_module(self, module_field: str) -> bool:
        """
        Returns True if this user's company has the given module enabled.

        Platform Admin always returns True (bypasses ceiling).
        All other users are bounded by their company's modules.

        Usage:
            user.can_access_module("module_inventory")
        """
        if self.is_platform_admin:
            return True
        if not self.company_id:
            return False
        return getattr(self.company, module_field, False)