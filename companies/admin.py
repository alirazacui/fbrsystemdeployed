"""
companies/admin.py
Fixed: format_html cannot take f-strings — use mark_safe for pre-built HTML.
"""
from django.contrib import admin
from django.utils.html import format_html, mark_safe
from .models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):

    # ── List view ──────────────────────────────────────────────────────
    list_display = [
        "business_name",
        "ntn",
        "vertical",
        "business_mode",
        "subscription_plan",
        "subscription_status",
        "is_active",
        "logo_preview",
        "created_at",
    ]
    list_filter = [
        "is_active",
        "business_mode",
        "vertical",
        "subscription_plan",
        "subscription_status",
        "fbr_sector",
    ]
    search_fields = ["business_name", "ntn", "strn", "owner_cnic", "email"]
    ordering      = ["-created_at"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "logo_preview",
        "owner_info",
        "enabled_modules_display",
        "assigned_scenarios_display",
    ]

    # ── Detail view fieldsets ──────────────────────────────────────────
    fieldsets = (
        ("Core Business Identity", {
            "fields": (
                "business_name",
                "ntn",
                "strn",
                "owner_cnic",
                "owner_info",
            )
        }),

        ("FBR / Regulatory", {
            "fields": (
                "business_mode",
                "fbr_business_nature",
                "fbr_sector",
            )
        }),

        ("Our Classification", {
            "fields": ("vertical",)
        }),

        ("Contact & Branding", {
            "fields": (
                "logo",
                "logo_preview",
                "address",
                "phone",
                "email",
                "website_url",
            )
        }),

        ("Subscription", {
            "fields": (
                "subscription_plan",
                "subscription_status",
                "subscription_start_date",
                "subscription_expiry_date",
                "next_billing_date",
            )
        }),

        ("Modules — Sales & FBR (Forced)", {
            "description": (
                "These three modules are FORCED and cannot be disabled. "
                "They are the core of the platform."
            ),
            "fields": (
                "module_invoices",
                "module_fbr_di",
                "module_customer_db",
            )
        }),

        ("Modules — Multi-Location", {
            "classes": ("collapse",),
            "fields": (
                "module_multi_branch",
                "module_terminals_cash_sessions",
                "module_inventory",
                "module_warehousing",
            )
        }),

        ("Modules — Operations", {
            "classes": ("collapse",),
            "fields": (
                "module_returns",
                "module_debit_credit_notes",
                "module_fbr_amendments",
                "module_cheque_bank_transfer",
                "module_customer_display",
                "module_hardware_integration",
            )
        }),

        ("Modules — Restaurant / F&B", {
            "classes": ("collapse",),
            "fields": (
                "module_restaurant_fnb",
            )
        }),

        ("Modules — Insights", {
            "classes": ("collapse",),
            "fields": (
                "module_basic_reports",
                "module_advanced_reports",
                "module_audit_logs",
            )
        }),

        ("Enabled Modules Summary", {
            "classes": ("collapse",),
            "fields": ("enabled_modules_display",)
        }),

        ("FBR Sandbox — Tokens & IP Whitelisting", {
            "classes": ("collapse",),
            "fields": (
                "fbr_sandbox_token",
                "fbr_production_token",
                "fbr_test_buyer_ntn",
                "fbr_sandbox_complete",
                "fbr_ip_1",
                "fbr_ip_2",
                "fbr_ip_3",
                "fbr_crm_user_id",
            )
        }),

        ("FBR Sandbox Scenarios — Assigned from IRIS", {
            "classes": ("collapse",),
            "description": (
                "Tick exactly the scenarios IRIS assigned to this tenant. "
                "Based on their Business Nature + Sector combination. "
                "Only needed for sandbox onboarding."
            ),
            "fields": (
                "assigned_scenarios_display",
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
            )
        }),

        ("Internal Admin Metadata", {
            "classes": ("collapse",),
            "fields": (
                "account_manager",
                "internal_notes",
                "tags",
            )
        }),

        ("Status & Timestamps", {
            "fields": (
                "is_active",
                "created_at",
                "updated_at",
            )
        }),
    )

    # ── Custom display methods ─────────────────────────────────────────

    def logo_preview(self, obj):
        if obj.logo:
            return format_html(
                '<img src="{}" style="height:40px; border-radius:4px;" />',
                obj.logo.url,
            )
        return "—"
    logo_preview.short_description = "Logo"

    def owner_info(self, obj):
        owner = obj.owner
        if owner:
            return format_html(
                "<strong>{}</strong> &lt;{}&gt;",
                owner.get_full_name() or "—",
                owner.email,
            )
        return mark_safe('<span style="color:orange;">⚠ No owner assigned yet</span>')
    owner_info.short_description = "Current Owner"

    def enabled_modules_display(self, obj):
        modules = obj.get_enabled_modules()
        if not modules:
            return "No modules enabled"
        items = "".join(
            '<li style="color:green;">✓ {}</li>'.format(
                m.replace("module_", "").replace("_", " ").title()
            )
            for m in modules
        )
        return mark_safe(
            '<ul style="margin:0;padding-left:16px;">{}</ul>'.format(items)
        )
    enabled_modules_display.short_description = "Currently Enabled Modules"

    def assigned_scenarios_display(self, obj):
        scenarios = obj.get_assigned_scenarios()
        if not scenarios:
            return mark_safe('<span style="color:gray;">No scenarios assigned yet</span>')
        items = "".join(
            '<li style="color:#0066cc;">☑ {}</li>'.format(s)
            for s in scenarios
        )
        return mark_safe(
            '<ul style="margin:0;padding-left:16px;">{}</ul>'.format(items)
        )
    assigned_scenarios_display.short_description = "Assigned Scenarios Summary"