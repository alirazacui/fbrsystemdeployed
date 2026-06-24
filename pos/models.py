from django.db import models
from config.storage_backends import product_image_upload_path
# Create your models here.
"""
pos/models.py  — Phase 2: Products & Categories

Two models here:

  Category
  ────────
  Simple product grouping per company.
  e.g. "Beverages", "Dairy", "Electronics"

  Product
  ───────
  One row = one sellable item belonging to a company.

  Divided into sections:
    1. Identity & categorisation
    2. Pricing
    3. Barcode & unit
    4. FBR tax fields  ← from official PRAL DI API spec v1.3
    5. Inventory
    6. Status & timestamps

FBR item-level fields (from PRAL DI API Technical Specification v1.3)
──────────────────────────────────────────────────────────────────────
Required by FBR at invoice submission time:
  hsCode                        → hs_code
  productDescription            → name  (already on product)
  rate                          → tax_rate_percent
  uoM                           → unit_of_measure
  quantity                      → (from sale line, not product)
  valueSalesExcludingST         → (computed at sale time)
  salesTaxApplicable            → (computed at sale time)
  saleType                      → fbr_sale_type

Optional FBR fields stored at product level (defaults, overridable per sale):
  salesTaxWithheldAtSource      → fbr_sales_tax_withheld (default 0)
  furtherTax                    → fbr_further_tax (default 0)
  extraTax                      → fbr_extra_tax (default 0)
  fedPayable                    → fbr_fed_payable (default 0)
  fixedNotifiedValueOrRetailPrice → fbr_fixed_retail_price (default 0)
  sroScheduleNo                 → fbr_sro_schedule_no
  sroItemSerialNo               → fbr_sro_item_serial_no
  discount                      → fbr_default_discount (default 0)
  totalValues                   → (computed at sale time: quantity × unit price + tax)

Variant decision: simple products only for Phase 2.
Variants (size/colour/weight) will be added as a ProductVariant model in Phase 2b.
"""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class UnitOfMeasure(models.TextChoices):
    """
    Common UOM values from FBR reference API (/pdi/v1/uom).
    Admin can also type a custom value via fbr_uom_custom field.
    """
    NUMBERS_PIECES = "Numbers, pieces, units", _("Numbers / Pieces / Units")
    KG             = "KG",                    _("Kilogram (KG)")
    GRAM           = "Gram",                  _("Gram")
    LITRE          = "Litre",                 _("Litre")
    ML             = "ML",                    _("Millilitre (ML)")
    METRE          = "Metre",                 _("Metre")
    SQ_METRE       = "Square Metre",          _("Square Metre")
    KWH            = "KWH",                   _("Kilowatt Hour (KWH)")
    TON            = "Ton",                   _("Ton")
    DOZEN          = "Dozen",                 _("Dozen")
    PACK           = "Pack",                  _("Pack")
    BOX            = "Box",                   _("Box")
    SET            = "Set",                   _("Set")


class FBRSaleType(models.TextChoices):
    """
    Sale type values accepted by FBR DI API (saleType field).
    Determines which tax rules apply at invoice time.
    From PRAL DI API Technical Specification v1.3, Section 9.
    """
    STANDARD_RATE              = "Goods at standard rate (default)",         _("Standard Rate (Default)")
    GOODS_REDUCED_RATE         = "Goods at Reduced Rate",                    _("Goods at Reduced Rate")
    EXEMPT_GOODS               = "Exempt Goods",                             _("Exempt Goods")
    ZERO_RATED                 = "Goods at zero-rate",                       _("Zero Rated Goods")
    THIRD_SCHEDULE             = "3rd Schedule Goods",                       _("3rd Schedule Goods")
    STEEL_MELTING              = "Steel Melting and re-rolling",             _("Steel Melting & Re-rolling")
    SHIP_BREAKING              = "Ship breaking",                            _("Ship Breaking")
    COTTON_GINNERS             = "Cotton Ginners",                           _("Cotton Ginners")
    TELECOM_SERVICES           = "Telecommunication services",               _("Telecommunication Services")
    TOLL_MANUFACTURING         = "Toll Manufacturing",                       _("Toll Manufacturing")
    PETROLEUM_PRODUCTS         = "Petroleum Products",                       _("Petroleum Products")
    ELECTRICITY_RETAILERS      = "Electricity Supply to Retailers",          _("Electricity Supply to Retailers")
    GAS_CNG                    = "Gas to CNG stations",                      _("Gas to CNG Stations")
    MOBILE_PHONES              = "Mobile Phones",                            _("Mobile Phones")
    PROCESSING_CONVERSION      = "Processing/ Conversion of Goods",         _("Processing / Conversion of Goods")
    GOODS_FED_ST_MODE          = "Goods (FED in ST Mode)",                   _("Goods — FED in ST Mode")
    SERVICES_FED_ST_MODE       = "Services (FED in ST Mode)",                _("Services — FED in ST Mode")
    SERVICES                   = "Services",                                 _("Services")
    ELECTRIC_VEHICLE           = "Electric Vehicle",                         _("Electric Vehicle")
    CEMENT_CONCRETE            = "Cement /Concrete Block",                   _("Cement / Concrete Block")
    POTASSIUM_CHLORATE         = "Potassium Chlorate",                       _("Potassium Chlorate")
    CNG_SALES                  = "CNG Sales",                                _("CNG Sales")
    GOODS_SRO_297              = "Goods as per SRO.297(|)/2023",             _("Goods per SRO 297(I)/2023")
    NON_ADJUSTABLE             = "Non-Adjustable Supplies",                  _("Non-Adjustable Supplies (Drugs)")


class TaxRatePercent(models.TextChoices):
    """
    Common FBR tax rates.
    Stored as string to match FBR API format exactly (e.g. "18%").
    """
    ZERO        = "0%",   _("0% — Zero Rated / Exempt")
    ONE         = "1%",   _("1%")
    TWO         = "2%",   _("2%")
    THREE       = "3%",   _("3%")
    FIVE        = "5%",   _("5%")
    EIGHT       = "8%",   _("8%")
    TEN         = "10%",  _("10%")
    TWELVE      = "12%",  _("12%")
    THIRTEEN    = "13%",  _("13%")
    FIFTEEN     = "15%",  _("15%")
    SEVENTEEN   = "17%",  _("17%")
    EIGHTEEN    = "18%",  _("18% — Standard Rate")
    TWENTY      = "20%",  _("20%")
    TWENTY_FIVE = "25%",  _("25%")


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

