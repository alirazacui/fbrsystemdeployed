"""
========================================================
pos/serializers.py  — Product & Category section
========================================================
"""
 
from rest_framework import serializers
from .models import *
 
 
# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------
 
class CategorySerializer(serializers.ModelSerializer):
    """Full CRUD serializer for Category."""
 
    company_name = serializers.CharField(
        source="company.business_name",
        read_only=True,
    )
    product_count = serializers.SerializerMethodField()
 
    class Meta:
        model  = Category
        fields = [
            "id",
            "company",
            "company_name",
            "name",
            "description",
            "is_active",
            "product_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "company",        # set from request.user.company in ViewSet
            "company_name",
            "product_count",
            "created_at",
            "updated_at",
        ]
 
    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()
 
    def validate_name(self, value):
        """Name must be unique within the company."""
        request = self.context.get("request")
        company = request.user.company
        qs = Category.objects.filter(
            company=company,
            name__iexact=value.strip(),
        )
        # Exclude current instance on update
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"A category named '{value}' already exists in your company."
            )
        return value.strip()
 
    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["company"] = request.user.company
        return super().create(validated_data)
 
 
# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------
 
class ProductListSerializer(serializers.ModelSerializer):
    """
    Lightweight — for product search in POS terminal and list views.
    Only fields needed to display a product card and add to cart.
    """
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
        default=None,
    )
    is_low_stock = serializers.BooleanField(read_only=True)
 
    class Meta:
        model  = Product
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "selling_price",
            "tax_rate_percent",
            "fbr_sale_type",
            "unit_of_measure",
            "barcode",
            "sku",
            "current_stock",
            "track_inventory",
            "is_low_stock",
            "is_active",
            "image",
        ]
        read_only_fields = fields
 
 
