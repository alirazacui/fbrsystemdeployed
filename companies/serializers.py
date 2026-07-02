"""
companies/serializers.py
"""

from rest_framework import serializers
from .models import Company


class CompanyListSerializer(serializers.ModelSerializer):
    """
    Lightweight — used for lists and dropdowns.
    Only the fields needed to identify a company at a glance.
    """
    owner_email = serializers.SerializerMethodField()
    subscription_active = serializers.BooleanField(
        source="is_subscription_active", read_only=True
    )

    class Meta:
        model = Company
        fields = [
            "id",
            "business_name",
            "ntn",
            "vertical",
            "subscription_plan",
            "subscription_status",
            "subscription_active",
            "is_active",
            "owner_email",
            "created_at",
        ]
        read_only_fields = fields

    def get_owner_email(self, obj):
        owner = obj.owner  # uses the property on Company
        return owner.email if owner else None


class CompanyDetailSerializer(serializers.ModelSerializer):
    """
    Full detail — used for create, retrieve, update.
    Includes all fields including modules and FBR sandbox state.
    """
    owner_email = serializers.SerializerMethodField()
    owner_id    = serializers.SerializerMethodField()
    enabled_modules = serializers.ListField(
        source="get_enabled_modules", read_only=True
    )

    class Meta:
        model = Company
        fields = [
            # ── Core identity ──────────────────────────────
            "id",
            "business_name",
            "ntn",
            "strn",
            "owner_cnic",

            # ── FBR / regulatory ───────────────────────────
            "business_mode",
            "fbr_business_nature",
            "fbr_sector",

            # ── Our own classification ─────────────────────
            "vertical",

            # ── Contact & branding ─────────────────────────
            "logo",
            "address",
            "phone",
            "email",
            "website_url",

            # ── Subscription ───────────────────────────────
            "subscription_plan",
            "subscription_status",
            "subscription_start_date",
            "subscription_expiry_date",
            "next_billing_date",

            # ── Modules ────────────────────────────────────
            "module_invoices",
            "module_fbr_di",
            "module_customer_db",
            "module_multi_branch",
            "module_terminals_cash_sessions",
            "module_inventory",
            "module_warehousing",
            "module_returns",
            "module_debit_credit_notes",
            "module_fbr_amendments",
            "module_cheque_bank_transfer",
            "module_customer_display",
            "module_hardware_integration",
            "module_restaurant_fnb",
            "module_basic_reports",
            "module_advanced_reports",
            "module_audit_logs",
            "enabled_modules",           # computed, read-only

            # ── FBR sandbox ────────────────────────────────
            "fbr_sandbox_token",
            "fbr_production_token",
            "fbr_sandbox_endpoint",
            "fbr_production_endpoint",
            "fbr_test_buyer_ntn",
            "fbr_sandbox_complete",
            "fbr_ip_1",
            "fbr_ip_2",
            "fbr_ip_3",
            "fbr_crm_user_id",

            # ── Sandbox scenarios ──────────────────────────
            "fbr_scenario_sn001",
            "fbr_scenario_sn002",
            "fbr_scenario_sn003",
            "fbr_scenario_sn004",
            "fbr_scenario_sn005",
            "fbr_scenario_sn006",
            "fbr_scenario_sn007",
            "fbr_scenario_sn008",
            "fbr_scenario_sn009",
            "fbr_scenario_sn010",
            "fbr_scenario_sn011",
            "fbr_scenario_sn012",
            "fbr_scenario_sn013",
            "fbr_scenario_sn014",
            "fbr_scenario_sn015",
            "fbr_scenario_sn016",
            "fbr_scenario_sn017",
            "fbr_scenario_sn018",
            "fbr_scenario_sn019",
            "fbr_scenario_sn020",
            "fbr_scenario_sn021",
            "fbr_scenario_sn022",
            "fbr_scenario_sn023",
            "fbr_scenario_sn024",
            "fbr_scenario_sn025",
            "fbr_scenario_sn026",
            "fbr_scenario_sn027",
            "fbr_scenario_sn028",

            # ── Internal admin ─────────────────────────────
            "account_manager",
            "internal_notes",
            "tags",

            # ── Status & timestamps ────────────────────────
            "is_active",
            "created_at",
            "updated_at",

            # ── Computed ───────────────────────────────────
            "owner_email",
            "owner_id",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "owner_email",
            "owner_id",
            "enabled_modules",
            "fbr_sandbox_complete",     # set by system, not manually
        ]

    def get_owner_email(self, obj):
        owner = obj.owner
        return owner.email if owner else None

    def get_owner_id(self, obj):
        owner = obj.owner
        return owner.id if owner else None

    def validate_fbr_business_nature(self, value):
        """Ensure at least one business nature is selected."""
        if not value:
            raise serializers.ValidationError(
                "At least one FBR Business Nature must be selected."
            )
        return value

    def validate_ntn(self, value):
        """NTN must be numeric digits only."""
        cleaned = value.replace("-", "").strip()
        if not cleaned.isdigit():
            raise serializers.ValidationError(
                "NTN must contain digits only (dashes are stripped automatically)."
            )
        return cleaned

    def validate_owner_cnic(self, value):
        """CNIC: strip dashes and validate 13 digits."""
        cleaned = value.replace("-", "").strip()
        if not cleaned.isdigit() or len(cleaned) != 13:
            raise serializers.ValidationError(
                "CNIC must be exactly 13 digits (format: 00000-0000000-0)."
            )
        return value  # keep original formatted value


