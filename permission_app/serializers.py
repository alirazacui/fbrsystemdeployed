"""
permissions_app/serializers.py
"""

from rest_framework import serializers
from .models import Permission, UserPermission


class PermissionSerializer(serializers.ModelSerializer):
    """
    Read-only catalogue of all available permissions.
    Used to populate the permission panel in the UI.
    Grouped by module on the frontend using the `module` field.
    """
    module_display = serializers.CharField(source="get_module_display", read_only=True)
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model  = Permission
        fields = [
            "id",
            "module",
            "module_display",
            "action",
            "action_display",
            "codename",
            "label",
            "description",
            "is_active",
        ]
        read_only_fields = fields


class UserPermissionSerializer(serializers.ModelSerializer):
    """
    Read — shows a user's current permission grants.
    Includes enough detail to render the checkbox panel.
    """
    permission_codename    = serializers.CharField(source="permission.codename",            read_only=True)
    permission_label       = serializers.CharField(source="permission.label",               read_only=True)
    permission_module      = serializers.CharField(source="permission.module",              read_only=True)
    permission_module_display = serializers.CharField(source="permission.get_module_display", read_only=True)
    permission_action      = serializers.CharField(source="permission.action",              read_only=True)
    granted_by_email       = serializers.EmailField(source="granted_by.email",             read_only=True,
                                                    default=None)

    class Meta:
        model  = UserPermission
        fields = [
            "id",
            "user",
            "permission",
            "permission_codename",
            "permission_label",
            "permission_module",
            "permission_module_display",
            "permission_action",
            "granted_by",
            "granted_by_email",
            "granted_at",
        ]
        read_only_fields = [
            "id",
            "granted_by",
            "granted_by_email",
            "granted_at",
            "permission_codename",
            "permission_label",
            "permission_module",
            "permission_module_display",
            "permission_action",
        ]


class AssignPermissionsSerializer(serializers.Serializer):
    """
    Bulk assign permissions to a user.

    Accepts a list of permission IDs and replaces the user's current
    permission set with exactly that list — making it idempotent
    (safe to call multiple times with the same data).

    The company-module ceiling is enforced inside save().

    Request body:
        {
            "permission_ids": [1, 3, 7, 12]
        }
    """
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,   # allow_empty=True means "remove all permissions"
    )

    def validate_permission_ids(self, ids):
        """Check all IDs exist and are active."""
        permissions = Permission.objects.filter(id__in=ids, is_active=True)
        found_ids   = set(permissions.values_list("id", flat=True))
        missing     = set(ids) - found_ids
        if missing:
            raise serializers.ValidationError(
                f"Permission IDs not found or inactive: {sorted(missing)}"
            )
        return ids

    def save(self, user, granted_by):
        """
        Replace the user's permissions with the submitted list.

        Ceiling check: for client users, every permission's module must
        be enabled on their company. Raises ValidationError if not.
        """
        from .models import UserPermission, Permission

        permission_ids = self.validated_data["permission_ids"]
        permissions    = list(Permission.objects.filter(id__in=permission_ids, is_active=True))

        # ── Ceiling check ──────────────────────────────────────────────────
        if user.is_client_user and user.company_id:
            company = user.company
            blocked = []
            for perm in permissions:
                module_field = perm.module_field
                if module_field and not getattr(company, module_field, False):
                    blocked.append(perm.label)
            if blocked:
                raise serializers.ValidationError(
                    {
                        "permission_ids": (
                            f"These permissions cannot be granted — their module is not "
                            f"enabled for {company.business_name}: {', '.join(blocked)}"
                        )
                    }
                )

        # ── Replace: delete existing, bulk-create new ──────────────────────
        UserPermission.objects.filter(user=user).delete()
        UserPermission.objects.bulk_create(
            [
                UserPermission(
                    user       = user,
                    permission = perm,
                    granted_by = granted_by,
                )
                for perm in permissions
            ],
            ignore_conflicts=True,
        )
        return user


class CompanyPermissionPanelSerializer(serializers.Serializer):
    """
    Returns a structured permission panel for a specific user,
    filtered to only show modules their company has enabled.

    Used by the UI to render the checkbox grid.

    Response shape:
        [
            {
                "module": "fbr_di",
                "module_display": "FBR Digital Invoicing",
                "permissions": [
                    {"id": 1, "action": "view",   "label": "View FBR DI",   "granted": true},
                    {"id": 2, "action": "create", "label": "Create FBR DI", "granted": false},
                    ...
                ]
            },
            ...
        ]
    """

    def to_representation(self, user):
        from .models import Permission, UserPermission, MODULE_TO_COMPANY_FIELD, PermissionModule

        # Get the set of permission IDs this user currently holds
        granted_ids = set(
            UserPermission.objects
            .filter(user=user)
            .values_list("permission_id", flat=True)
        )

        # All active permissions, ordered by module then action
        all_permissions = Permission.objects.filter(is_active=True).order_by("module", "action")

        # Group by module
        grouped = {}
        for perm in all_permissions:
            # For client users, skip modules their company doesn't have
            if user.is_client_user and user.company_id:
                module_field = MODULE_TO_COMPANY_FIELD.get(perm.module)
                if module_field and not getattr(user.company, module_field, False):
                    continue  # company ceiling — hide this module entirely

            if perm.module not in grouped:
                grouped[perm.module] = {
                    "module":         perm.module,
                    "module_display": perm.get_module_display(),
                    "permissions":    [],
                }
            grouped[perm.module]["permissions"].append({
                "id":      perm.id,
                "action":  perm.action,
                "label":   perm.label,
                "codename": perm.codename,
                "granted": perm.id in granted_ids,
            })

        return list(grouped.values())