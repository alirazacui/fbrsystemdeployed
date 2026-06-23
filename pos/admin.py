from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Category, Product

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ["name", "company", "is_active", "created_at"]
    list_filter   = ["is_active", "company"]
    search_fields = ["name", "company__business_name"]

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display  = ["name", "company", "category", "selling_price", 
                     "tax_rate_percent", "fbr_sale_type", "is_active"]
    list_filter   = ["is_active", "company", "category", "fbr_sale_type", "tax_rate_percent"]
    search_fields = ["name", "barcode", "sku", "hs_code"]


from .models import Category, Product, Customer

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display  = ["name", "ntn_cnic", "registration_type", 
                     "province", "company", "is_walk_in", "is_active"]
    list_filter   = ["registration_type", "is_walk_in", "is_active", "company"]
    search_fields = ["name", "ntn_cnic", "phone", "email"]
    readonly_fields = ["is_walk_in", "created_at", "updated_at"]


from .models import CashSession, Sale, SaleLine, SalePayment

@admin.register(CashSession)
class CashSessionAdmin(admin.ModelAdmin):
    list_display = ["cashier", "company", "status", "opening_balance", 
                    "closing_balance", "cash_difference", "opened_at"]
    list_filter  = ["status", "company"]

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ["sale_number", "company", "customer", "status",
                    "total_amount", "fbr_submission_status", "completed_at"]
    list_filter  = ["status", "fbr_submission_status", "company"]
    search_fields = ["sale_number", "fbr_invoice_number"]

@admin.register(SaleLine)
class SaleLineAdmin(admin.ModelAdmin):
    list_display = ["sale", "product_name", "quantity", 
                    "unit_price", "sales_tax_applicable", "line_total"]

@admin.register(SalePayment)
class SalePaymentAdmin(admin.ModelAdmin):
    list_display = ["sale", "payment_method", "amount", "created_at"]
    list_filter  = ["payment_method"]