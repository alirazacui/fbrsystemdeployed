from django.db import models

# Create your models here.
"""
========================================================
subscriptions/models.py
 
Dynamic subscription management system.
 
Admin creates and manages plans — no hardcoded limits.
Plans define exactly what a company can do and how much.
 
Three models:
  SubscriptionPlan      → admin-defined plans with limits
  CompanySubscription   → links company to active plan
  SubscriptionHistory   → audit trail of all plan changes
========================================================
"""
 
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
 
 
# ---------------------------------------------------------------------------
# SubscriptionPlan
# ---------------------------------------------------------------------------
 
class SubscriptionPlan(models.Model):
    """
    One row = one subscription plan admin has created.
 
    Admin can create unlimited plans with any limits they want.
    Examples:
      Trial   → 14 days, 50 products, 2 users, free
      Starter → 30 days, 200 products, 5 users, Rs. 2000/month
      Pro     → 30 days, 1000 products, 15 users, Rs. 5000/month
      Premium → 30 days, unlimited products, unlimited users, Rs. 10000/month
    """
 
    # ── Identity ──────────────────────────────────────────────────────
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("Plan Name"),
        help_text=_("e.g. Trial, Starter, Pro, Premium, Enterprise"),
    )
 
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Shown to admin when assigning plan to a company."),
    )
 
    is_trial = models.BooleanField(
        default=False,
        verbose_name=_("Is Trial Plan"),
        help_text=_(
            "Trial plans are given free for a limited period. "
            "Each company can only use a trial plan once."
        ),
    )
 
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_(
            "Inactive plans cannot be assigned to new companies. "
            "Existing subscriptions on this plan are not affected."
        ),
    )
 
    # ── Pricing ───────────────────────────────────────────────────────
    price_per_month = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Price Per Month (Rs.)"),
        help_text=_("Set to 0 for free/trial plans."),
    )
 
    duration_days = models.PositiveIntegerField(
        default=30,
        verbose_name=_("Duration (Days)"),
        help_text=_(
            "How many days this plan lasts. "
            "Trial plans typically 14 days, paid plans 30 days."
        ),
    )
 
    # ── Usage limits ──────────────────────────────────────────────────
    # Set to 0 to mean UNLIMITED for any limit field
 
    max_products = models.PositiveIntegerField(
        default=100,
        verbose_name=_("Max Products"),
        help_text=_("Maximum number of active products. 0 = unlimited."),
    )
 
    max_users = models.PositiveIntegerField(
        default=3,
        verbose_name=_("Max Staff Users"),
        help_text=_(
            "Maximum number of staff users (Manager, Cashier, Salesperson). "
            "Does not count the Owner. 0 = unlimited."
        ),
    )
 
    max_customers = models.PositiveIntegerField(
        default=500,
        verbose_name=_("Max Customers"),
        help_text=_("Maximum number of customer records. 0 = unlimited."),
    )
 
    max_sales_per_month = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Max Sales Per Month"),
        help_text=_("Maximum completed sales per month. 0 = unlimited."),
    )
 
    max_categories = models.PositiveIntegerField(
        default=20,
        verbose_name=_("Max Categories"),
        help_text=_("Maximum product categories. 0 = unlimited."),
    )
 
    # ── Modules included in this plan ─────────────────────────────────
    # These are DEFAULT modules auto-enabled when this plan is assigned.
    # Admin can still override per-company after assignment.
 
    includes_fbr_di              = models.BooleanField(default=True,  verbose_name=_("Includes FBR Digital Invoicing"))
    includes_inventory           = models.BooleanField(default=False, verbose_name=_("Includes Inventory Tracking"))
    includes_warehousing         = models.BooleanField(default=False, verbose_name=_("Includes Warehousing"))
    includes_advanced_reports    = models.BooleanField(default=False, verbose_name=_("Includes Advanced Reports"))
    includes_audit_logs          = models.BooleanField(default=False, verbose_name=_("Includes Audit Logs"))
    includes_hardware_integration = models.BooleanField(default=False, verbose_name=_("Includes Hardware Integration"))
    includes_restaurant_fnb      = models.BooleanField(default=False, verbose_name=_("Includes Restaurant F&B"))
    includes_multi_branch        = models.BooleanField(default=False, verbose_name=_("Includes Multi-Branch"))
    includes_debit_credit_notes  = models.BooleanField(default=True,  verbose_name=_("Includes Debit/Credit Notes"))
    includes_returns             = models.BooleanField(default=True,  verbose_name=_("Includes Returns"))
    includes_cheque_bank         = models.BooleanField(default=False, verbose_name=_("Includes Cheque & Bank Transfer"))
 
    # ── Timestamps ────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name        = _("Subscription Plan")
        verbose_name_plural = _("Subscription Plans")
        ordering            = ["price_per_month"]
 
    def __str__(self):
        price = f"Rs. {self.price_per_month}/month" if self.price_per_month > 0 else "Free"
        return f"{self.name} ({price}, {self.duration_days} days)"
 
    def get_limit_display(self, field_name: str) -> str:
        """Returns 'Unlimited' or the actual number."""
        value = getattr(self, field_name, 0)
        return "Unlimited" if value == 0 else str(value)
 
    def is_unlimited(self, field_name: str) -> bool:
        return getattr(self, field_name, 0) == 0
 
 
