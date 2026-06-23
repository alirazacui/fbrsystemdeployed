"""
companies/models.py

Company is the tenant record. Every client business that buys a POS or
Digital Invoicing licence from us gets one Company record. All non-platform
users (Owner, Manager, Cashier, Salesperson) belong to exactly one Company.

Platform users (Admin, Admin Staff) do NOT belong to any Company.

Changes from v1
---------------
1. FBR Business Nature — kept as ArrayField (multi-checkbox in admin)
   but FBRBusinessNature choices updated to match IRIS exactly
   (removed Manufacturer — not in IRIS list shown in screenshot)

2. FBR Sector — values updated to match IRIS dropdown exactly
   (Wholesale/Retails, Cement or Concrete Blocks, etc.)

3. Modules restructured to match benchmark screenshot:
   - SALES & FBR: Invoices, FBR DI, Customers — all three FORCED (cannot be disabled)
   - MULTI-LOCATION: Multi-branch, Terminals & cash sessions, Inventory, Warehousing
   - OPERATIONS: Returns, Debit/credit notes (split from returns), Manual FBR amendments,
                 Cheques + bank transfers, Customer-facing display, Hardware integrations
   - RESTAURANT: Single toggle (gates ALL restaurant features — dine-in, tables, KDS, etc.)
   - INSIGHTS: Basic reports, Advanced reports, Audit log

4. FBR Sandbox Scenarios — replaced ArrayField with 28 individual BooleanFields
   (SN001–SN028) so admin ticks checkboxes exactly like benchmark shows,
   instead of typing a free-text list

5. FORCED_MODULES class constant added — these three can never be turned off

6. clean() added — enforces forced modules cannot be set to False

7. Import path fixed: 'users.models' not 'apps.users.models'
"""

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from config.storage_backends import company_logo_upload_path


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class BusinessMode(models.TextChoices):
    POS_ONLY = "pos_only", _("POS Only")
    DI_ONLY  = "di_only",  _("Digital Invoicing Only")
    BOTH     = "both",     _("POS + Digital Invoicing")


class FBRBusinessNature(models.TextChoices):
    """
    Matches IRIS checkboxes exactly (screenshot 2).
    Multi-select — stored as ArrayField.
    """
    MANUFACTURER     = "manufacturer",     _("Manufacturer")
    IMPORTER         = "importer",         _("Importer")
    EXPORTER         = "exporter",         _("Exporter")
    DISTRIBUTOR      = "distributor",      _("Distributor")
    WHOLESALER       = "wholesaler",       _("Wholesaler")
    RETAILER         = "retailer",         _("Retailer")
    SERVICE_PROVIDER = "service_provider", _("Service Provider")
    OTHER            = "other",            _("Other")


class FBRSector(models.TextChoices):
    """
    Matches IRIS dropdown exactly (screenshot 2).
    Single select — one value per company.
    """
    POTASSIUM_CHLORATE   = "potassium_chlorate",   _("Potassium Chlorate")
    CEMENT_CONCRETE      = "cement_concrete",       _("Cement or Concrete Blocks")
    MOBILE               = "mobile",                _("Mobile")
    WHOLESALE_RETAILS    = "wholesale_retails",     _("Wholesale / Retails")
    PHARMACEUTICALS      = "pharmaceuticals",       _("Pharmaceuticals")
    CNG_STATIONS         = "cng_stations",          _("CNG Stations")
    AUTOMOBILE           = "automobile",            _("Automobile")
    SERVICES             = "services",              _("Services")
    GAS_DISTRIBUTION     = "gas_distribution",      _("Gas Distribution")
    ELECTRICITY          = "electricity",           _("Electricity Distribution")
    PETROLEUM            = "petroleum",             _("Petroleum")
    TELECOM              = "telecom",               _("Telecom")
    TEXTILE              = "textile",               _("Textile")
    FMCG                 = "fmcg",                  _("FMCG")
    STEEL                = "steel",                 _("Steel")
    ALL_OTHER            = "all_other",             _("All Other Sectors")


class BusinessVertical(models.TextChoices):
    """
    Our own internal classification — drives POS UI/features shown.
    Completely independent of FBR Sector.
    """
    GROCERY       = "grocery",       _("Grocery Store")
    GENERAL_STORE = "general_store", _("General Store")
    RESTAURANT    = "restaurant",    _("Restaurant / F&B")
    PHARMACY      = "pharmacy",      _("Pharmacy")
    ELECTRONICS   = "electronics",   _("Electronics")
    CLOTHING      = "clothing",      _("Clothing / Apparel")
    WHOLESALE     = "wholesale",     _("Wholesale")
    OTHER         = "other",         _("Other")