class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Full detail — for create, retrieve, update.
    Includes all FBR tax fields.
    """
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
        default=None,
    )
    company_name = serializers.CharField(
        source="company.business_name",
        read_only=True,
    )
    is_low_stock = serializers.BooleanField(read_only=True)
 
    class Meta:
        model  = Product
        fields = [
            # ── Identity ───────────────────────────────────────────
            "id",
            "company",
            "company_name",
            "category",
            "category_name",
            "name",
            "description",
            "image",
 
            # ── Pricing ────────────────────────────────────────────
            "selling_price",
            "cost_price",
 
            # ── Barcode & unit ─────────────────────────────────────
            "barcode",
            "sku",
            "unit_of_measure",
 
            # ── FBR tax fields ─────────────────────────────────────
            "hs_code",
            "fbr_sale_type",
            "tax_rate_percent",
            "fbr_fixed_retail_price",
            "fbr_sales_tax_withheld",
            "fbr_further_tax",
            "fbr_extra_tax",
            "fbr_fed_payable",
            "fbr_default_discount",
            "fbr_sro_schedule_no",
            "fbr_sro_item_serial_no",
 
            # ── Inventory ──────────────────────────────────────────
            "track_inventory",
            "current_stock",
            "low_stock_threshold",
            "is_low_stock",
 
            # ── Status & audit ─────────────────────────────────────
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "company",
            "company_name",
            "category_name",
            "is_low_stock",
            "created_by",
            "created_at",
            "updated_at",
        ]
 
    def validate(self, attrs):
        """
        If fbr_sale_type requires an hs_code, enforce it.
        Manufacturer-cum-retailer types require hs_code.
        """
        sale_type = attrs.get("fbr_sale_type", "")
        hs_code   = attrs.get("hs_code", "")
 
        # These sale types require HS code per FBR spec
        hs_required_types = [
            "Steel Melting and re-rolling",
            "Ship breaking",
            "Petroleum Products",
            "Electricity Supply to Retailers",
            "Gas to CNG stations",
            "Mobile Phones",
            "Cement /Concrete Block",
            "Potassium Chlorate",
        ]
        if sale_type in hs_required_types and not hs_code:
            raise serializers.ValidationError({
                "hs_code": (
                    f"HS Code is required for sale type '{sale_type}'. "
                    f"Please provide a valid HS Code (e.g. 0101.2100)."
                )
            })
        return attrs
 
    def validate_barcode(self, value):
        """Barcode must be unique per company if provided."""
        if not value:
            return value
        request = self.context.get("request")
        company = request.user.company
        qs = Product.objects.filter(
            company=company,
            barcode=value,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Barcode '{value}' is already assigned to another product."
            )
        return value
 
    def validate_sku(self, value):
        """SKU must be unique per company if provided."""
        if not value:
            return value
        request = self.context.get("request")
        company = request.user.company
        qs = Product.objects.filter(
            company=company,
            sku=value,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"SKU '{value}' is already assigned to another product."
            )
        return value
 
    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["company"]    = request.user.company
        validated_data["created_by"] = request.user
        return super().create(validated_data)
 
 
class ProductStockUpdateSerializer(serializers.ModelSerializer):
    """
    Dedicated serializer for manual stock adjustments.
    Separate from ProductDetailSerializer so stock changes
    are explicit and auditable.
    """
    adjustment = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        write_only=True,
        help_text=(
            "Positive = stock in (receiving goods). "
            "Negative = stock out (manual write-off). "
            "This is added to current_stock, not a replacement."
        ),
    )
    reason = serializers.CharField(
        max_length=255,
        write_only=True,
        required=False,
        default="",
        help_text="Reason for manual adjustment (e.g. 'Damaged goods', 'Stock count correction').",
    )
 
    class Meta:
        model  = Product
        fields = ["current_stock", "adjustment", "reason"]
        read_only_fields = ["current_stock"]
 
    def validate_adjustment(self, value):
        """Prevent stock going below zero."""
        product = self.instance
        if product and (float(product.current_stock) + float(value)) < 0:
            raise serializers.ValidationError(
                f"Adjustment would bring stock below zero. "
                f"Current stock: {product.current_stock}. "
                f"Maximum reduction: {product.current_stock}."
            )
        return value
 
    def update(self, instance, validated_data):
        adjustment = validated_data.pop("adjustment")
        validated_data.pop("reason", "")   # logged separately in Phase 5 audit log
        instance.current_stock = float(instance.current_stock) + float(adjustment)
        instance.save(update_fields=["current_stock", "updated_at"])
        return instance


"""
========================================================
pos/customer_serializers.py  — paste into pos/serializers.py
========================================================
"""
 
from rest_framework import serializers
from .models import Customer, BuyerRegistrationType
 
 
# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------
 
class CustomerListSerializer(serializers.ModelSerializer):
    """
    Lightweight — for customer search on POS terminal.
    Only fields needed to identify and select a customer.
    """
    class Meta:
        model  = Customer
        fields = [
            "id",
            "name",
            "ntn_cnic",
            "registration_type",
            "phone",
            "is_walk_in",
            "is_active",
        ]
        read_only_fields = fields
 
 
class CustomerDetailSerializer(serializers.ModelSerializer):
    """
    Full detail — for create, retrieve, update.
    Includes all FBR buyer fields.
    """
    company_name = serializers.CharField(
        source="company.business_name",
        read_only=True,
    )
    created_by_email = serializers.EmailField(
        source="created_by.email",
        read_only=True,
        default=None,
    )
 
    class Meta:
        model  = Customer
        fields = [
            "id",
            "company",
            "company_name",
            # FBR buyer fields
            "name",
            "ntn_cnic",
            "registration_type",
            "province",
            "address",
            # Contact
            "phone",
            "email",
            # Flags
            "is_walk_in",
            "is_active",
            # Audit
            "created_by",
            "created_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "company",
            "company_name",
            "is_walk_in",       # set by system only
            "created_by",
            "created_by_email",
            "created_at",
            "updated_at",
        ]
 
    def validate(self, attrs):
        """
        If registration_type is Registered, ntn_cnic is required.
        NTN = 7 or 9 digits. CNIC = 13 digits.
        """
        reg_type = attrs.get(
            "registration_type",
            self.instance.registration_type if self.instance else BuyerRegistrationType.UNREGISTERED,
        )
        ntn_cnic = attrs.get(
            "ntn_cnic",
            self.instance.ntn_cnic if self.instance else "",
        )
 
        if reg_type == BuyerRegistrationType.REGISTERED:
            if not ntn_cnic:
                raise serializers.ValidationError({
                    "ntn_cnic": "NTN/CNIC is required for registered buyers."
                })
            # Validate format — strip dashes
            cleaned = ntn_cnic.replace("-", "").strip()
            if not cleaned.isdigit():
                raise serializers.ValidationError({
                    "ntn_cnic": "NTN/CNIC must contain digits only."
                })
            if len(cleaned) not in (7, 9, 13):
                raise serializers.ValidationError({
                    "ntn_cnic": (
                        "NTN must be 7 or 9 digits. "
                        "CNIC must be 13 digits. "
                        f"You provided {len(cleaned)} digits."
                    )
                })
 
        return attrs
 
    def validate_ntn_cnic(self, value):
        """NTN/CNIC must be unique per company if provided."""
        if not value:
            return value
        request = self.context.get("request")
        company = request.user.company if not request.user.is_platform_admin else None
        if company:
            qs = Customer.objects.filter(company=company, ntn_cnic=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    f"A customer with NTN/CNIC '{value}' already exists in your company."
                )
        return value
 
    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["company"]    = request.user.company
        validated_data["created_by"] = request.user
        return super().create(validated_data)
 


from rest_framework import serializers
from django.db import transaction
from .models import (
    CashSession, Sale, SaleLine, SalePayment,
    SaleStatus, FBRSubmissionStatus, PaymentMethod,
)
 
 
# ---------------------------------------------------------------------------
# CashSession
# ---------------------------------------------------------------------------
 
class CashSessionOpenSerializer(serializers.ModelSerializer):
    """Opens a new cash session (shift start)."""
 
    class Meta:
        model  = CashSession
        fields = ["opening_balance", "opening_note"]
 
    def validate(self, attrs):
        """Block if cashier already has an open session."""
        from .models import CashSessionStatus
        request = self.context["request"]
        already_open = CashSession.objects.filter(
            company  = request.user.company,
            cashier  = request.user,
            status   = CashSessionStatus.OPEN,
        ).exists()
        if already_open:
            raise serializers.ValidationError(
                "You already have an open cash session. "
                "Close it before opening a new one."
            )
        return attrs
 
    def create(self, validated_data):
        request = self.context["request"]
        validated_data["company"] = request.user.company
        validated_data["cashier"] = request.user
        return super().create(validated_data)
 
 
class CashSessionCloseSerializer(serializers.Serializer):
    """Closes an open cash session (shift end)."""
    closing_balance = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        help_text="Actual cash counted in the till at end of shift.",
    )
    closing_note = serializers.CharField(
        required=False,
        default="",
        max_length=500,
    )
 
 
class CashSessionSerializer(serializers.ModelSerializer):
    """Read — full detail of a cash session."""
    cashier_email    = serializers.EmailField(source="cashier.email",           read_only=True)
    company_name     = serializers.CharField(source="company.business_name",    read_only=True)
    total_sales      = serializers.SerializerMethodField()
    total_cash_sales = serializers.SerializerMethodField()
 
    class Meta:
        model  = CashSession
        fields = [
            "id",
            "company",
            "company_name",
            "cashier",
            "cashier_email",
            "status",
            "opening_balance",
            "opening_note",
            "opened_at",
            "closing_balance",
            "expected_cash",
            "cash_difference",
            "closed_at",
            "closing_note",
            "total_sales",
            "total_cash_sales",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
 
    def get_total_sales(self, obj):
        """Total number of completed sales in this session."""
        return obj.sales.filter(status=SaleStatus.COMPLETED).count()
 
    def get_total_cash_sales(self, obj):
        """Total cash collected in this session."""
        from django.db.models import Sum
        result = SalePayment.objects.filter(
            sale__cash_session=obj,
            sale__status=SaleStatus.COMPLETED,
            payment_method=PaymentMethod.CASH,
        ).aggregate(total=Sum("amount"))["total"]
        return result or 0
 
 
# ---------------------------------------------------------------------------
# SaleLine
# ---------------------------------------------------------------------------
 
class SaleLineSerializer(serializers.ModelSerializer):
    """Read — shows a sale line with all snapshot fields."""
 
    class Meta:
        model  = SaleLine
        fields = [
            "id",
            "product",
            "product_name",
            "hs_code",
            "unit_of_measure",
            "fbr_sale_type",
            "tax_rate_percent",
            "quantity",
            "unit_price",
            "discount_amount",
            "value_excl_tax",
            "sales_tax_applicable",
            "sales_tax_withheld",
            "further_tax",
            "extra_tax",
            "fed_payable",
            "fixed_retail_price",
            "sro_schedule_no",
            "sro_item_serial_no",
            "line_total",
            "created_at",
        ]
        read_only_fields = fields
 
 
class AddSaleLineSerializer(serializers.Serializer):
    """
    Add a product line to a DRAFT sale.
 
    Validates:
    - Product belongs to same company
    - Product is active
    - Stock is sufficient (if track_inventory=True)
    - Sale is still in DRAFT status
    """
    product_id      = serializers.IntegerField()
    quantity        = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=0.001
    )
    discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2,
        min_value=0, default=0, required=False,
    )
 
    def validate(self, attrs):
        from .models import Product
        request    = self.context["request"]
        sale       = self.context["sale"]
        product_id = attrs["product_id"]
        quantity   = float(attrs["quantity"])
 
        # Sale must be DRAFT
        if sale.status != SaleStatus.DRAFT:
            raise serializers.ValidationError(
                "Cannot modify a sale that is not in DRAFT status."
            )
 
        # Product must exist and belong to same company
        try:
            product = Product.objects.get(
                pk=product_id,
                company=request.user.company,
                is_active=True,
            )
        except Product.DoesNotExist:
            raise serializers.ValidationError({
                "product_id": "Product not found or does not belong to your company."
            })
 
        # Stock check — block if insufficient
        if product.track_inventory and float(product.current_stock) < quantity:
            raise serializers.ValidationError({
                "quantity": (
                    f"Insufficient stock for '{product.name}'. "
                    f"Available: {product.current_stock}, "
                    f"Requested: {quantity}."
                )
            })
 
        attrs["product"] = product
        return attrs
 
 
# ---------------------------------------------------------------------------
# SalePayment
# ---------------------------------------------------------------------------
 
class SalePaymentSerializer(serializers.ModelSerializer):
    """Read — shows a payment row."""
    payment_method_display = serializers.CharField(
        source="get_payment_method_display", read_only=True
    )
 
    class Meta:
        model  = SalePayment
        fields = [
            "id",
            "payment_method",
            "payment_method_display",
            "amount",
            "cheque_number",
            "cheque_bank",
            "cheque_date",
            "bank_reference",
            "bank_name",
            "card_last_four",
            "card_type",
            "created_at",
        ]
        read_only_fields = fields
 
 
class AddSalePaymentSerializer(serializers.Serializer):
    """
    Add a payment to a DRAFT sale.
    A sale can have multiple payments (split payment).
    """
    payment_method  = serializers.ChoiceField(choices=PaymentMethod.choices)
    amount          = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=0.01
    )
    # Cheque fields
    cheque_number   = serializers.CharField(max_length=50,  required=False, default="")
    cheque_bank     = serializers.CharField(max_length=100, required=False, default="")
    cheque_date     = serializers.DateField(required=False, allow_null=True, default=None)
    # Bank transfer fields
    bank_reference  = serializers.CharField(max_length=100, required=False, default="")
    bank_name       = serializers.CharField(max_length=100, required=False, default="")
    # Card fields
    card_last_four  = serializers.CharField(max_length=4,   required=False, default="")
    card_type       = serializers.CharField(max_length=20,  required=False, default="")
 
    def validate(self, attrs):
        sale   = self.context["sale"]
        method = attrs["payment_method"]
 
        # Sale must be DRAFT
        if sale.status != SaleStatus.DRAFT:
            raise serializers.ValidationError(
                "Cannot add payment to a sale that is not in DRAFT status."
            )
 
        # Cheque fields required if method is cheque
        if method == PaymentMethod.CHEQUE and not attrs.get("cheque_number"):
            raise serializers.ValidationError({
                "cheque_number": "Cheque number is required for cheque payments."
            })
 
        # Bank transfer fields required if method is bank transfer
        if method == PaymentMethod.BANK_TRANSFER and not attrs.get("bank_reference"):
            raise serializers.ValidationError({
                "bank_reference": "Bank reference is required for bank transfer payments."
            })
 
        # Check company module for cheque/bank transfer
        request = self.context["request"]
        company = request.user.company
        if method in (PaymentMethod.CHEQUE, PaymentMethod.BANK_TRANSFER):
            if not company.module_cheque_bank_transfer:
                raise serializers.ValidationError(
                    f"Your company does not have the "
                    f"'Cheques + Bank Transfers' module enabled."
                )
 
        return attrs
 
 
# ---------------------------------------------------------------------------
# Sale
# ---------------------------------------------------------------------------
 
class SaleListSerializer(serializers.ModelSerializer):
    """Lightweight — for sale history list."""
    customer_name            = serializers.CharField(source="customer.name",      read_only=True)
    cashier_email            = serializers.CharField(source="cashier.email",      read_only=True)
    status_display           = serializers.CharField(source="get_status_display", read_only=True)
    fbr_status_display       = serializers.CharField(
        source="get_fbr_submission_status_display", read_only=True
    )
 
    class Meta:
        model  = Sale
        fields = [
            "id",
            "sale_number",
            "status",
            "status_display",
            "sale_type",
            "customer_name",
            "cashier_email",
            "total_amount",
            "amount_paid",
            "fbr_submission_status",
            "fbr_status_display",
            "fbr_invoice_number",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields
 
 
class SaleDetailSerializer(serializers.ModelSerializer):
    """
    Full detail — includes lines, payments, all FBR fields.
    Used for receipt printing and sale review.
    """
    lines                    = SaleLineSerializer(many=True, read_only=True)
    payments                 = SalePaymentSerializer(many=True, read_only=True)
    customer_name            = serializers.CharField(source="customer.name",      read_only=True)
    customer_ntn_cnic        = serializers.CharField(source="customer.ntn_cnic",  read_only=True)
    cashier_email            = serializers.CharField(source="cashier.email",      read_only=True)
    company_name             = serializers.CharField(
        source="company.business_name", read_only=True
    )
    status_display           = serializers.CharField(source="get_status_display", read_only=True)
    fbr_status_display       = serializers.CharField(
        source="get_fbr_submission_status_display", read_only=True
    )
 
    class Meta:
        model  = Sale
        fields = [
            "id",
            "sale_number",
            "company",
            "company_name",
            "cashier",
            "cashier_email",
            "cash_session",
            "customer",
            "customer_name",
            "customer_ntn_cnic",
            "sale_type",
            "status",
            "status_display",
            # Financial totals
            "subtotal",
            "total_discount",
            "total_tax",
            "total_further_tax",
            "total_fed",
            "total_amount",
            "amount_paid",
            "change_given",
            # FBR
            "fbr_submission_status",
            "fbr_status_display",
            "fbr_invoice_number",
            "fbr_scenario_id",
            "fbr_submitted_at",
            "fbr_error_code",
            "fbr_error_message",
            "fbr_qr_code",
            # Notes
            "notes",
            "original_sale",
            # Timestamps
            "completed_at",
            "created_at",
            "updated_at",
            # Nested
            "lines",
            "payments",
        ]
        read_only_fields = fields
 
 
class CreateSaleSerializer(serializers.ModelSerializer):
    """
    Creates a new DRAFT sale.
    Lines and payments are added separately via dedicated endpoints.
    """
    class Meta:
        model  = Sale
        fields = ["customer", "cash_session", "sale_type", "notes"]
 
    def validate_customer(self, customer):
        """Customer must belong to same company."""
        request = self.context["request"]
        if customer.company != request.user.company:
            raise serializers.ValidationError(
                "Customer does not belong to your company."
            )
        if not customer.is_active:
            raise serializers.ValidationError(
                f"Customer '{customer.name}' is inactive."
            )
        return customer
 
    def validate_cash_session(self, session):
        """Cash session must be open and belong to this cashier."""
        from .models import CashSessionStatus
        if session and session.status != CashSessionStatus.OPEN:
            raise serializers.ValidationError(
                "Selected cash session is not open."
            )
        if session and session.cashier != self.context["request"].user:
            raise serializers.ValidationError(
                "Cash session does not belong to you."
            )
        return session
 
    def create(self, validated_data):
        request = self.context["request"]
        validated_data["company"] = request.user.company
        validated_data["cashier"] = request.user
        validated_data["status"]  = SaleStatus.DRAFT
        return super().create(validated_data)
 
 
class CompleteSaleSerializer(serializers.Serializer):
    """
    Validates that a DRAFT sale is ready to be completed.
    Checks lines exist and payments cover the total.
    """
 
    def validate(self, attrs):
        sale = self.context["sale"]
 
        # Must be DRAFT
        if sale.status != SaleStatus.DRAFT:
            raise serializers.ValidationError(
                f"Sale is already {sale.get_status_display()}."
            )
 
        # Must have at least one line
        if not sale.lines.exists():
            raise serializers.ValidationError(
                "Cannot complete a sale with no items."
            )
 
        # Recompute totals before checking payment
        sale.compute_totals()
        sale.refresh_from_db()
 
        # Payments must cover total
        from django.db.models import Sum
        total_paid = sale.payments.aggregate(
            total=Sum("amount")
        )["total"] or 0
 
        if float(total_paid) < float(sale.total_amount):
            shortage = float(sale.total_amount) - float(total_paid)
            raise serializers.ValidationError(
                f"Payment is short by Rs. {shortage:.2f}. "
                f"Total: {sale.total_amount}, Paid: {total_paid}."
            )
 
        return attrs
    
"""
========================================================
pos/return_serializers.py
Add to pos/serializers.py
========================================================
"""
 
from rest_framework import serializers
 
 
class SaleReturnLineInputSerializer(serializers.Serializer):
    """Input for one return line."""
    original_line_id  = serializers.IntegerField()
    quantity_returned = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=0.001
    )
 
 
class CreateReturnSerializer(serializers.Serializer):
    """
    Creates a return against a completed sale.
 
    Body:
    {
        "original_sale_id": 5,
        "reason": "defective",
        "reason_notes": "Screen cracked on delivery",
        "lines": [
            {"original_line_id": 12, "quantity_returned": 1},
            {"original_line_id": 13, "quantity_returned": 2}
        ]
    }
 
    For full return — pass all lines with full quantities.
    For partial return — pass only the lines being returned.
    """
    original_sale_id = serializers.IntegerField()
    reason           = serializers.ChoiceField(choices=ReturnReason.choices)
    reason_notes     = serializers.CharField(
        required=False, default="", max_length=500
    )
    lines = serializers.ListField(
        child=SaleReturnLineInputSerializer(),
        min_length=1,
        help_text="At least one line must be returned.",
    )
 
    def validate_original_sale_id(self, sale_id):
        from pos.models import Sale, SaleStatus
        request = self.context["request"]
        try:
            sale = Sale.objects.get(
                pk      = sale_id,
                company = request.user.company,
                status  = SaleStatus.COMPLETED,
            )
        except Sale.DoesNotExist:
            raise serializers.ValidationError(
                "Sale not found, does not belong to your company, "
                "or is not in COMPLETED status."
            )
 
        # Check FBR invoice exists
        if not sale.fbr_invoice_number and sale.company.module_fbr_di:
            raise serializers.ValidationError(
                "This sale has not been submitted to FBR yet. "
                "Wait for FBR submission to complete before processing a return."
            )
 
        # Check if already fully returned
        from pos.models import SaleReturn, ReturnStatus
        existing_returns = SaleReturn.objects.filter(
            original_sale = sale,
            status        = ReturnStatus.COMPLETED,
            return_type   = "full",
        )
        if existing_returns.exists():
            raise serializers.ValidationError(
                "This sale has already been fully returned."
            )
 
        self.context["original_sale"] = sale
        return sale_id
 
    def validate_lines(self, lines):
        """Validate each return line against original sale lines."""
        from pos.models import SaleLine
        from pos.models import SaleReturnLine
 
        original_sale = self.context.get("original_sale")
        if not original_sale:
            return lines
 
        validated_lines = []
        for line_data in lines:
            line_id  = line_data["original_line_id"]
            qty      = line_data["quantity_returned"]
 
            # Line must exist on original sale
            try:
                original_line = SaleLine.objects.get(
                    pk=line_id, sale=original_sale
                )
            except SaleLine.DoesNotExist:
                raise serializers.ValidationError(
                    f"Line {line_id} does not belong to this sale."
                )
 
            # Quantity cannot exceed original
            if float(qty) > float(original_line.quantity):
                raise serializers.ValidationError(
                    f"Return quantity ({qty}) for '{original_line.product_name}' "
                    f"exceeds original quantity ({original_line.quantity})."
                )
 
            # Check already-returned quantity for this line
            already_returned = SaleReturnLine.objects.filter(
                original_line=original_line,
                sale_return__status="completed",
            ).aggregate(
                total=models.Sum("quantity_returned")
            )["total"] or 0
 
            remaining = float(original_line.quantity) - float(already_returned)
            if float(qty) > remaining:
                raise serializers.ValidationError(
                    f"Only {remaining} units of '{original_line.product_name}' "
                    f"are available for return."
                )
 
            line_data["original_line_obj"] = original_line
            validated_lines.append(line_data)
 
        return validated_lines
 
 
class SaleReturnLineSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SaleReturnLine
        fields = [
            "id", "product_name", "quantity_returned",
            "unit_price", "tax_rate_percent",
            "return_value_excl_tax", "return_tax",
            "return_line_total", "stock_restored",
        ]
        read_only_fields = fields
 
 
class SaleReturnSerializer(serializers.ModelSerializer):
    """Full return detail."""
    lines                = SaleReturnLineSerializer(many=True, read_only=True)
    original_sale_number = serializers.CharField(
        source="original_sale.sale_number", read_only=True
    )
    credit_note_number   = serializers.CharField(
        source="credit_note_sale.sale_number",
        read_only=True, default=None,
    )
    fbr_credit_note_number = serializers.CharField(
        source="credit_note_sale.fbr_invoice_number",
        read_only=True, default=None,
    )
    processed_by_email   = serializers.EmailField(
        source="processed_by.email", read_only=True
    )
 
    class Meta:
        model  = SaleReturn
        fields = [
            "id",
            "return_number",
            "return_type",
            "status",
            "reason",
            "reason_notes",
            "original_sale",
            "original_sale_number",
            "credit_note_sale",
            "credit_note_number",
            "fbr_credit_note_number",
            "total_return_amount",
            "total_return_tax",
            "refund_amount",
            "refund_paid",
            "refund_paid_at",
            "fbr_eligible",
            "fbr_eligibility_reason",
            "processed_by",
            "processed_by_email",
            "lines",
            "created_at",
            "completed_at",
        ]
        read_only_fields = fields