# ---------------------------------------------------------------------------
# CompanySubscription
# ---------------------------------------------------------------------------
 
class CompanySubscription(models.Model):
    """
    One row = one active or historical subscription for a company.
 
    A company always has exactly one ACTIVE subscription.
    When plan is changed, old subscription is marked EXPIRED
    and a new one is created.
 
    This is the source of truth for:
    - Is this company allowed to use the POS right now?
    - How many products/users/customers can they have?
    - When does their subscription expire?
    """
 
    class Status(models.TextChoices):
        ACTIVE    = "active",    _("Active")
        TRIAL     = "trial",     _("Trial")
        EXPIRED   = "expired",   _("Expired")
        SUSPENDED = "suspended", _("Suspended — Manual suspension by admin")
        CANCELLED = "cancelled", _("Cancelled")
 
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="subscriptions",
        verbose_name=_("Company"),
    )
 
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
        verbose_name=_("Plan"),
    )
 
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.TRIAL,
        verbose_name=_("Status"),
    )
 
    # ── Dates ─────────────────────────────────────────────────────────
    start_date = models.DateField(
        default=timezone.now,
        verbose_name=_("Start Date"),
    )
 
    expiry_date = models.DateField(
        verbose_name=_("Expiry Date"),
        help_text=_("After this date the company's POS access is blocked."),
    )
 
    # ── Extension tracking ────────────────────────────────────────────
    extended_by_days = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Extended By (Days)"),
        help_text=_("Total days manually added by admin extensions."),
    )
 
    extension_notes = models.TextField(
        blank=True,
        verbose_name=_("Extension Notes"),
        help_text=_("Admin notes about why extension was granted."),
    )
 
    # ── Warning tracking ──────────────────────────────────────────────
    expiry_warning_sent = models.BooleanField(
        default=False,
        verbose_name=_("7-Day Warning Email Sent"),
    )
 
    expiry_warning_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Warning Sent At"),
    )
 
    # ── Audit ─────────────────────────────────────────────────────────
    assigned_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_subscriptions",
        verbose_name=_("Assigned By"),
    )
 
    notes = models.TextField(
        blank=True,
        verbose_name=_("Notes"),
    )
 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name        = _("Company Subscription")
        verbose_name_plural = _("Company Subscriptions")
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status"], name="sub_company_status_idx"),
            models.Index(fields=["expiry_date"],       name="sub_expiry_date_idx"),
            models.Index(fields=["status"],            name="sub_status_idx"),
        ]
        constraints = [
            # Only one ACTIVE or TRIAL subscription per company at a time
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(status__in=["active", "trial"]),
                name="unique_active_subscription_per_company",
            ),
        ]
 
    def __str__(self):
        return (
            f"{self.company.business_name} → {self.plan.name} "
            f"[{self.get_status_display()}] expires {self.expiry_date}"
        )
 
    # ── Properties ────────────────────────────────────────────────────
 
    @property
    def is_active(self) -> bool:
        """True if subscription is usable right now."""
        return (
            self.status in (self.Status.ACTIVE, self.Status.TRIAL)
            and self.expiry_date >= timezone.now().date()
        )
 
    @property
    def days_remaining(self) -> int:
        """Days until expiry. Negative means already expired."""
        delta = self.expiry_date - timezone.now().date()
        return delta.days
 
    @property
    def is_expiring_soon(self) -> bool:
        """True if expiring within 7 days."""
        return 0 <= self.days_remaining <= 7
 
    # ── Limit checks ──────────────────────────────────────────────────
 
    def check_product_limit(self) -> tuple[bool, str]:
        """
        Returns (can_add, reason).
        Called before creating a new product.
        """
        if self.plan.is_unlimited("max_products"):
            return True, ""
        current = self.company.products.filter(is_active=True).count()
        if current >= self.plan.max_products:
            return False, (
                f"Product limit reached. Your {self.plan.name} plan allows "
                f"{self.plan.max_products} products. "
                f"You currently have {current}. "
                f"Upgrade your plan to add more products."
            )
        return True, ""
 
    def check_user_limit(self) -> tuple[bool, str]:
        """
        Returns (can_add, reason).
        Called before creating a new staff user.
        Does not count Owner.
        """
        if self.plan.is_unlimited("max_users"):
            return True, ""
        from users.models import User
        current = User.objects.filter(
            company=self.company,
            role__in=["manager", "cashier", "salesperson"],
            status="active",
        ).count()
        if current >= self.plan.max_users:
            return False, (
                f"Staff user limit reached. Your {self.plan.name} plan allows "
                f"{self.plan.max_users} staff users. "
                f"You currently have {current}. "
                f"Upgrade your plan to add more users."
            )
        return True, ""
 
    def check_customer_limit(self) -> tuple[bool, str]:
        """Returns (can_add, reason). Called before creating a new customer."""
        if self.plan.is_unlimited("max_customers"):
            return True, ""
        current = self.company.customers.filter(
            is_active=True, is_walk_in=False
        ).count()
        if current >= self.plan.max_customers:
            return False, (
                f"Customer limit reached. Your {self.plan.name} plan allows "
                f"{self.plan.max_customers} customers. "
                f"You currently have {current}. "
                f"Upgrade your plan to add more customers."
            )
        return True, ""
 
    def check_sales_limit(self) -> tuple[bool, str]:
        """Returns (can_add, reason). Called before completing a sale."""
        if self.plan.is_unlimited("max_sales_per_month"):
            return True, ""
        from pos.models import Sale, SaleStatus
        from django.utils import timezone
        now     = timezone.now()
        current = Sale.objects.filter(
            company      = self.company,
            status       = SaleStatus.COMPLETED,
            completed_at__year  = now.year,
            completed_at__month = now.month,
        ).count()
        if current >= self.plan.max_sales_per_month:
            return False, (
                f"Monthly sales limit reached. Your {self.plan.name} plan allows "
                f"{self.plan.max_sales_per_month} sales per month. "
                f"You have completed {current} this month. "
                f"Upgrade your plan to process more sales."
            )
        return True, ""
 
    # ── Actions ───────────────────────────────────────────────────────
 
    def extend(self, days: int, notes: str = "", extended_by=None):
        """
        Admin manually extends subscription by N days.
        Updates expiry_date and logs extension.
        """
        from datetime import timedelta
        self.expiry_date       += timedelta(days=days)
        self.extended_by_days  += days
        self.extension_notes   += (
            f"\n[{timezone.now().date()}] Extended by {days} days"
            f" by {extended_by.email if extended_by else 'Admin'}."
            f" Notes: {notes}"
        )
        # Reactivate if was expired
        if self.status == self.Status.EXPIRED:
            self.status = self.Status.ACTIVE
        self.save()
 
        # Log to history
        SubscriptionHistory.objects.create(
            company     = self.company,
            action      = SubscriptionHistory.Action.EXTENDED,
            plan        = self.plan,
            performed_by = extended_by,
            notes       = f"Extended by {days} days. {notes}",
        )
 
    def expire(self):
        """Mark subscription as expired and block company POS access."""
        self.status = self.Status.EXPIRED
        self.save(update_fields=["status", "updated_at"])
 
        # Update company subscription_status field
        self.company.subscription_status = "expired"
        self.company.save(update_fields=["subscription_status", "updated_at"])
 
        SubscriptionHistory.objects.create(
            company = self.company,
            action  = SubscriptionHistory.Action.EXPIRED,
            plan    = self.plan,
            notes   = "Auto-expired by system.",
        )
 
 
# ---------------------------------------------------------------------------
# SubscriptionHistory
# ---------------------------------------------------------------------------
 
class SubscriptionHistory(models.Model):
    """
    Audit trail of every subscription change.
    Never deleted — permanent record.
    """
 
    class Action(models.TextChoices):
        CREATED   = "created",   _("Plan Assigned")
        UPGRADED  = "upgraded",  _("Plan Upgraded")
        DOWNGRADED = "downgraded", _("Plan Downgraded")
        EXTENDED  = "extended",  _("Subscription Extended")
        EXPIRED   = "expired",   _("Subscription Expired")
        SUSPENDED = "suspended", _("Account Suspended")
        REACTIVATED = "reactivated", _("Account Reactivated")
        CANCELLED = "cancelled", _("Subscription Cancelled")
 
    company      = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="subscription_history",
    )
    plan         = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
    )
    action       = models.CharField(max_length=15, choices=Action.choices)
    performed_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    notes        = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        verbose_name        = _("Subscription History")
        verbose_name_plural = _("Subscription History")
        ordering            = ["-created_at"]
 
    def __str__(self):
        return f"{self.company.business_name} — {self.get_action_display()} — {self.created_at.date()}"