class Category(models.Model):
    """
    Product grouping within a company.
    Each company manages its own categories independently.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="categories",
        verbose_name=_("Company"),
    )

    name = models.CharField(
        max_length=100,
        verbose_name=_("Category Name"),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = _("Category")
        verbose_name_plural = _("Categories")
        ordering            = ["name"]
        unique_together     = [("company", "name")]  # no duplicate names per company

    def __str__(self):
        return f"{self.name} ({self.company.business_name})"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class Product(models.Model):
    """
    One row = one sellable product belonging to a company.

    FBR tax fields are stored here as DEFAULTS.
    They can be overridden at the sale line level if needed
    (e.g. a one-time discount or special tax treatment).
    """

    # ------------------------------------------------------------------
    # 1. Identity & categorisation
    # ------------------------------------------------------------------

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name=_("Company"),
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
        verbose_name=_("Category"),
    )

    name = models.CharField(
        max_length=255,
        verbose_name=_("Product Name"),
        help_text=_("Maps to 'productDescription' in FBR invoice JSON."),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
    )

    image = models.ImageField(
    upload_to=product_image_upload_path,
    blank=True,
    null=True,
    verbose_name=_("Product Image"),
    )

    # ------------------------------------------------------------------
    # 2. Pricing
    # ------------------------------------------------------------------

    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("Selling Price (excl. tax)"),
        help_text=_(
            "Base selling price excluding sales tax. "
            "Maps to 'valueSalesExcludingST' in FBR JSON. "
            "Tax is calculated on top of this at sale time."
        ),
    )

    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
        verbose_name=_("Cost Price"),
        help_text=_("Purchase/cost price. Used for profit margin reporting. Not sent to FBR."),
    )

    # ------------------------------------------------------------------
    # 3. Barcode & unit
    # ------------------------------------------------------------------

    barcode = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Barcode"),
        help_text=_(
            "Optional. Supports EAN-13, UPC-A, Code 128, QR, etc. "
            "Used by barcode scanner on POS terminal."
        ),
    )

    sku = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("SKU"),
        help_text=_("Internal stock keeping unit code. Optional but recommended."),
    )

    unit_of_measure = models.CharField(
        max_length=50,
        choices=UnitOfMeasure.choices,
        default=UnitOfMeasure.NUMBERS_PIECES,
        verbose_name=_("Unit of Measure (UoM)"),
        help_text=_(
            "Maps to 'uoM' in FBR invoice JSON. "
            "Must match FBR reference values from /pdi/v1/uom."
        ),
    )

    # ------------------------------------------------------------------
    # 4. FBR tax fields
    #
    # These are stored at product level as defaults.
    # The invoice generator reads these when building the FBR JSON payload.
    # All field names map directly to FBR DI API item fields.
    # ------------------------------------------------------------------

    hs_code = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("HS Code"),
        help_text=_(
            "Harmonized System code. REQUIRED by FBR for manufacturer-cum-retailer. "
            "Format: XXXX.XXXX (e.g. 0101.2100). "
            "Maps to 'hsCode' in FBR invoice JSON."
        ),
    )

    fbr_sale_type = models.CharField(
        max_length=80,
        choices=FBRSaleType.choices,
        default=FBRSaleType.STANDARD_RATE,
        verbose_name=_("FBR Sale Type"),
        help_text=_(
            "Determines which tax rules apply. "
            "Maps to 'saleType' in FBR invoice JSON. "
            "Must match exactly the string FBR expects."
        ),
    )

    tax_rate_percent = models.CharField(
        max_length=10,
        choices=TaxRatePercent.choices,
        default=TaxRatePercent.EIGHTEEN,
        verbose_name=_("Tax Rate"),
        help_text=_(
            "Sales tax rate. Maps to 'rate' in FBR invoice JSON. "
            "Use 0% for exempt or zero-rated goods."
        ),
    )

    fbr_fixed_retail_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Fixed / Notified Value or Retail Price"),
        help_text=_(
            "For 3rd schedule goods with a fixed retail price. "
            "Maps to 'fixedNotifiedValueOrRetailPrice' in FBR JSON. "
            "Leave 0 for most products."
        ),
    )

    fbr_sales_tax_withheld = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Sales Tax Withheld at Source"),
        help_text=_(
            "For withholding agent scenarios. "
            "Maps to 'salesTaxWithheldAtSource' in FBR JSON. "
            "Leave 0 for normal retail sales."
        ),
    )

    fbr_further_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Further Tax"),
        help_text=_(
            "Additional tax on sales to unregistered buyers (where applicable). "
            "Maps to 'furtherTax' in FBR JSON."
        ),
    )

    fbr_extra_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Extra Tax"),
        help_text=_(
            "Applicable for certain sectors (e.g. steel, petroleum). "
            "Maps to 'extraTax' in FBR JSON. Leave 0 for most products."
        ),
    )

    fbr_fed_payable = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Federal Excise Duty (FED) Payable"),
        help_text=_(
            "Federal excise duty. Applicable for specific goods (tobacco, beverages, etc.). "
            "Maps to 'fedPayable' in FBR JSON."
        ),
    )

    fbr_default_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Default Discount"),
        help_text=_(
            "Default per-item discount amount. Can be overridden at sale time. "
            "Maps to 'discount' in FBR JSON."
        ),
    )

    fbr_sro_schedule_no = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("SRO Schedule No."),
        help_text=_(
            "Statutory Regulatory Order schedule number. "
            "Required for SRO-based sale types (SN024, SN025). "
            "Maps to 'sroScheduleNo' in FBR JSON."
        ),
    )

    fbr_sro_item_serial_no = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("SRO Item Serial No."),
        help_text=_(
            "Item serial number within the SRO schedule. "
            "Maps to 'sroItemSerialNo' in FBR JSON."
        ),
    )

    # ------------------------------------------------------------------
    # 5. Inventory
    # ------------------------------------------------------------------

    track_inventory = models.BooleanField(
        default=False,
        verbose_name=_("Track Inventory"),
        help_text=_(
            "If True, stock level is tracked and decremented on each sale. "
            "Only meaningful if company has module_inventory=True."
        ),
    )

    current_stock = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Current Stock"),
        help_text=_(
            "Current stock quantity. Decremented by sales, incremented by stock-ins. "
            "Only tracked if track_inventory=True."
        ),
    )

    low_stock_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Low Stock Threshold"),
        help_text=_(
            "Alert when current_stock falls below this value. "
            "Set to 0 to disable low-stock alerts."
        ),
    )

    # ------------------------------------------------------------------
    # 6. Status & timestamps
    # ------------------------------------------------------------------

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Inactive products do not appear in the POS product search."),
    )

    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_products",
        verbose_name=_("Created By"),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True,     verbose_name=_("Updated At"))

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    class Meta:
        verbose_name        = _("Product")
        verbose_name_plural = _("Products")
        ordering            = ["name"]
        indexes = [
            models.Index(fields=["company", "is_active"], name="product_company_active_idx"),
            models.Index(fields=["barcode"],              name="product_barcode_idx"),
            models.Index(fields=["sku"],                  name="product_sku_idx"),
            models.Index(fields=["hs_code"],              name="product_hs_code_idx"),
        ]
        constraints = [
            # Barcode must be unique per company (not globally — two companies can have same barcode)
            models.UniqueConstraint(
                fields=["company", "barcode"],
                condition=models.Q(barcode__gt=""),   # only when barcode is not empty
                name="unique_barcode_per_company",
            ),
            # SKU must be unique per company
            models.UniqueConstraint(
                fields=["company", "sku"],
                condition=models.Q(sku__gt=""),
                name="unique_sku_per_company",
            ),
        ]

    def __str__(self):
        return f"{self.name} [{self.company.business_name}]"

    # ------------------------------------------------------------------
    # FBR helpers — called by invoice generator in Phase 3
    # ------------------------------------------------------------------

    def get_fbr_item_payload(self, quantity: float, override_discount: float = None) -> dict:
        """
        Returns the FBR DI API JSON payload for this product as a sale line item.

        Called by the invoice generator when building the JSON to POST to:
        https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata

        Args:
            quantity: Number of units sold
            override_discount: Optional per-sale discount (overrides product default)

        Returns:
            dict matching FBR item JSON structure
        """
        unit_price    = float(self.selling_price)
        value_excl_st = round(unit_price * quantity, 2)
        tax_rate_val  = float(self.tax_rate_percent.replace("%", "")) / 100
        sales_tax     = round(value_excl_st * tax_rate_val, 2)
        total_value   = round(value_excl_st + sales_tax, 2)
        discount      = float(override_discount if override_discount is not None else self.fbr_default_discount)

        return {
            "hsCode":                          self.hs_code or "",
            "productDescription":              self.name,
            "rate":                            self.tax_rate_percent,
            "uoM":                             self.unit_of_measure,
            "quantity":                        quantity,
            "valueSalesExcludingST":           value_excl_st,
            "fixedNotifiedValueOrRetailPrice": float(self.fbr_fixed_retail_price),
            "salesTaxApplicable":              sales_tax,
            "salesTaxWithheldAtSource":        float(self.fbr_sales_tax_withheld),
            "extraTax":                        float(self.fbr_extra_tax) or "",
            "furtherTax":                      float(self.fbr_further_tax),
            "sroScheduleNo":                   self.fbr_sro_schedule_no or "",
            "sroItemSerialNo":                 self.fbr_sro_item_serial_no or "",
            "fedPayable":                      float(self.fbr_fed_payable),
            "discount":                        discount,
            "totalValues":                     total_value,
            "saleType":                        self.fbr_sale_type,
        }

    @property
    def is_low_stock(self) -> bool:
        if not self.track_inventory or self.low_stock_threshold == 0:
            return False
        return self.current_stock <= self.low_stock_threshold
    

"""
pos/customer_models.py