class SubscriptionPlan(models.TextChoices):
    TRIAL   = "trial",   _("Trial")
    STARTER = "starter", _("Starter")
    PRO     = "pro",     _("Pro")
    PREMIUM = "premium", _("Premium")


class SubscriptionStatus(models.TextChoices):
    ACTIVE    = "active",    _("Active")
    TRIAL     = "trial",     _("Trial")
    EXPIRED   = "expired",   _("Expired")
    SUSPENDED = "suspended", _("Suspended")
    CANCELLED = "cancelled", _("Cancelled")


# ---------------------------------------------------------------------------
# All 28 FBR sandbox scenarios — complete list from PRAL documentation
# ---------------------------------------------------------------------------

FBR_SCENARIOS = [
    ("sn001", "SN001 · Standard Rate — Registered Buyer"),
    ("sn002", "SN002 · Standard Rate — Unregistered Buyer"),
    ("sn003", "SN003 · Steel Melted"),
    ("sn004", "SN004 · Steel Scrap by Ship Breaker"),
    ("sn005", "SN005 · Reduced Rate — Registered Buyer"),
    ("sn006", "SN006 · Exempted Goods"),
    ("sn007", "SN007 · Zero Rated Goods"),
    ("sn008", "SN008 · Third Schedule Goods"),
    ("sn009", "SN009 · Purchase from Cotton Grower"),
    ("sn010", "SN010 · Telecom Services by Mobile Operators"),
    ("sn011", "SN011 · Steel via Toll Manufacturing"),
    ("sn012", "SN012 · Petroleum Products"),
    ("sn013", "SN013 · Electricity to Retailers"),
    ("sn014", "SN014 · Gas to CNG Stations"),
    ("sn015", "SN015 · Mobile Phones"),
    ("sn016", "SN016 · Processing / Conversion of Goods"),
    ("sn017", "SN017 · Goods (FED in ST Mode)"),
    ("sn018", "SN018 · Services (FED in ST Mode)"),
    ("sn019", "SN019 · Services (ICT Ordinance)"),
    ("sn020", "SN020 · Electric Vehicles"),
    ("sn021", "SN021 · Cement / Concrete Block"),
    ("sn022", "SN022 · Potassium Chloride"),
    ("sn023", "SN023 · SNNG Sale"),
    ("sn024", "SN024 · Goods per SC004"),
    ("sn025", "SN025 · Goods per SRO2971"),
    ("sn026", "SN026 · Standard Rate — End Consumer (Retailer)"),
    ("sn027", "SN027 · Third Schedule — End Consumer (Retailer)"),
    ("sn028", "SN028 · Reduced Rate — End Consumer (Retailer)"),
]


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------

