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
            "module_sales_invoicing",
            "module_fbr_di",
            "module_customer_db",
            "module_fbr_registered_buyer",
            "module_returns",
            "module_fbr_amendments",
            "module_cheque_bank_transfer",
            "module_customer_display",
            "module_hardware_integration",
            "module_inventory",
            "module_warehousing",
            "module_multi_location",
            "module_restaurant_fnb",
            "module_dine_in",
            "module_takeaway",
            "module_delivery",
            "module_table_floor_map",
            "module_kitchen_display",
            "module_basic_reports",
            "module_advanced_reports",
            "module_audit_logs",
            "enabled_modules",           # computed, read-only

            # ── FBR sandbox ────────────────────────────────
            "fbr_sandbox_token",
            "fbr_production_token",
            "fbr_assigned_scenarios",
            "fbr_test_buyer_ntn",
            "fbr_sandbox_complete",
            "fbr_ip_1",
            "fbr_ip_2",
            "fbr_ip_3",
            "fbr_crm_user_id",

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
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "owner_email",
            "enabled_modules",
            "fbr_sandbox_complete",     # set by system, not manually
        ]

    def get_owner_email(self, obj):
        owner = obj.owner
        return owner.email if owner else None

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
            "module_sales_invoicing",
            "module_fbr_di",
            "module_customer_db",
            "module_fbr_registered_buyer",
            "module_returns",
            "module_fbr_amendments",
            "module_cheque_bank_transfer",
            "module_customer_display",
            "module_hardware_integration",
            "module_inventory",
            "module_warehousing",
            "module_multi_location",
            "module_restaurant_fnb",
            "module_dine_in",
            "module_takeaway",
            "module_delivery",
            "module_table_floor_map",
            "module_kitchen_display",
            "module_basic_reports",
            "module_advanced_reports",
            "module_audit_logs",
        ]