class CompanyModulesSerializer(serializers.ModelSerializer):
    """
    Thin serializer just for updating a company's module toggles.
    Used by Admin when enabling/disabling features for a company.
    Separate from CompanyDetailSerializer so the endpoint is explicit
    and can't accidentally update business identity fields.
    """

    class Meta:
        model = Company
        fields = [
            "module_invoices",
            "module_fbr_di",
            "module_customer_db",
            "module_multi_branch",
            "module_terminals_cash_sessions",
            "module_inventory",
            "module_warehousing",
            "module_returns",
            "module_debit_credit_notes",
            "module_fbr_amendments",
            "module_cheque_bank_transfer",
            "module_customer_display",
            "module_hardware_integration",
            "module_restaurant_fnb",
            "module_basic_reports",
            "module_advanced_reports",
            "module_audit_logs",
        ]


from pos.models import CompanyPaymentMethodSettings

class CompanyPaymentMethodSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyPaymentMethodSettings
        fields = [
            "id",
            "is_cash_enabled",
            "is_card_enabled",
            "is_easypaisa_enabled",
            "is_jazzcash_enabled",
            "is_raast_enabled",
            "is_bank_transfer_enabled",
            "is_cheque_enabled",
            "easypaisa_merchant_id",
            "easypaisa_qr_image",
            "jazzcash_merchant_id",
            "jazzcash_qr_image",
            "raast_iban",
            "raast_qr_image",
            "bank_name",
            "bank_account_name",
            "bank_iban",
        ]

    def validate(self, attrs):
        # 1. EasyPaisa validation
        is_ep_enabled = attrs.get("is_easypaisa_enabled", self.instance.is_easypaisa_enabled if self.instance else False)
        if is_ep_enabled:
            ep_merchant = attrs.get("easypaisa_merchant_id", self.instance.easypaisa_merchant_id if self.instance else "").strip()
            ep_qr = attrs.get("easypaisa_qr_image", self.instance.easypaisa_qr_image if self.instance else None)
            if not ep_merchant or not ep_qr:
                raise serializers.ValidationError({
                    "is_easypaisa_enabled": "You must provide both Merchant ID and QR Image before enabling EasyPaisa."
                })

        # 2. JazzCash validation
        is_jc_enabled = attrs.get("is_jazzcash_enabled", self.instance.is_jazzcash_enabled if self.instance else False)
        if is_jc_enabled:
            jc_merchant = attrs.get("jazzcash_merchant_id", self.instance.jazzcash_merchant_id if self.instance else "").strip()
            jc_qr = attrs.get("jazzcash_qr_image", self.instance.jazzcash_qr_image if self.instance else None)
            if not jc_merchant or not jc_qr:
                raise serializers.ValidationError({
                    "is_jazzcash_enabled": "You must provide both Merchant ID and QR Image before enabling JazzCash."
                })

        # 3. Raast validation
        is_raast_enabled = attrs.get("is_raast_enabled", self.instance.is_raast_enabled if self.instance else False)
        if is_raast_enabled:
            raast_iban = attrs.get("raast_iban", self.instance.raast_iban if self.instance else "").strip()
            raast_qr = attrs.get("raast_qr_image", self.instance.raast_qr_image if self.instance else None)
            if not raast_iban or not raast_qr:
                raise serializers.ValidationError({
                    "is_raast_enabled": "You must provide both IBAN (receiver) and QR Image before enabling Raast."
                })

        # 4. Bank Transfer validation
        is_bank_enabled = attrs.get("is_bank_transfer_enabled", self.instance.is_bank_transfer_enabled if self.instance else False)
        if is_bank_enabled:
            bank_name = attrs.get("bank_name", self.instance.bank_name if self.instance else "").strip()
            acc_name = attrs.get("bank_account_name", self.instance.bank_account_name if self.instance else "").strip()
            iban = attrs.get("bank_iban", self.instance.bank_iban if self.instance else "").strip()
            if not bank_name or not acc_name or not iban:
                raise serializers.ValidationError({
                    "is_bank_transfer_enabled": "You must provide Bank Name, Account Name, and IBAN before enabling Bank Transfer."
                })

        return attrs