class Company(models.Model):
    """
    One row = one client business (tenant).

    Sections
    --------
    1.  Core business identity
    2.  FBR / regulatory info
    3.  Business classification (our own — vertical)
    4.  Contact & branding
    5.  Subscription
    6.  Feature modules (hard ceiling for all user permissions)
    7.  FBR sandbox / onboarding state
    8.  FBR sandbox scenarios (SN001–SN028, individual checkboxes)
    9.  Internal admin metadata
    10. Timestamps & status
    """

    # Modules that are FORCED — can never be disabled for any company.
    # Enforced in clean() and in Django admin (read-only checkboxes).
    FORCED_MODULES = [
        "module_invoices",
        "module_fbr_di",
        "module_customer_db",
    ]

    # ------------------------------------------------------------------
    # 1. Core business identity
    # ------------------------------------------------------------------

    business_name = models.CharField(
        max_length=255,
        verbose_name=_("Business Name"),
    )

    ntn = models.CharField(
        max_length=15,
        unique=True,
        verbose_name=_("NTN"),
        help_text=_("National Tax Number — 7 digits (e.g. 1234567)"),
    )

    strn = models.CharField(
        max_length=17,
        unique=True,
        blank=True,
        null=True,
        verbose_name=_("STRN"),
        help_text=_("Sales Tax Registration Number — 13 digits"),
    )

    owner_cnic = models.CharField(
        max_length=15,
        verbose_name=_("Owner CNIC"),
        help_text=_("Format: 00000-0000000-0 (13 digits with dashes)"),
    )

    # ------------------------------------------------------------------
    # 2. FBR / regulatory info
    # ------------------------------------------------------------------

    business_mode = models.CharField(
        max_length=20,
        choices=BusinessMode.choices,
        default=BusinessMode.POS_ONLY,
        verbose_name=_("Business Mode"),
        help_text=_(
            "Which product(s) this company has licensed. "
            "Does NOT auto-set any modules — admin configures modules independently."
        ),
    )

    fbr_business_nature = ArrayField(
        base_field=models.CharField(
            max_length=30,
            choices=FBRBusinessNature.choices,
        ),
        default=list,
        blank=True,
        verbose_name=_("FBR Business Nature"),
        help_text=_(
            "One or more FBR-defined business natures. "
            "Required before submitting invoices to PRAL."
        ),
    )

    fbr_sector = models.CharField(
        max_length=30,
        choices=FBRSector.choices,
        blank=True,
        null=True,
        verbose_name=_("FBR Sector"),
        help_text=_(
            "Exactly one sector. Combined with Business Nature to determine "
            "eligible sandbox scenarios inside IRIS."
        ),
    )

    # ------------------------------------------------------------------
    # 3. Business classification (our own)
    # ------------------------------------------------------------------

    vertical = models.CharField(
        max_length=30,
        choices=BusinessVertical.choices,
        default=BusinessVertical.GENERAL_STORE,
        verbose_name=_("Business Vertical"),
        help_text=_(
            "Controls which POS features/UI this company sees. "
            "Independent of FBR Sector."
        ),
    )

    # ------------------------------------------------------------------
    # 4. Contact & branding
    # ------------------------------------------------------------------

    logo = models.ImageField(
    upload_to=company_logo_upload_path,
    storage=None,    # uses default S3 storage from settings
    blank=True,
    null=True,
    verbose_name=_("Company Logo"),
  ) 

    address = models.TextField(
        verbose_name=_("Business Address"),
        help_text=_("Full address in a single field (street, city, province, postal code)."),
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Business Phone"),
    )

    email = models.EmailField(
        blank=True,
        verbose_name=_("Business Email"),
    )

    website_url = models.URLField(
        blank=True,
        verbose_name=_("Website URL"),
    )

    # ------------------------------------------------------------------
    # 5. Subscription
    # ------------------------------------------------------------------

    subscription_plan = models.CharField(
        max_length=20,
        choices=SubscriptionPlan.choices,
        default=SubscriptionPlan.TRIAL,
        verbose_name=_("Subscription Plan"),
    )

    subscription_status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIAL,
        verbose_name=_("Subscription Status"),
    )

    subscription_start_date = models.DateField(
        blank=True, null=True,
        verbose_name=_("Subscription Start Date"),
    )

    subscription_expiry_date = models.DateField(
        blank=True, null=True,
        verbose_name=_("Subscription Expiry Date"),
    )

    next_billing_date = models.DateField(
        blank=True, null=True,
        verbose_name=_("Next Billing Date"),
    )

    # ------------------------------------------------------------------
    # 6. Feature modules
    #
    # Hard ceiling for ALL users in this company.
    # Platform Admin bypasses this ceiling entirely.
    # Owner gets everything enabled here — auto-granted by signal.
    #
    # Grouped exactly as benchmark screenshot shows:
    #   SALES & FBR  |  MULTI-LOCATION  |  OPERATIONS  |  RESTAURANT  |  INSIGHTS
    #
    # FORCED modules (cannot be disabled):
    #   module_invoices, module_fbr_di, module_customer_db
    # ------------------------------------------------------------------

    # ── SALES & FBR (all three FORCED) ──────────────────────────────
    module_invoices = models.BooleanField(
        default=True,
        verbose_name=_("Invoices"),
        help_text=_(
            "Create, list, and manage invoices. "
            "FORCED — cannot be disabled. This is the core product."
        ),
    )

    module_fbr_di = models.BooleanField(
        default=True,
        verbose_name=_("FBR Digital Invoicing"),
        help_text=_(
            "Submit invoices to PRAL and store FBR tokens. "
            "FORCED — FBR submission is the primary value of the platform."
        ),
    )

    module_customer_db = models.BooleanField(
        default=True,
        verbose_name=_("Customers"),
        help_text=_(
            "Customer database with NTN/CNIC. "
            "FORCED — FBR registered-buyer scenarios require a customer record with NTN."
        ),
    )

    # ── MULTI-LOCATION ───────────────────────────────────────────────
    module_multi_branch = models.BooleanField(
        default=False,
        verbose_name=_("Multi-Branch"),
        help_text=_(
            "Multiple physical locations. When disabled the tenant "
            "operates from a single implicit branch. "
            "Reserved for future use — not wired to branch-creation logic yet."
        ),
    )

    module_terminals_cash_sessions = models.BooleanField(
        default=False,
        verbose_name=_("Terminals & Cash Sessions"),
        help_text=_("POS terminal registration and cashier shift open/close flow."),
    )

    module_inventory = models.BooleanField(
        default=False,
        verbose_name=_("Inventory Tracking"),
        help_text=_("Stock levels, movements, adjustments, transfers, stock audits."),
    )

    module_warehousing = models.BooleanField(
        default=False,
        verbose_name=_("Warehouses (Digital Invoicing)"),
        help_text=_(
            "Per-warehouse stock for Digital-Invoicing tenants: "
            "godowns under a branch, opening balance + stock-in per warehouse, "
            "and warehouse-keyed sale deduction."
        ),
    )

    # ── OPERATIONS ───────────────────────────────────────────────────
    module_returns = models.BooleanField(
        default=False,
        verbose_name=_("Returns"),
        help_text=_("Customer returns workflow."),
    )

    module_debit_credit_notes = models.BooleanField(
        default=False,
        verbose_name=_("Debit / Credit Notes"),
        help_text=_(
            "Issue follow-up notes against existing FBR-validated invoices "
            "for forgotten items or amendments."
        ),
    )

    module_fbr_amendments = models.BooleanField(
        default=False,
        verbose_name=_("Manual FBR Amendments"),
        help_text=_(
            "Phase 4 manual-amendment workflow including Annexure-C linkage."
        ),
    )

    module_cheque_bank_transfer = models.BooleanField(
        default=False,
        verbose_name=_("Cheques + Bank Transfers"),
        help_text=_("Beyond cash and card — cheques, bank refs, wallet payment tracking."),
    )

    module_customer_display = models.BooleanField(
        default=False,
        verbose_name=_("Customer-Facing Display"),
        help_text=_(
            "The second-monitor display showing the running cart "
            "and post-sale thank-you."
        ),
    )

    module_hardware_integration = models.BooleanField(
        default=False,
        verbose_name=_("Hardware Integrations"),
        help_text=_("Thermal printer, barcode scanner, cash drawer kick."),
    )

    # ── RESTAURANT ───────────────────────────────────────────────────
    module_restaurant_fnb = models.BooleanField(
        default=False,
        verbose_name=_("Restaurant / F&B"),
        help_text=_(
            "Single toggle that gates ALL restaurant features: "
            "dine-in / takeaway / delivery orders, tables + floor map, "
            "menu modifiers (add-ons / sizes), kitchen tickets (KDS) + KDOC. "
            "Gates the restaurant API; pair with the restaurant vertical to surface the UI."
        ),
    )

    # ── INSIGHTS ─────────────────────────────────────────────────────
    module_basic_reports = models.BooleanField(
        default=True,
        verbose_name=_("Reports — Basic"),
        help_text=_("Daily summary, today's sales, simple lookups."),
    )

    module_advanced_reports = models.BooleanField(
        default=False,
        verbose_name=_("Reports — Advanced"),
        help_text=_("Scheduled reports, period comparisons, exports."),
    )

    module_audit_logs = models.BooleanField(
        default=False,
        verbose_name=_("Audit Log"),
        help_text=_("Six-year-retention audit trail viewer."),
    )

    # ------------------------------------------------------------------
    # 7. FBR sandbox / onboarding state
    # ------------------------------------------------------------------

    fbr_sandbox_token = models.TextField(
        blank=True,
        verbose_name=_("FBR Sandbox Token"),
        help_text=_(
            "Issued by IRIS after IP whitelisting is accepted. "
            "Used for test invoice submission."
        ),
    )

    fbr_production_token = models.TextField(
        blank=True,
        verbose_name=_("FBR Production Token"),
        help_text=_(
            "Issued automatically by IRIS once ALL assigned sandbox scenarios "
            "are cleared. Required before any live invoice can be submitted."
        ),
    )

    fbr_test_buyer_ntn = models.CharField(
        max_length=15,
        blank=True,
        verbose_name=_("FBR Test Buyer NTN"),
        help_text=_(
            "Required only if this tenant's assigned scenarios include SN001 or SN005 "
            "(registered buyer scenarios). "
            "PRAL's own test NTN is NOT pre-registered — enter the actual test NTN here."
        ),
    )

    fbr_sandbox_complete = models.BooleanField(
        default=False,
        verbose_name=_("Sandbox Testing Complete"),
        help_text=_(
            "Set to True automatically once all assigned scenarios are cleared "
            "and a production token is issued."
        ),
    )

    # IP whitelisting — FBR hard limit is 3 IPs
    fbr_ip_1 = models.GenericIPAddressField(
        blank=True, null=True, verbose_name=_("Whitelisted IP 1")
    )
    fbr_ip_2 = models.GenericIPAddressField(
        blank=True, null=True, verbose_name=_("Whitelisted IP 2")
    )
    fbr_ip_3 = models.GenericIPAddressField(
        blank=True, null=True, verbose_name=_("Whitelisted IP 3")
    )

    # CRM credentials for raising support cases with PRAL DI CRM
    fbr_crm_user_id = models.EmailField(
        blank=True,
        verbose_name=_("FBR CRM User ID (Email)"),
        help_text=_(
            "Email registered as Technical Contact Person in IRIS Technical Details. "
            "Used to log into dicrm.pral.com.pk"
        ),
    )

    # ------------------------------------------------------------------
    # 8. FBR sandbox scenarios — SN001 to SN028
    #
    # Individual BooleanField per scenario (not an ArrayField).
    # Admin ticks exactly which scenarios IRIS assigned to this tenant.
    # Needed only for sandbox onboarding — once fbr_sandbox_complete=True
    # and a production token is issued, these are historical record only.
    # ------------------------------------------------------------------

    fbr_scenario_sn001 = models.BooleanField(default=False, verbose_name=_("SN001 · Standard Rate — Registered Buyer"))
    fbr_scenario_sn002 = models.BooleanField(default=False, verbose_name=_("SN002 · Standard Rate — Unregistered Buyer"))
    fbr_scenario_sn003 = models.BooleanField(default=False, verbose_name=_("SN003 · Steel Melted"))
    fbr_scenario_sn004 = models.BooleanField(default=False, verbose_name=_("SN004 · Steel Scrap by Ship Breaker"))
    fbr_scenario_sn005 = models.BooleanField(default=False, verbose_name=_("SN005 · Reduced Rate — Registered Buyer"))
    fbr_scenario_sn006 = models.BooleanField(default=False, verbose_name=_("SN006 · Exempted Goods"))
    fbr_scenario_sn007 = models.BooleanField(default=False, verbose_name=_("SN007 · Zero Rated Goods"))
    fbr_scenario_sn008 = models.BooleanField(default=False, verbose_name=_("SN008 · Third Schedule Goods"))
    fbr_scenario_sn009 = models.BooleanField(default=False, verbose_name=_("SN009 · Purchase from Cotton Grower"))
    fbr_scenario_sn010 = models.BooleanField(default=False, verbose_name=_("SN010 · Telecom Services by Mobile Operators"))
    fbr_scenario_sn011 = models.BooleanField(default=False, verbose_name=_("SN011 · Steel via Toll Manufacturing"))
    fbr_scenario_sn012 = models.BooleanField(default=False, verbose_name=_("SN012 · Petroleum Products"))
    fbr_scenario_sn013 = models.BooleanField(default=False, verbose_name=_("SN013 · Electricity to Retailers"))
    fbr_scenario_sn014 = models.BooleanField(default=False, verbose_name=_("SN014 · Gas to CNG Stations"))
    fbr_scenario_sn015 = models.BooleanField(default=False, verbose_name=_("SN015 · Mobile Phones"))
    fbr_scenario_sn016 = models.BooleanField(default=False, verbose_name=_("SN016 · Processing / Conversion of Goods"))
    fbr_scenario_sn017 = models.BooleanField(default=False, verbose_name=_("SN017 · Goods (FED in ST Mode)"))
    fbr_scenario_sn018 = models.BooleanField(default=False, verbose_name=_("SN018 · Services (FED in ST Mode)"))
    fbr_scenario_sn019 = models.BooleanField(default=False, verbose_name=_("SN019 · Services (ICT Ordinance)"))
    fbr_scenario_sn020 = models.BooleanField(default=False, verbose_name=_("SN020 · Electric Vehicles"))
    fbr_scenario_sn021 = models.BooleanField(default=False, verbose_name=_("SN021 · Cement / Concrete Block"))
    fbr_scenario_sn022 = models.BooleanField(default=False, verbose_name=_("SN022 · Potassium Chloride"))
    fbr_scenario_sn023 = models.BooleanField(default=False, verbose_name=_("SN023 · SNNG Sale"))
    fbr_scenario_sn024 = models.BooleanField(default=False, verbose_name=_("SN024 · Goods per SC004"))
    fbr_scenario_sn025 = models.BooleanField(default=False, verbose_name=_("SN025 · Goods per SRO2971"))
    fbr_scenario_sn026 = models.BooleanField(default=False, verbose_name=_("SN026 · Standard Rate — End Consumer (Retailer)"))
    fbr_scenario_sn027 = models.BooleanField(default=False, verbose_name=_("SN027 · Third Schedule — End Consumer (Retailer)"))
    fbr_scenario_sn028 = models.BooleanField(default=False, verbose_name=_("SN028 · Reduced Rate — End Consumer (Retailer)"))

    # ------------------------------------------------------------------
    # 9. Internal admin metadata
    # ------------------------------------------------------------------

    account_manager = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Account Manager"),
        help_text=_("Name of the internal staff member responsible for this account."),
    )

    internal_notes = models.TextField(
        blank=True,
        verbose_name=_("Internal Notes"),
        help_text=_("Visible only to Admin/Admin Staff. Never shown in POS or client UI."),
    )

    tags = ArrayField(
        base_field=models.CharField(max_length=50),
        default=list,
        blank=True,
        verbose_name=_("Tags"),
        help_text=_("Free-form labels for filtering companies in the admin app (e.g. 'vip', 'cash-only')."),
    )

    # ------------------------------------------------------------------
    # 10. Timestamps & status
    # ------------------------------------------------------------------

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_(
            "Inactive companies cannot log into the POS. "
            "Deactivate instead of deleting — records are never hard-deleted."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True,     verbose_name=_("Updated At"))

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    class Meta:
        verbose_name        = _("Company")
        verbose_name_plural = _("Companies")
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["ntn"],                 name="company_ntn_idx"),
            models.Index(fields=["is_active"],           name="company_active_idx"),
            models.Index(fields=["subscription_status"], name="company_sub_status_idx"),
        ]

    def __str__(self):
        return f"{self.business_name} ({self.ntn})"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        """
        Enforce that FORCED modules can never be set to False.
        Called by Django admin and serializer validation.
        """
        errors = {}
        for field_name in self.FORCED_MODULES:
            if getattr(self, field_name) is False:
                errors[field_name] = _(
                    f"This module is forced and cannot be disabled. "
                    f"It is a core requirement of the platform."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Always enforce forced modules before saving."""
        for field_name in self.FORCED_MODULES:
            setattr(self, field_name, True)
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Convenience properties & methods
    # ------------------------------------------------------------------

    @property
    def owner(self):
        """
        Returns the single Owner user for this company.
        Local import avoids circular dependency at module level.
        Returns None if no owner has been created yet.
        """
        from users.models import User
        return User.objects.filter(company=self, role=User.Role.OWNER).first()

    @property
    def is_subscription_active(self):
        return self.subscription_status in (
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIAL,
        )

    def get_enabled_modules(self) -> list[str]:
        """
        Returns list of module field names that are currently True.
        Used by the permission system to enforce the company ceiling.

        Example: ['module_invoices', 'module_fbr_di', 'module_customer_db', 'module_basic_reports']
        """
        return [
            f.name
            for f in self._meta.get_fields()
            if f.name.startswith("module_") and getattr(self, f.name) is True
        ]

    def get_assigned_scenarios(self) -> list[str]:
        """
        Returns list of scenario codes (uppercase) that are ticked True.
        Example: ['SN001', 'SN005', 'SN026']
        Used by the FBR sandbox runner to know which scenarios to submit.
        """
        return [
            code.upper()
            for code, _ in FBR_SCENARIOS
            if getattr(self, f"fbr_scenario_{code}", False)
        ]