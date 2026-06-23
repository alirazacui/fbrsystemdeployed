"""
permissions_app/migrations/0002_seed_permissions.py

Seeds the full Permission catalogue — all modules × all 6 actions.
Run automatically with: python manage.py migrate

To re-seed after adding new modules, create a new migration that
calls seed_permissions() again — existing rows are skipped (get_or_create).
"""

from django.db import migrations


# ── All module × action combinations to seed ───────────────────────────────
# Format: (module_value, action_value, human_label)

PERMISSIONS_TO_SEED = []

MODULES = [
    ("sales_invoicing",      "Sales Invoicing"),
    ("fbr_di",               "FBR Digital Invoicing"),
    ("customer_db",          "Customer Database"),
    ("fbr_registered_buyer", "FBR Registered Buyer"),
    ("returns",              "Returns & Debit/Credit Notes"),
    ("fbr_amendments",       "Manual FBR Amendments"),
    ("cheque_bank_transfer", "Cheque & Bank Transfer"),
    ("customer_display",     "Customer-Facing Display"),
    ("hardware_integration", "Hardware Integration"),
    ("inventory",            "Inventory Tracking"),
    ("warehousing",          "Warehousing"),
    ("multi_location",       "Multi-Location / Multi-Branch"),
    ("restaurant_fnb",       "Restaurant F&B"),
    ("dine_in",              "Dine-In"),
    ("takeaway",             "Takeaway"),
    ("delivery",             "Delivery"),
    ("table_floor_map",      "Table & Floor Map"),
    ("kitchen_display",      "Kitchen Display / KDS"),
    ("basic_reports",        "Basic Reports"),
    ("advanced_reports",     "Advanced Reports"),
    ("audit_logs",           "Audit Logs"),
    ("user_management",      "User Management"),
    ("company_management",   "Company Management"),
]

ACTIONS = [
    ("view",    "View"),
    ("create",  "Create"),
    ("edit",    "Edit"),
    ("delete",  "Delete"),
    ("export",  "Export"),
    ("approve", "Approve"),
]

for module_val, module_label in MODULES:
    for action_val, action_label in ACTIONS:
        PERMISSIONS_TO_SEED.append({
            "module":   module_val,
            "action":   action_val,
            "codename": f"{module_val}.{action_val}",
            "label":    f"{action_label} {module_label}",
        })


def seed_permissions(apps, schema_editor):
    Permission = apps.get_model("permission_app", "Permission")
    created_count = 0
    for perm_data in PERMISSIONS_TO_SEED:
        _, created = Permission.objects.get_or_create(
            codename = perm_data["codename"],
            defaults = {
                "module":      perm_data["module"],
                "action":      perm_data["action"],
                "label":       perm_data["label"],
                "description": "",
                "is_active":   True,
            },
        )
        if created:
            created_count += 1
    print(f"\n  ✓ Seeded {created_count} permissions ({len(PERMISSIONS_TO_SEED)} total defined)")


def unseed_permissions(apps, schema_editor):
    """Reverse migration — remove all seeded permissions."""
    Permission = apps.get_model("permission_app", "Permission")
    codenames  = [p["codename"] for p in PERMISSIONS_TO_SEED]
    deleted, _ = Permission.objects.filter(codename__in=codenames).delete()
    print(f"\n  ✓ Removed {deleted} seeded permissions")


class Migration(migrations.Migration):

    dependencies = [
        # Replace '0001_initial' with whatever your actual first migration is named
        ("permission_app", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_permissions, reverse_code=unseed_permissions),
    ]