Customer model for the POS system.

Every sale can be linked to a customer. For FBR Digital Invoicing,
customer records with NTN/CNIC are REQUIRED for registered buyer
scenarios (SN001, SN005 etc). The module_customer_db is FORCED on
every company for exactly this reason.

FBR buyer fields required at invoice time
──────────────────────────────────────────
  buyerNTNCNIC          → ntn_cnic
  buyerBusinessName     → name
  buyerProvince         → province
  buyerAddress          → address
  buyerRegistrationType → registration_type  ("Registered" / "Unregistered")

NTN vs CNIC
───────────
  Business customers (companies)  → NTN  (7 or 9 digits)
  Individual customers            → CNIC (13 digits)
  Walk-in / anonymous             → use a single shared "walk-in" record per company
                                    with a dummy NTN (FBR accepts 1000000000000 for
                                    unregistered end consumers in sandbox)
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class BuyerRegistrationType(models.TextChoices):
    """
    Matches FBR buyerRegistrationType field exactly.
    Registered   → has NTN, can claim input tax credit
    Unregistered → individual or non-registered business
    """
    REGISTERED   = "Registered",   _("Registered (NTN holder)")
    UNREGISTERED = "Unregistered", _("Unregistered")


class ProvinceChoice(models.TextChoices):
    """
    Pakistan provinces + territories.
    Maps to FBR's province reference API (/pdi/v1/provinces).
    Used in buyerProvince field on FBR invoice JSON.
    """
    PUNJAB         = "Punjab",                  _("Punjab")
    SINDH          = "Sindh",                   _("Sindh")
    KPK            = "Khyber Pakhtunkhwa",      _("Khyber Pakhtunkhwa (KPK)")
    BALOCHISTAN    = "Balochistan",             _("Balochistan")
    AJK            = "Azad Jammu & Kashmir",    _("Azad Jammu & Kashmir")
    GB             = "Gilgit-Baltistan",        _("Gilgit-Baltistan")
    ICT            = "Islamabad",               _("Islamabad Capital Territory")


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class Customer(models.Model):
    """
    One row = one customer of a company.

    Sections
    ────────
    1. Company ownership
    2. Identity (FBR buyer fields)
    3. Contact details
    4. Walk-in flag
    5. Status & timestamps
    """

    # ------------------------------------------------------------------
    # 1. Company ownership
    # ------------------------------------------------------------------

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="customers",
        verbose_name=_("Company"),
        help_text=_("Every customer belongs to exactly one company (tenant)."),
    )

    # ------------------------------------------------------------------
    # 2. Identity — FBR buyer fields
    # ------------------------------------------------------------------

    name = models.CharField(
        max_length=255,
        verbose_name=_("Customer Name / Business Name"),
        help_text=_(
            "Full name of the individual or registered business name. "
            "Maps to 'buyerBusinessName' in FBR invoice JSON."
        ),
    )

    ntn_cnic = models.CharField(
        max_length=15,
        blank=True,
        verbose_name=_("NTN / CNIC"),
        help_text=_(
            "National Tax Number (7 or 9 digits) for registered businesses, "
            "or CNIC (13 digits) for individuals. "
            "REQUIRED for FBR registered buyer scenarios (SN001, SN005). "
            "Maps to 'buyerNTNCNIC' in FBR invoice JSON."
        ),
    )

    registration_type = models.CharField(
        max_length=15,
        choices=BuyerRegistrationType.choices,
        default=BuyerRegistrationType.UNREGISTERED,
        verbose_name=_("Registration Type"),
        help_text=_(
            "Registered = NTN holder who can claim input tax credit. "
            "Unregistered = individual or non-registered business. "
            "Maps to 'buyerRegistrationType' in FBR invoice JSON."
        ),
    )

    province = models.CharField(
        max_length=50,
        choices=ProvinceChoice.choices,
        blank=True,
        verbose_name=_("Province"),
        help_text=_(
            "Customer's province. "
            "Maps to 'buyerProvince' in FBR invoice JSON."
        ),
    )

    address = models.TextField(
        blank=True,
        verbose_name=_("Address"),
        help_text=_(
            "Full business or home address. "
            "Maps to 'buyerAddress' in FBR invoice JSON."
        ),
    )

    # ------------------------------------------------------------------
    # 3. Contact details (not sent to FBR — for our own records)
    # ------------------------------------------------------------------

    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Phone Number"),
    )

    email = models.EmailField(
        blank=True,
        verbose_name=_("Email Address"),
    )

    # ------------------------------------------------------------------
    # 4. Walk-in customer flag
    #
    # Each company has exactly one walk-in record created automatically
    # when the company is first set up. Walk-in is used for:
    #   - Cash sales to anonymous customers
    #   - Unregistered end consumers (SN026, SN027, SN028)
    #
    # Walk-in record uses FBR's accepted dummy NTN for unregistered
    # end consumers: "1000000000000" (13 zeros after 1).
    # ------------------------------------------------------------------

    is_walk_in = models.BooleanField(
        default=False,
        verbose_name=_("Walk-In Customer"),
        help_text=_(
            "If True this is the shared anonymous walk-in record for this company. "
            "Used for cash sales where customer details are not collected. "
            "Each company has exactly one walk-in record. "
            "Cannot be deleted."
        ),
    )

    # ------------------------------------------------------------------
    # 5. Status & timestamps
    # ------------------------------------------------------------------

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Inactive customers do not appear in POS customer search."),
    )

    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_customers",
        verbose_name=_("Created By"),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True,     verbose_name=_("Updated At"))

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    class Meta:
        verbose_name        = _("Customer")
        verbose_name_plural = _("Customers")
        ordering            = ["name"]
        indexes = [
            models.Index(fields=["company", "is_active"],  name="customer_company_active_idx"),
            models.Index(fields=["ntn_cnic"],              name="customer_ntn_cnic_idx"),
            models.Index(fields=["registration_type"],     name="customer_reg_type_idx"),
        ]
        constraints = [
            # Each company can have only ONE walk-in record
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(is_walk_in=True),
                name="unique_walkin_per_company",
            ),
            # NTN/CNIC must be unique per company (same customer can't be added twice)
            models.UniqueConstraint(
                fields=["company", "ntn_cnic"],
                condition=models.Q(ntn_cnic__gt=""),
                name="unique_ntn_cnic_per_company",
            ),
        ]

    def __str__(self):
        reg = "✓" if self.registration_type == BuyerRegistrationType.REGISTERED else "—"
        return f"{self.name} [{reg} NTN: {self.ntn_cnic or 'N/A'}]"

    # ------------------------------------------------------------------
    # FBR helper — called by invoice generator in Phase 3
    # ------------------------------------------------------------------

    def get_fbr_buyer_payload(self) -> dict:
        """
        Returns the FBR buyer fields for the invoice header JSON.

        Called by invoice generator when building the JSON to POST to:
        https://gw.fbr.gov.pk/di_data/v1/di/postinvoicedata

        Returns:
            dict with buyerNTNCNIC, buyerBusinessName,
                      buyerProvince, buyerAddress, buyerRegistrationType
        """
        return {
            "buyerNTNCNIC":          self.ntn_cnic or "1000000000000",
            "buyerBusinessName":     self.name,
            "buyerProvince":         self.province or "Punjab",
            "buyerAddress":          self.address  or "Pakistan",
            "buyerRegistrationType": self.registration_type,
        }

    def delete(self, *args, **kwargs):
        """
        Prevent deletion of the walk-in customer record.
        Deactivate instead.
        """
        if self.is_walk_in:
            raise ValueError(
                "Walk-in customer record cannot be deleted. "
                "It is required for anonymous sales. Deactivate it instead."
            )
        super().delete(*args, **kwargs)


