from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User, UserStatus
 
 
@admin.register(User)
class UserAdmin(BaseUserAdmin):
 
    # ── List view ──────────────────────────────────────────────────────
    list_display = [
        "email",
        "full_name_display",
        "role",
        "status",
        "company_link",
        "date_joined",
    ]
    list_filter  = ["role", "status", "company"]
    search_fields = ["email", "first_name", "last_name", "company__business_name"]
    ordering      = ["-date_joined"]
    readonly_fields = [
        "date_joined",
        "updated_at",
        "last_login",
        "created_by",
        "full_name_display",
        "company_link",
        "permission_summary",
    ]
 
    # ── Detail view ────────────────────────────────────────────────────
    fieldsets = (
        ("Login Credentials", {
            "fields": ("email", "password")
        }),
        ("Personal Details", {
            "fields": (
                "first_name",
                "last_name",
                "full_name_display",
                "phone",
            )
        }),
        ("Role & Company", {
            "fields": (
                "role",
                "company",
                "company_link",
            )
        }),
        ("Account Status", {
            "fields": ("status",)
        }),
        ("Permissions Summary", {
            "classes": ("collapse",),
            "fields": ("permission_summary",)
        }),
        ("Audit", {
            "fields": (
                "created_by",
                "date_joined",
                "updated_at",
                "last_login",
            )
        }),
    )
 
    add_fieldsets = (
        ("Create New User", {
            "classes": ("wide",),
            "fields": (
                "email",
                "first_name",
                "last_name",
                "phone",
                "role",
                "company",
                "status",
                "password1",
                "password2",
            ),
        }),
    )
 
    # Override default UserAdmin filter_horizontal (we don't use Django's groups/permissions)
    filter_horizontal = []
 
    # ── Custom display methods ─────────────────────────────────────────
 
    def full_name_display(self, obj):
        return obj.get_full_name() or "—"
    full_name_display.short_description = "Full Name"
 
    def company_link(self, obj):
        if obj.company:
            return format_html(
                '<a href="/admin/companies/company/{}/change/">{}</a>',
                obj.company.id,
                obj.company.business_name,
            )
        return format_html(
    '<span style="color:{};">{}</span>',
    'gray',
    'Platform User'
)
    company_link.short_description = "Company"
 
    def permission_summary(self, obj):
        if obj.is_platform_admin:
            return format_html(
                '<span style="color:green;font-weight:bold;">Platform Admin — all permissions bypassed</span>'
            )
        from permission_app.models import UserPermission
        perms = UserPermission.objects.filter(user=obj).select_related("permission")
        if not perms.exists():
            return format_html('<span style="color:orange;">No permissions assigned yet</span>')
        items = "".join(
            f'<li>{p.permission.label}</li>'
            for p in perms
        )
        return format_html(
            f'<ul style="margin:0;padding-left:16px;max-height:200px;overflow-y:auto;">{items}</ul>'
        )
    permission_summary.short_description = "Granted Permissions"
 