from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Permission, UserPermission
 
 
@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
 
    list_display  = ["codename", "label", "module", "action", "is_active"]
    list_filter   = ["module", "action", "is_active"]
    search_fields = ["codename", "label", "module"]
    ordering      = ["module", "action"]
    readonly_fields = ["codename"]
 
    fieldsets = (
        (None, {
            "fields": (
                "module",
                "action",
                "codename",
                "label",
                "description",
                "is_active",
            )
        }),
    )
 
 
@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
 
    list_display  = [
        "user_email",
        "permission_codename",
        "permission_module",
        "granted_by_email",
        "granted_at",
    ]
    list_filter   = ["permission__module", "permission__action"]
    search_fields = [
        "user__email",
        "permission__codename",
        "permission__label",
    ]
    ordering      = ["-granted_at"]
    readonly_fields = ["granted_at", "granted_by"]
 
    # ── Custom display methods ─────────────────────────────────────────
 
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "User"
 
    def permission_codename(self, obj):
        return obj.permission.codename
    permission_codename.short_description = "Permission"
 
    def permission_module(self, obj):
        return obj.permission.get_module_display()
    permission_module.short_description = "Module"
 
    def granted_by_email(self, obj):
        if obj.granted_by:
            return obj.granted_by.email
        return "System (auto-granted)"
    granted_by_email.short_description = "Granted By"
 