# ---------------------------------------------------------------------------
# Signal — auto-create walk-in customer when a Company is activated
# ---------------------------------------------------------------------------

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="companies.Company")
def create_walkin_customer(sender, instance, created, **kwargs):
    """
    When a new Company is created, automatically create its walk-in
    customer record so cashiers can immediately start processing
    anonymous cash sales without any setup.
    """
    if not created:
        return

    Customer.objects.get_or_create(
        company    = instance,
        is_walk_in = True,
        defaults   = {
            "name":              "Walk-In Customer",
            "ntn_cnic":          "1000000000000",  # FBR accepted dummy for unregistered
            "registration_type": BuyerRegistrationType.UNREGISTERED,
            "province":          ProvinceChoice.PUNJAB,
            "address":           "Pakistan",
            "is_active":         True,
        }
    )



"""
pos/sale_models.py

Four models for the core POS transaction:

  CashSession
  ───────────
  A cashier's shift. Opened with an opening balance, closed with a
  cash count. All sales during the shift are linked to this session.
  Required when module_terminals_cash_sessions is enabled.

  Sale
  ────
  The transaction header. One row = one complete or in-progress sale.
  Statuses: DRAFT → COMPLETED → (optionally) RETURNED
  A DRAFT sale is parked/held — cashier can come back to it.
  A COMPLETED sale triggers FBR invoice submission in Phase 3.

  SaleLine
  ────────
  One row per product in the sale. Stores all FBR item-level fields
  at the time of sale (snapshot — so changing a product later doesn't
  affect historical sales).

  SalePayment
  ───────────
  One row per payment method used in a sale.
  A sale can have multiple SalePayment rows (split payment).
  Sum of all SalePayment.amount must equal Sale.total_amount.

FBR invoice header fields that come from Sale:
  invoiceType       → sale_type (Sale Invoice / Debit Note / Credit Note)
  invoiceDate       → completed_at
  invoiceRefNo      → fbr_invoice_number (assigned by FBR on submission)
  scenarioId        → fbr_scenario_id (determined at submission time)
  sellerBusinessName → company.business_name
  sellerNTNCNIC      → company.ntn
  sellerProvince     → derived from company.address (Phase 3)
  sellerAddress      → company.address
  buyerNTNCNIC       → customer.ntn_cnic
  buyerBusinessName  → customer.name
  buyerProvince      → customer.province
  buyerAddress       → customer.address
  buyerRegistrationType → customer.registration_type

FBR item fields come from SaleLine (snapshot of Product FBR fields).
"""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

import uuid


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class CashSessionStatus(models.TextChoices):
    OPEN   = "open",   _("Open")
    CLOSED = "closed", _("Closed")


class SaleStatus(models.TextChoices):
    DRAFT     = "draft",     _("Draft / On Hold")
    COMPLETED = "completed", _("Completed")
    RETURNED  = "returned",  _("Returned")
    CANCELLED = "cancelled", _("Cancelled")


class SaleType(models.TextChoices):
    """
    Maps to FBR invoiceType field.
    """
    SALE_INVOICE = "Sale Invoice",   _("Sale Invoice")
    DEBIT_NOTE   = "Debit Note",     _("Debit Note")
    CREDIT_NOTE  = "Credit Note",    _("Credit Note")


class PaymentMethod(models.TextChoices):
    CASH          = "cash",          _("Cash")
    CARD          = "card",          _("Card (Debit/Credit)")
    CHEQUE        = "cheque",        _("Cheque")
    BANK_TRANSFER = "bank_transfer", _("Bank Transfer")


class FBRSubmissionStatus(models.TextChoices):
    PENDING  = "pending",  _("Pending — not yet submitted to FBR")
    SUCCESS  = "success",  _("Submitted & Validated by FBR")
    FAILED   = "failed",   _("Submission Failed")
    SKIPPED  = "skipped",  _("Skipped — FBR DI not enabled for this company")


# ---------------------------------------------------------------------------
# CashSession
# ---------------------------------------------------------------------------

