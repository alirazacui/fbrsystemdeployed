from rest_framework import serializers
from .models import *
 
class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Full plan detail with limit displays."""
 
    max_products_display      = serializers.SerializerMethodField()
    max_users_display         = serializers.SerializerMethodField()
    max_customers_display     = serializers.SerializerMethodField()
    max_sales_display         = serializers.SerializerMethodField()
 
    class Meta:
        model  = SubscriptionPlan
        fields = [
            "id", "code", "name", "description", "is_trial", "is_active",
            "price_per_month", "price_per_year", "duration_days", "sort_order",
            "max_products", "max_products_display",
            "max_users",    "max_users_display",
            "max_customers","max_customers_display",
            "max_sales_per_month", "max_sales_display",
            "max_categories",
            "includes_fbr_di", "includes_inventory",
            "includes_warehousing", "includes_advanced_reports",
            "includes_audit_logs", "includes_hardware_integration",
            "includes_restaurant_fnb", "includes_multi_branch",
            "includes_debit_credit_notes", "includes_returns",
            "includes_cheque_bank",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
 
    def get_max_products_display(self, obj):
        return obj.get_limit_display("max_products")
 
    def get_max_users_display(self, obj):
        return obj.get_limit_display("max_users")
 
    def get_max_customers_display(self, obj):
        return obj.get_limit_display("max_customers")
 
    def get_max_sales_display(self, obj):
        return obj.get_limit_display("max_sales_per_month")
 
 
class CompanySubscriptionSerializer(serializers.ModelSerializer):
    """Full subscription detail."""
    plan_name       = serializers.CharField(source="plan.name",             read_only=True)
    company_name    = serializers.CharField(source="company.business_name", read_only=True)
    days_remaining  = serializers.IntegerField(read_only=True)
    is_active       = serializers.BooleanField(read_only=True)
    is_expiring_soon = serializers.BooleanField(read_only=True)
    assigned_by_email = serializers.EmailField(
        source="assigned_by.email", read_only=True, default=None
    )
 
    class Meta:
        model  = CompanySubscription
        fields = [
            "id", "company", "company_name",
            "plan", "plan_name", "status",
            "start_date", "expiry_date",
            "days_remaining", "is_active", "is_expiring_soon",
            "extended_by_days", "extension_notes",
            "expiry_warning_sent", "expiry_warning_sent_at",
            "assigned_by", "assigned_by_email",
            "notes", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "days_remaining", "is_active", "is_expiring_soon",
            "extended_by_days", "extension_notes",
            "expiry_warning_sent", "expiry_warning_sent_at",
            "assigned_by", "assigned_by_email",
            "created_at", "updated_at",
        ]
 
 
class AssignPlanSerializer(serializers.Serializer):
    """Admin assigns a plan to a company."""
    company_id = serializers.IntegerField()
    plan_id    = serializers.IntegerField()
    notes      = serializers.CharField(required=False, default="", max_length=500)
 
    def validate(self, attrs):
        from companies.models import Company
 
        try:
            company = Company.objects.get(pk=attrs["company_id"])
        except Company.DoesNotExist:
            raise serializers.ValidationError({"company_id": "Company not found."})
 
        try:
            plan = SubscriptionPlan.objects.get(pk=attrs["plan_id"], is_active=True)
        except SubscriptionPlan.DoesNotExist:
            raise serializers.ValidationError({"plan_id": "Plan not found or inactive."})
 
        # Trial plan can only be used once per company
        if plan.is_trial:
            used_trial = SubscriptionHistory.objects.filter(
                company = company,
                plan__is_trial = True,
            ).exists()
            if used_trial:
                raise serializers.ValidationError(
                    f"{company.business_name} has already used a trial plan. "
                    f"Assign a paid plan instead."
                )
 
        attrs["company"] = company
        attrs["plan"]    = plan
        return attrs
 
 
class ExtendSubscriptionSerializer(serializers.Serializer):
    """Admin extends a subscription."""
    days  = serializers.IntegerField(min_value=1, max_value=365)
    notes = serializers.CharField(required=False, default="", max_length=500)