class CashSession(models.Model):
    """
    One row = one cashier shift.

    Opened when cashier starts their shift (with opening cash balance).
    Closed when cashier ends shift (with actual cash count).
    All sales during the shift are linked via sale.cash_session FK.

    Only relevant when company.module_terminals_cash_sessions = True.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="cash_sessions",
        verbose_name=_("Company"),
    )

    cashier = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="cash_sessions",
        verbose_name=_("Cashier"),
        help_text=_("The user who opened this session."),
    )

    status = models.CharField(
        max_length=10,
        choices=CashSessionStatus.choices,
        default=CashSessionStatus.OPEN,
        verbose_name=_("Status"),
    )

    # ── Opening ──────────────────────────────────────────────────────
    opening_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Opening Cash Balance"),
        help_text=_("Cash in the till at the start of the shift."),
    )

    opened_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Opened At"),
    )

    opening_note = models.TextField(
        blank=True,
        verbose_name=_("Opening Note"),
    )

    # ── Closing ──────────────────────────────────────────────────────
    closing_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Closing Cash Count"),
        help_text=_("Actual cash counted in the till at end of shift."),
    )

    expected_cash = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Expected Cash"),
        help_text=_(
            "System-calculated: opening_balance + total cash sales during session. "
            "Computed when session is closed."
        ),
    )

    cash_difference = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Cash Difference"),
        help_text=_("closing_balance − expected_cash. Negative = shortage."),
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Closed At"),
    )

    closing_note = models.TextField(
        blank=True,
        verbose_name=_("Closing Note"),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = _("Cash Session")
        verbose_name_plural = _("Cash Sessions")
        ordering            = ["-opened_at"]
        indexes = [
            models.Index(fields=["company", "status"], name="cashsession_company_status_idx"),
            models.Index(fields=["cashier"],           name="cashsession_cashier_idx"),
        ]
        constraints = [
            # A cashier can only have ONE open session at a time per company
            models.UniqueConstraint(
                fields=["company", "cashier"],
                condition=models.Q(status="open"),
                name="unique_open_session_per_cashier",
            ),
        ]

    def __str__(self):
        return (
            f"Session #{self.pk} — {self.cashier.email} "
            f"[{self.get_status_display()}] @ {self.company.business_name}"
        )

    def close(self, closing_balance: float, note: str = ""):
        """
        Close the session. Computes expected cash and difference.
        Call this from the ViewSet action, not directly from a view.
        """
        from django.db.models import Sum

        total_cash_sales = (
            SalePayment.objects
            .filter(
                sale__cash_session=self,
                sale__status=SaleStatus.COMPLETED,
                payment_method=PaymentMethod.CASH,
            )
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        self.closing_balance = closing_balance
        self.expected_cash   = float(self.opening_balance) + float(total_cash_sales)
        self.cash_difference = float(closing_balance) - float(self.expected_cash)
        self.closed_at       = timezone.now()
        self.closing_note    = note
        self.status          = CashSessionStatus.CLOSED
        self.save()


# ---------------------------------------------------------------------------
# Sale
# ---------------------------------------------------------------------------

class Sale(models.Model):
    """
    One row = one POS transaction (complete or in-progress).

    DRAFT   → parked/held sale, not yet paid, not sent to FBR
    COMPLETED → fully paid, FBR submission triggered
    RETURNED  → a return was processed against this sale
    CANCELLED → voided before completion

    The sale_number is our internal reference (e.g. "INV-2025-000001").
    The fbr_invoice_number is assigned by FBR after successful submission.
    """

    # ------------------------------------------------------------------
    # Ownership & session
    # ------------------------------------------------------------------

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="sales",
        verbose_name=_("Company"),
    )

    cashier = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="sales",
        verbose_name=_("Cashier / Created By"),
    )

    cash_session = models.ForeignKey(
        CashSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales",
        verbose_name=_("Cash Session"),
        help_text=_(
            "The open cash session this sale belongs to. "
            "NULL if company doesn't use cash sessions."
        ),
    )

    customer = models.ForeignKey(
        "pos.Customer",
        on_delete=models.PROTECT,
        related_name="sales",
        verbose_name=_("Customer"),
        help_text=_(
            "Required. Use the walk-in record for anonymous cash sales. "
            "For FBR registered buyer scenarios, customer must have a valid NTN."
        ),
    )

    # ------------------------------------------------------------------
    # Sale identity
    # ------------------------------------------------------------------

    sale_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Sale / Invoice Number"),
        help_text=_(
            "Our internal sequential invoice number. "
            "Format: INV-YYYY-NNNNNN (e.g. INV-2025-000001). "
            "Auto-generated on save."
        ),
    )

    sale_type = models.CharField(
        max_length=20,
        choices=SaleType.choices,
        default=SaleType.SALE_INVOICE,
        verbose_name=_("Sale Type"),
        help_text=_("Maps to 'invoiceType' in FBR invoice JSON."),
    )

    status = models.CharField(
        max_length=15,
        choices=SaleStatus.choices,
        default=SaleStatus.DRAFT,
        verbose_name=_("Status"),
    )

    # ------------------------------------------------------------------
    # Financial totals (denormalised for fast reporting)
    # These are computed from SaleLines and stored here on completion.
    # ------------------------------------------------------------------

    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Subtotal (excl. tax)"),
        help_text=_("Sum of (selling_price × quantity) for all lines."),
    )

    total_discount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total Discount"),
        help_text=_("Sum of discount amounts across all lines."),
    )

    total_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total Sales Tax"),
        help_text=_("Sum of salesTaxApplicable across all lines."),
    )

    total_further_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total Further Tax"),
    )

    total_fed = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total FED Payable"),
    )

    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total Amount (incl. all taxes)"),
        help_text=_(
            "Grand total the customer pays. "
            "Maps to sum of 'totalValues' across all FBR line items."
        ),
    )

    amount_paid = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Amount Paid"),
        help_text=_("Sum of all SalePayment rows. Must equal total_amount on completion."),
    )

    change_given = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Change Given"),
        help_text=_("Cash change returned to customer (amount_paid − total_amount)."),
    )

    # ------------------------------------------------------------------
    # FBR submission fields
    # ------------------------------------------------------------------

    fbr_submission_status = models.CharField(
        max_length=10,
        choices=FBRSubmissionStatus.choices,
        default=FBRSubmissionStatus.PENDING,
        verbose_name=_("FBR Submission Status"),
    )

    fbr_invoice_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("FBR Invoice Number"),
        help_text=_(
            "Assigned by FBR after successful submission. "
            "Format: {NTN}DI{timestamp} e.g. '7000007DI1747119701593'. "
            "Printed as QR code on receipt."
        ),
    )

    fbr_scenario_id = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_("FBR Scenario ID"),
        help_text=_(
            "The sandbox scenario code used for this invoice (e.g. 'SN001'). "
            "Determined at submission time based on customer registration type "
            "and product sale types."
        ),
    )

    fbr_submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("FBR Submitted At"),
    )

    fbr_error_code = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_("FBR Error Code"),
        help_text=_("Error code from FBR response if submission failed (e.g. '0046')."),
    )

    fbr_error_message = models.TextField(
        blank=True,
        verbose_name=_("FBR Error Message"),
        help_text=_("Full error message from FBR if submission failed."),
    )

    fbr_qr_code = models.TextField(
        blank=True,
        verbose_name=_("FBR QR Code Data"),
        help_text=_(
            "QR code content for printing on receipt. "
            "Version 2.0 (25×25), 1.0 × 1.0 inch as per PRAL spec."
        ),
    )
    # ── Receipt URLs (stored after first generation) ──────────────────
    receipt_thermal_url = models.URLField(
        blank=True,
        verbose_name=_("Thermal Receipt URL"),
        help_text=_(
            "S3 URL of generated 80mm thermal receipt PDF. "
            "Auto-populated on first receipt request. "
            "Empty until first generated."
        ),
    )
 
    receipt_a4_url = models.URLField(
        blank=True,
        verbose_name=_("A4 Invoice URL"),
        help_text=_(
            "S3 URL of generated A4 invoice PDF. "
            "Auto-populated on first invoice request."
        ),
    )
 
    receipt_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Receipt Generated At"),
        help_text=_("Timestamp of last receipt generation."),
    )

    # ------------------------------------------------------------------
    # Notes & reference
    # ------------------------------------------------------------------

    notes = models.TextField(
        blank=True,
        verbose_name=_("Internal Notes"),
    )

    # For debit/credit notes — reference to original sale
    original_sale = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_debit_notes",
        verbose_name=_("Original Sale (for Debit/Credit Notes)"),
        help_text=_(
            "Maps to 'invoiceRefNo' in FBR JSON. "
            "Required when sale_type is Debit Note or Credit Note."
        ),
    )

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Completed At"),
        help_text=_("When the sale was finalised. Maps to 'invoiceDate' in FBR JSON."),
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True,     verbose_name=_("Updated At"))

    class Meta:
        verbose_name        = _("Sale")
        verbose_name_plural = _("Sales")
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status"],          name="sale_company_status_idx"),
            models.Index(fields=["company", "completed_at"],    name="sale_company_date_idx"),
            models.Index(fields=["fbr_submission_status"],      name="sale_fbr_status_idx"),
            models.Index(fields=["fbr_invoice_number"],         name="sale_fbr_inv_no_idx"),
            models.Index(fields=["customer"],                   name="sale_customer_idx"),
        ]

    def __str__(self):
        return f"{self.sale_number} [{self.get_status_display()}] — {self.company.business_name}"

    def save(self, *args, **kwargs):
        # Auto-generate sale_number if not set
        if not self.sale_number:
            self.sale_number = self._generate_sale_number()
        super().save(*args, **kwargs)

    def _generate_sale_number(self) -> str:
        """
        Generates a sequential invoice number per company.
        Format: INV-YYYY-NNNNNN (e.g. INV-2025-000001)
        """
        from django.utils import timezone
        year  = timezone.now().year
        count = Sale.objects.filter(company=self.company).count() + 1
        return f"INV-{year}-{count:06d}"

    def compute_totals(self):
        """
        Recompute all financial totals from SaleLines.
        Call this after adding/editing lines, before completing the sale.
        """
        lines = self.lines.all()

        self.subtotal         = sum(l.unit_price * l.quantity for l in lines)
        self.total_discount   = sum(l.discount_amount for l in lines)
        self.total_tax        = sum(l.sales_tax_applicable for l in lines)
        self.total_further_tax = sum(l.further_tax for l in lines)
        self.total_fed        = sum(l.fed_payable for l in lines)
        self.total_amount     = sum(l.line_total for l in lines)
        self.save(update_fields=[
            "subtotal", "total_discount", "total_tax",
            "total_further_tax", "total_fed", "total_amount",
            "updated_at",
        ])

    def complete(self):
        """
        Mark sale as completed. Sets completed_at timestamp.
        FBR submission is triggered separately by a Celery task / signal.
        """
        from django.utils import timezone
        self.status       = SaleStatus.COMPLETED
        self.completed_at = timezone.now()
        # Compute amount_paid from payments
        self.amount_paid = sum(
            p.amount for p in self.payments.all()
        )
        self.change_given = max(0, float(self.amount_paid) - float(self.total_amount))
        self.save()


# ---------------------------------------------------------------------------
# SaleLine
# ---------------------------------------------------------------------------

class SaleLine(models.Model):
    """
    One row = one product line in a sale.

    All FBR item fields are SNAPSHOTTED at the time of sale.
    This is critical — if a product's tax rate changes later,
    the historical sale must still show the rate at time of sale.

    get_fbr_item_payload() on this model returns the FBR JSON
    item dict directly, ready for the invoice submission.
    """

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("Sale"),
    )

    product = models.ForeignKey(
        "pos.Product",
        on_delete=models.PROTECT,   # never delete a product that has sales history
        related_name="sale_lines",
        verbose_name=_("Product"),
    )

    # ── Snapshot fields — copied from Product at time of sale ─────────

    product_name = models.CharField(
        max_length=255,
        verbose_name=_("Product Name (snapshot)"),
        help_text=_("Copied from product.name at sale time. Maps to 'productDescription' in FBR JSON."),
    )

    hs_code = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("HS Code (snapshot)"),
        help_text=_("Copied from product.hs_code at sale time. Maps to 'hsCode' in FBR JSON."),
    )

    unit_of_measure = models.CharField(
        max_length=50,
        verbose_name=_("Unit of Measure (snapshot)"),
        help_text=_("Copied from product.unit_of_measure at sale time. Maps to 'uoM' in FBR JSON."),
    )

    fbr_sale_type = models.CharField(
        max_length=80,
        verbose_name=_("FBR Sale Type (snapshot)"),
        help_text=_("Copied from product.fbr_sale_type at sale time. Maps to 'saleType' in FBR JSON."),
    )

    tax_rate_percent = models.CharField(
        max_length=10,
        verbose_name=_("Tax Rate (snapshot)"),
        help_text=_("Copied from product.tax_rate_percent at sale time. Maps to 'rate' in FBR JSON."),
    )

    # ── Quantity & pricing ────────────────────────────────────────────

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(0.001)],
        verbose_name=_("Quantity"),
    )

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name=_("Unit Price (excl. tax)"),
        help_text=_("Copied from product.selling_price at sale time."),
    )

    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Discount Amount"),
        help_text=_("Maps to 'discount' in FBR JSON."),
    )

    # ── FBR computed tax fields ───────────────────────────────────────

    value_excl_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Value excl. Tax"),
        help_text=_("unit_price × quantity. Maps to 'valueSalesExcludingST' in FBR JSON."),
    )

    sales_tax_applicable = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Sales Tax Applicable"),
        help_text=_("value_excl_tax × tax_rate. Maps to 'salesTaxApplicable' in FBR JSON."),
    )

    sales_tax_withheld = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("Sales Tax Withheld at Source"),
        help_text=_("Maps to 'salesTaxWithheldAtSource' in FBR JSON."),
    )

    further_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("Further Tax"),
        help_text=_("Maps to 'furtherTax' in FBR JSON."),
    )

    extra_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("Extra Tax"),
        help_text=_("Maps to 'extraTax' in FBR JSON."),
    )

    fed_payable = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("FED Payable"),
        help_text=_("Maps to 'fedPayable' in FBR JSON."),
    )

    fixed_retail_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("Fixed / Notified Retail Price"),
        help_text=_("Maps to 'fixedNotifiedValueOrRetailPrice' in FBR JSON."),
    )

    sro_schedule_no = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("SRO Schedule No."),
        help_text=_("Maps to 'sroScheduleNo' in FBR JSON."),
    )

    sro_item_serial_no = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("SRO Item Serial No."),
        help_text=_("Maps to 'sroItemSerialNo' in FBR JSON."),
    )

    line_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Line Total (incl. all taxes)"),
        help_text=_("value_excl_tax + sales_tax + further_tax + fed − discount. Maps to 'totalValues'."),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = _("Sale Line")
        verbose_name_plural = _("Sale Lines")
        ordering            = ["id"]

    def __str__(self):
        return f"{self.product_name} × {self.quantity} @ {self.unit_price}"

    def save(self, *args, **kwargs):
        """Auto-compute all tax fields before saving."""
        self._compute_fields()
        super().save(*args, **kwargs)

    def _compute_fields(self):
        """
        Compute all derived financial fields from quantity, unit_price,
        tax_rate_percent and individual tax fields.
        """
        qty        = float(self.quantity)
        price      = float(self.unit_price)
        discount   = float(self.discount_amount)
        tax_rate   = float(self.tax_rate_percent.replace("%", "")) / 100

        self.value_excl_tax       = round(price * qty, 2)
        self.sales_tax_applicable = round(self.value_excl_tax * tax_rate, 2)
        self.line_total           = round(
            float(self.value_excl_tax)
            + float(self.sales_tax_applicable)
            + float(self.further_tax)
            + float(self.fed_payable)
            + float(self.extra_tax)
            - discount,
            2
        )

    @classmethod
    def from_product(cls, sale, product, quantity: float,
                     discount_amount: float = 0) -> "SaleLine":
        """
        Factory method — creates a SaleLine from a Product,
        snapshotting all FBR fields at the current moment.

        Usage:
            line = SaleLine.from_product(sale, product, quantity=2)
            line.save()
        """
        return cls(
            sale               = sale,
            product            = product,
            product_name       = product.name,
            hs_code            = product.hs_code,
            unit_of_measure    = product.unit_of_measure,
            fbr_sale_type      = product.fbr_sale_type,
            tax_rate_percent   = product.tax_rate_percent,
            quantity           = quantity,
            unit_price         = product.selling_price,
            discount_amount    = discount_amount,
            sales_tax_withheld = product.fbr_sales_tax_withheld,
            further_tax        = product.fbr_further_tax,
            extra_tax          = product.fbr_extra_tax,
            fed_payable        = product.fbr_fed_payable,
            fixed_retail_price = product.fbr_fixed_retail_price,
            sro_schedule_no    = product.fbr_sro_schedule_no,
            sro_item_serial_no = product.fbr_sro_item_serial_no,
        )

    def get_fbr_item_payload(self) -> dict:
        """
        Returns FBR DI API item JSON for this sale line.
        Called by the invoice generator in Phase 3.
        """
        return {
            "hsCode":                          self.hs_code or "",
            "productDescription":              self.product_name,
            "rate":                            self.tax_rate_percent,
            "uoM":                             self.unit_of_measure,
            "quantity":                        float(self.quantity),
            "valueSalesExcludingST":           float(self.value_excl_tax),
            "fixedNotifiedValueOrRetailPrice": float(self.fixed_retail_price),
            "salesTaxApplicable":              float(self.sales_tax_applicable),
            "salesTaxWithheldAtSource":        float(self.sales_tax_withheld),
            "extraTax":                        float(self.extra_tax) or "",
            "furtherTax":                      float(self.further_tax),
            "sroScheduleNo":                   self.sro_schedule_no or "",
            "sroItemSerialNo":                 self.sro_item_serial_no or "",
            "fedPayable":                      float(self.fed_payable),
            "discount":                        float(self.discount_amount),
            "totalValues":                     float(self.line_total),
            "saleType":                        self.fbr_sale_type,
        }


# ---------------------------------------------------------------------------
# SalePayment
# ---------------------------------------------------------------------------

class SalePayment(models.Model):
    """
    One row = one payment made against a sale.
    A sale can have multiple SalePayment rows (split payment).

    Sum of all SalePayment.amount for a sale must equal Sale.total_amount
    before the sale can be completed.

    Cheque and bank transfer fields are only relevant when
    company.module_cheque_bank_transfer = True.
    """

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("Sale"),
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        verbose_name=_("Payment Method"),
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        verbose_name=_("Amount"),
    )

    # ── Cheque fields (only when payment_method = CHEQUE) ────────────
    cheque_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Cheque Number"),
    )

    cheque_bank = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Cheque Bank"),
    )

    cheque_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Cheque Date"),
    )

    # ── Bank transfer fields (only when payment_method = BANK_TRANSFER)
    bank_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Bank Transfer Reference"),
    )

    bank_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Bank Name"),
    )

    # ── Card fields ──────────────────────────────────────────────────
    card_last_four = models.CharField(
        max_length=4,
        blank=True,
        verbose_name=_("Card Last 4 Digits"),
    )

    card_type = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Card Type"),
        help_text=_("e.g. Visa, Mastercard, UnionPay"),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = _("Sale Payment")
        verbose_name_plural = _("Sale Payments")
        ordering            = ["id"]
        indexes = [
            models.Index(fields=["sale"],           name="salepayment_sale_idx"),
            models.Index(fields=["payment_method"], name="salepayment_method_idx"),
        ]

    def __str__(self):
        return f"{self.get_payment_method_display()} — Rs. {self.amount} [{self.sale.sale_number}]"
    

"""
========================================================
pos/return_models.py
Add these to pos/models.py
 
Return flow:
1. Cashier selects original completed sale
2. Selects items to return (full or partial)
3. System creates SaleReturn record
4. SaleReturnLine rows created for each returned item
5. Stock incremented for returned items
6. Credit Note Sale created linked to original
7. Credit Note submitted to FBR
8. Cash refund recorded as SaleRefundPayment
 
FBR rules for credit notes (from PRAL manual):
- Only e-invoices received through DI Integration are eligible
- Corrections must be within 72 hours of invoice insertion date
- Invoice number cannot be modified
- Invoices linked with Annexure-C are not eligible
- Cannot exceed 10% of last month's sales
========================================================
"""
 
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
 
 
class ReturnStatus(models.TextChoices):
    PENDING   = "pending",   _("Pending")
    COMPLETED = "completed", _("Completed")
    REJECTED  = "rejected",  _("Rejected")
 
 
class ReturnReason(models.TextChoices):
    DEFECTIVE        = "defective",        _("Defective / Damaged Product")
    WRONG_ITEM       = "wrong_item",       _("Wrong Item Delivered")
    CUSTOMER_CHANGED = "customer_changed", _("Customer Changed Mind")
    OVERCHARGED      = "overcharged",      _("Overcharged")
    EXPIRED          = "expired",          _("Expired Product")
    OTHER            = "other",            _("Other")
 
 
class SaleReturn(models.Model):
    """
    One row = one return transaction.
 
    Links back to original Sale.
    Can be full (all items) or partial (selected items).
    Always results in a cash refund to customer.
 
    Creates a Credit Note Sale that gets submitted to FBR.
 
    FBR 72-hour rule is checked at creation time.
    """
 
    # ── Ownership ─────────────────────────────────────────────────────
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="returns",
        verbose_name=_("Company"),
    )
 
    original_sale = models.ForeignKey(
        "pos.Sale",
        on_delete=models.PROTECT,
        related_name="returns",
        verbose_name=_("Original Sale"),
        help_text=_(
            "The completed sale this return is against. "
            "Must have a valid FBR invoice number for credit note submission."
        ),
    )
 
    # Credit note sale created automatically when return is completed
    credit_note_sale = models.OneToOneField(
        "pos.Sale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="return_credit_note",
        verbose_name=_("Credit Note Sale"),
        help_text=_(
            "Auto-created Credit Note Sale linked to this return. "
            "Submitted to FBR as a Credit Note invoice."
        ),
    )
 
    processed_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        related_name="processed_returns",
        verbose_name=_("Processed By"),
    )
 
    # ── Return details ────────────────────────────────────────────────
    return_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Return Number"),
        help_text=_("Auto-generated. Format: RET-YYYY-NNNNNN"),
    )
 
    return_type = models.CharField(
        max_length=10,
        choices=[("full", _("Full Return")), ("partial", _("Partial Return"))],
        verbose_name=_("Return Type"),
    )
 
    reason = models.CharField(
        max_length=20,
        choices=ReturnReason.choices,
        default=ReturnReason.OTHER,
        verbose_name=_("Return Reason"),
    )
 
    reason_notes = models.TextField(
        blank=True,
        verbose_name=_("Additional Notes"),
        help_text=_("Required when reason is 'Other'."),
    )
 
    status = models.CharField(
        max_length=10,
        choices=ReturnStatus.choices,
        default=ReturnStatus.PENDING,
        verbose_name=_("Status"),
    )
 
    # ── Financial totals ──────────────────────────────────────────────
    total_return_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total Return Amount"),
        help_text=_("Sum of all returned line totals including tax."),
    )
 
    total_return_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Total Tax Returned"),
    )
 
    # ── Refund ────────────────────────────────────────────────────────
    refund_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Refund Amount"),
        help_text=_("Cash refunded to customer. Equals total_return_amount."),
    )
 
    refund_paid = models.BooleanField(
        default=False,
        verbose_name=_("Refund Paid"),
        help_text=_("True when cash has been physically returned to customer."),
    )
 
    refund_paid_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Refund Paid At"),
    )
 
    # ── FBR 72-hour eligibility check ────────────────────────────────
    fbr_eligible = models.BooleanField(
        default=True,
        verbose_name=_("FBR Credit Note Eligible"),
        help_text=_(
            "False if original invoice is older than 72 hours "
            "or has been reported in a submitted return. "
            "If False, return is processed internally but no credit note sent to FBR."
        ),
    )
 
    fbr_eligibility_reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("FBR Ineligibility Reason"),
        help_text=_("Reason why credit note cannot be submitted to FBR."),
    )
 
    # ── Timestamps ────────────────────────────────────────────────────
    created_at   = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at   = models.DateTimeField(auto_now=True)
 
    class Meta:
        verbose_name        = _("Sale Return")
        verbose_name_plural = _("Sale Returns")
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status"],    name="return_company_status_idx"),
            models.Index(fields=["original_sale"],        name="return_original_sale_idx"),
        ]
 
    def __str__(self):
        return f"{self.return_number} → {self.original_sale.sale_number}"
 
    def save(self, *args, **kwargs):
        if not self.return_number:
            self.return_number = self._generate_return_number()
        super().save(*args, **kwargs)
 
    def _generate_return_number(self) -> str:
        year  = timezone.now().year
        count = SaleReturn.objects.filter(company=self.company).count() + 1
        return f"RET-{year}-{count:06d}"
 
    def check_fbr_eligibility(self):
        """
        Checks FBR 72-hour rule and other eligibility conditions.
        Sets fbr_eligible and fbr_eligibility_reason.
        """
        original = self.original_sale
 
        # Must have FBR invoice number
        if not original.fbr_invoice_number:
            self.fbr_eligible          = False
            self.fbr_eligibility_reason = (
                "Original invoice was not submitted to FBR. "
                "Credit note cannot be issued."
            )
            return
 
        # 72-hour rule
        if original.completed_at:
            hours_elapsed = (
                timezone.now() - original.completed_at
            ).total_seconds() / 3600
 
            if hours_elapsed > 72:
                self.fbr_eligible           = False
                self.fbr_eligibility_reason = (
                    f"Original invoice is {hours_elapsed:.0f} hours old. "
                    f"FBR only allows corrections within 72 hours of invoice date."
                )
                return
 
        self.fbr_eligible           = True
        self.fbr_eligibility_reason = ""
 
 
class SaleReturnLine(models.Model):
    """
    One row = one product line being returned.
    Linked to both SaleReturn and original SaleLine.
    """
 
    sale_return = models.ForeignKey(
        SaleReturn,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("Sale Return"),
    )
 
    original_line = models.ForeignKey(
        "pos.SaleLine",
        on_delete=models.PROTECT,
        related_name="return_lines",
        verbose_name=_("Original Sale Line"),
    )
 
    product_name = models.CharField(
        max_length=255,
        verbose_name=_("Product Name (snapshot)"),
    )
 
    quantity_returned = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(0.001)],
        verbose_name=_("Quantity Returned"),
        help_text=_("Cannot exceed original line quantity."),
    )
 
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Unit Price"),
        help_text=_("Copied from original line."),
    )
 
    tax_rate_percent = models.CharField(
        max_length=10,
        verbose_name=_("Tax Rate"),
    )
 
    return_value_excl_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Return Value excl. Tax"),
    )
 
    return_tax = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Return Tax"),
    )
 
    return_line_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name=_("Return Line Total"),
    )
 
    # Track if stock was incremented back
    stock_restored = models.BooleanField(
        default=False,
        verbose_name=_("Stock Restored"),
    )
 
    class Meta:
        verbose_name        = _("Sale Return Line")
        verbose_name_plural = _("Sale Return Lines")
 
    def __str__(self):
        return f"{self.product_name} × {self.quantity_returned}"
 
    def save(self, *args, **kwargs):
        self._compute_totals()
        super().save(*args, **kwargs)
 
    def _compute_totals(self):
        qty      = float(self.quantity_returned)
        price    = float(self.unit_price)
        tax_rate = float(self.tax_rate_percent.replace("%", "")) / 100
 
        self.return_value_excl_tax = round(price * qty, 2)
        self.return_tax            = round(self.return_value_excl_tax * tax_rate, 2)
        self.return_line_total     = round(
            float(self.return_value_excl_tax) + float(self.return_tax), 2
        )
