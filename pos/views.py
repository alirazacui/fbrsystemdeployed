"""
========================================================
pos/views.py  — Product & Category section
========================================================
"""
 
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from companies.mixins import AuditLogMixin
 
from common.permissions import IsOwnerOrAdmin, IsClientUser, IsActiveUser
from .models import *
from pos.serializer import *

 
 
class CategoryViewSet(
    AuditLogMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    """
    Owner/Admin manages product categories.
    All queries scoped to requesting user's company.
 
    list     GET  /api/categories/
    create   POST /api/categories/
    retrieve GET  /api/categories/{id}/
    update   PUT  /api/categories/{id}/
    partial  PATCH /api/categories/{id}/
    """
    serializer_class   = CategorySerializer
    permission_classes = [IsOwnerOrAdmin]
 
    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            return Category.objects.all().select_related("company")
        return Category.objects.filter(
            company=user.company
        ).select_related("company")
 
 
class ProductViewSet(
    AuditLogMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    """
    Product management.
    Owner/Admin: full CRUD.
    Other client users: read-only list (for POS terminal search).
 
    list        GET  /api/products/
    create      POST /api/products/
    retrieve    GET  /api/products/{id}/
    update      PUT  /api/products/{id}/
    partial     PATCH /api/products/{id}/
    search      GET  /api/products/search/?q=term
    by_barcode  GET  /api/products/barcode/{barcode}/
    adjust_stock PATCH /api/products/{id}/stock/
    """
    permission_classes = [IsActiveUser]
 
    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            qs = Product.objects.all()
        else:
            qs = Product.objects.filter(
                company=user.company,
                is_active=True,
            )
        return qs.select_related("company", "category").order_by("name")
 
    def get_serializer_class(self):
        if self.action == "list" or self.action == "search":
            return ProductListSerializer
        if self.action == "adjust_stock":
            return ProductStockUpdateSerializer
        return ProductDetailSerializer
 
    def get_permissions(self):
        """
        create / update / adjust_stock → Owner or Admin only
        list / retrieve / search / by_barcode → any active client user
        """
        if self.action in ["create", "update", "partial_update", "adjust_stock"]:
            return [IsOwnerOrAdmin()]
        return [IsActiveUser()]
    def perform_create(self, serializer):
        """
        Called by CreateModelMixin.create() before saving.
        Check subscription product limit before allowing creation.
        """
        sub = getattr(self.request, "subscription", None)
        if sub:
            can_add, reason = sub.check_product_limit()
            if not can_add:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied(detail=reason)
        serializer.save()
 
    # ── Custom actions ─────────────────────────────────────────────────
 
    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        """
        GET /api/products/search/?q=term&category=id
 
        POS terminal product search. Returns lightweight list.
        Searches name, barcode, SKU.
        """
        query    = request.query_params.get("q", "").strip()
        category = request.query_params.get("category", "").strip()
 
        qs = self.get_queryset()
 
        if query:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=query)     |
                Q(barcode__icontains=query)  |
                Q(sku__icontains=query)
            )
 
        if category:
            qs = qs.filter(category_id=category)
 
        serializer = ProductListSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)
 
    @action(detail=False, methods=["get"], url_path=r"barcode/(?P<barcode>[^/.]+)")
    def by_barcode(self, request, barcode=None):
        """
        GET /api/products/barcode/{barcode}/
 
        Used by barcode scanner on POS terminal.
        Returns the single product matching this barcode.
        """
        try:
            product = self.get_queryset().get(barcode=barcode)
        except Product.DoesNotExist:
            return Response(
                {"detail": f"No product found with barcode '{barcode}'."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = ProductDetailSerializer(
            product, context={"request": request}
        )
        return Response(serializer.data)
 
    @action(detail=True, methods=["patch"], url_path="stock")
    def adjust_stock(self, request, pk=None):
        """
        PATCH /api/products/{id}/stock/
 
        Manual stock adjustment.
        Body: {"adjustment": 10, "reason": "Stock count correction"}
        Positive = stock in. Negative = stock out.
        """
        product    = self.get_object()
        serializer = ProductStockUpdateSerializer(
            product,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("update", product)
        return Response({
            "detail":        "Stock updated successfully.",
            "current_stock": product.current_stock,
        })


from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
 
from common.permissions import IsOwnerOrAdmin, IsActiveUser
from .models import Customer
from .serializer import CustomerDetailSerializer, CustomerListSerializer
 
 
class CustomerViewSet(
    AuditLogMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
    # No DestroyModelMixin — customers are never hard-deleted
    # Walk-in customer deletion is blocked at model level
):
    """
    Customer management.
    Owner/Admin: full CRUD.
    Cashier/Salesperson: read + search (to select customer at POS).
 
    list        GET  /api/customers/
    create      POST /api/customers/
    retrieve    GET  /api/customers/{id}/
    update      PUT  /api/customers/{id}/
    partial     PATCH /api/customers/{id}/
    search      GET  /api/customers/search/?q=term
    walkin      GET  /api/customers/walkin/
    deactivate  POST /api/customers/{id}/deactivate/
    activate    POST /api/customers/{id}/activate/
    """
    permission_classes = [IsActiveUser]
 
    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            return Customer.objects.all().select_related("company", "created_by")
        return Customer.objects.filter(
            company=user.company,
        ).select_related("company", "created_by").order_by("name")
 
    def get_serializer_class(self):
        if self.action in ["list", "search"]:
            return CustomerListSerializer
        return CustomerDetailSerializer
 
    def get_permissions(self):
        """
        create / update / activate / deactivate → Owner or Admin only
        list / retrieve / search / walkin       → any active client user
        """
        if self.action in ["create", "update", "partial_update",
                           "activate", "deactivate"]:
            return [IsOwnerOrAdmin()]
        return [IsActiveUser()]
    def perform_create(self, serializer):
        """Check subscription customer limit before creating customer."""
        sub = getattr(self.request, "subscription", None)
        if sub:
            can_add, reason = sub.check_customer_limit()
            if not can_add:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied(detail=reason)
        serializer.save()
 
    # ── Custom actions ─────────────────────────────────────────────────
 
    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        """
        GET /api/customers/search/?q=term
 
        POS terminal customer search.
        Searches name, NTN/CNIC, phone number.
        Returns active customers only.
        """
        query = request.query_params.get("q", "").strip()
 
        qs = self.get_queryset().filter(is_active=True)
 
        if query:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=query)     |
                Q(ntn_cnic__icontains=query) |
                Q(phone__icontains=query)
            )
 
        serializer = CustomerListSerializer(
            qs[:20],   # limit to 20 results for POS performance
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)
 
    @action(detail=False, methods=["get"], url_path="walkin")
    def walkin(self, request):
        """
        GET /api/customers/walkin/
 
        Returns this company's walk-in customer record.
        Used by POS terminal as default customer for cash sales.
        """
        try:
            customer = self.get_queryset().get(is_walk_in=True)
        except Customer.DoesNotExist:
            return Response(
                {"detail": "Walk-in customer record not found. Contact administrator."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CustomerDetailSerializer(
            customer, context={"request": request}
        )
        return Response(serializer.data)
 
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        """POST /api/customers/{id}/activate/"""
        customer           = self.get_object()
        customer.is_active = True
        customer.save(update_fields=["is_active", "updated_at"])
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("update", customer)
        return Response({"detail": f"Customer '{customer.name}' activated."})
 
    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        """POST /api/customers/{id}/deactivate/"""
        customer = self.get_object()
        if customer.is_walk_in:
            return Response(
                {"detail": "Walk-in customer cannot be deactivated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        customer.is_active = False
        customer.save(update_fields=["is_active", "updated_at"])
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("update", customer)
        return Response({"detail": f"Customer '{customer.name}' deactivated."})



from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from django.db import transaction
 
from common.permissions import IsOwnerOrAdmin, IsActiveUser, IsClientUser
from .models import (
    CashSession, Sale, SaleLine, SalePayment,
    SaleStatus, CashSessionStatus,
)
 
 
class CashSessionViewSet(AuditLogMixin, viewsets.ModelViewSet):
    """
    Cash session (shift) management.
 
    open    POST /api/cash-sessions/open/
    close   POST /api/cash-sessions/{id}/close/
    current GET  /api/cash-sessions/current/
    list    GET  /api/cash-sessions/
    """
    permission_classes = [IsClientUser]
 
    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            return CashSession.objects.all()
        return CashSession.objects.filter(
            company=user.company
        ).select_related("cashier", "company").order_by("-opened_at")
 
    @action(detail=False, methods=["post"], url_path="open")
    def open_session(self, request):
        """POST /api/cash-sessions/open/"""
        from .serializer import CashSessionOpenSerializer, CashSessionSerializer
        serializer = CashSessionOpenSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        session = serializer.save()
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("create", session)
        return Response(
            CashSessionSerializer(session).data,
            status=status.HTTP_201_CREATED,
        )
 
    @action(detail=True, methods=["post"], url_path="close")
    def close_session(self, request, pk=None):
        """POST /api/cash-sessions/{id}/close/"""
        from .serializer import CashSessionCloseSerializer, CashSessionSerializer
        session = self.get_object()
 
        if session.status == CashSessionStatus.CLOSED:
            return Response(
                {"detail": "This session is already closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if session.cashier != request.user and not request.user.is_platform_admin:
            return Response(
                {"detail": "You can only close your own cash session."},
                status=status.HTTP_403_FORBIDDEN,
            )
 
        serializer = CashSessionCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session.close(
            closing_balance=serializer.validated_data["closing_balance"],
            note=serializer.validated_data.get("closing_note", ""),
        )
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("update", session)
        return Response(CashSessionSerializer(session).data)
 
    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        """GET /api/cash-sessions/current/ — returns cashier's open session."""
        from .serializer import CashSessionSerializer
        try:
            session = CashSession.objects.get(
                company=request.user.company,
                cashier=request.user,
                status=CashSessionStatus.OPEN,
            )
        except CashSession.DoesNotExist:
            return Response(
                {"detail": "No open cash session found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(CashSessionSerializer(session).data)
 
    @action(detail=False, methods=["get"], url_path="")
    def list_sessions(self, request):
        """GET /api/cash-sessions/ — paginated list."""
        from .serializer import CashSessionSerializer
        qs         = self.get_queryset()
        page       = self.paginate_queryset(qs)
        serializer = CashSessionSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
 
 
class SaleViewSet(AuditLogMixin, viewsets.ModelViewSet):
    """
    Core POS transaction ViewSet.
 
    CREATE FLOW:
      1. POST /api/sales/                     → create DRAFT sale
      2. POST /api/sales/{id}/add-line/       → add product lines
      3. POST /api/sales/{id}/remove-line/    → remove a line
      4. POST /api/sales/{id}/add-payment/    → add payment(s)
      5. POST /api/sales/{id}/complete/       → complete sale
                                                (decrements stock, triggers FBR)
 
    OTHER:
      GET  /api/sales/                        → sale history list
      GET  /api/sales/{id}/                   → sale detail (receipt data)
      POST /api/sales/{id}/cancel/            → cancel a DRAFT sale
      GET  /api/sales/drafts/                 → all open drafts for this cashier
    """
    permission_classes = [IsClientUser]
 
    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            return Sale.objects.all()
        return Sale.objects.filter(
            company=user.company,
        ).select_related(
            "company", "cashier", "customer", "cash_session"
        ).prefetch_related("lines", "payments").order_by("-created_at")
 
    # ── 1. Create DRAFT sale ──────────────────────────────────────────
 
    @action(detail=False, methods=["post"], url_path="")
    def create_sale(self, request):
        """POST /api/sales/ — create a new DRAFT sale."""
        from .serializer import CreateSaleSerializer, SaleDetailSerializer
        serializer = CreateSaleSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        sale = serializer.save()
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("create", sale)
        return Response(
            SaleDetailSerializer(sale).data,
            status=status.HTTP_201_CREATED,
        )
 
    # ── 2. Add line ───────────────────────────────────────────────────
 
    @action(detail=True, methods=["post"], url_path="add-line")
    def add_line(self, request, pk=None):
        """POST /api/sales/{id}/add-line/"""
        from .serializer import AddSaleLineSerializer, SaleDetailSerializer
        sale       = self.get_object()
        serializer = AddSaleLineSerializer(
            data=request.data,
            context={"request": request, "sale": sale},
        )
        serializer.is_valid(raise_exception=True)
 
        product    = serializer.validated_data["product"]
        quantity   = serializer.validated_data["quantity"]
        discount   = serializer.validated_data.get("discount_amount", 0)
        unit_price = serializer.validated_data.get("unit_price")
 
        # If product already on sale, update quantity instead of adding duplicate
        existing = sale.lines.filter(product=product).first()
        if existing:
            existing.quantity        = float(existing.quantity) + float(quantity)
            existing.discount_amount = float(existing.discount_amount) + float(discount)
            if unit_price is not None:
                existing.unit_price = float(unit_price)
            existing.save()
        else:
            line = SaleLine.from_product(sale, product, quantity, float(discount), unit_price)
            line.save()
 
        sale.compute_totals()
        if sale.fbr_submission_status == "validated":
            sale.fbr_submission_status = "pending"
            sale.save(update_fields=["fbr_submission_status"])
        return Response(SaleDetailSerializer(sale).data)
 
    # ── 3. Remove line ────────────────────────────────────────────────
 
    @action(detail=True, methods=["post"], url_path="remove-line")
    def remove_line(self, request, pk=None):
        """POST /api/sales/{id}/remove-line/ — body: {"line_id": 5}"""
        from .serializer import SaleDetailSerializer
        sale    = self.get_object()
        line_id = request.data.get("line_id")
 
        if sale.status != SaleStatus.DRAFT:
            return Response(
                {"detail": "Cannot modify a completed sale."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        try:
            line = sale.lines.get(pk=line_id)
            line.delete()
        except SaleLine.DoesNotExist:
            return Response(
                {"detail": "Line not found on this sale."},
                status=status.HTTP_404_NOT_FOUND,
            )
 
        sale.compute_totals()
        return Response(SaleDetailSerializer(sale).data)
 
    # ── 4. Add payment ────────────────────────────────────────────────
 
    @action(detail=True, methods=["post"], url_path="add-payment")
    def add_payment(self, request, pk=None):
        """POST /api/sales/{id}/add-payment/"""
        from .serializer import AddSalePaymentSerializer, SaleDetailSerializer
        sale       = self.get_object()
        serializer = AddSalePaymentSerializer(
            data=request.data,
            context={"request": request, "sale": sale},
        )
        serializer.is_valid(raise_exception=True)
 
        SalePayment.objects.create(
            sale           = sale,
            payment_method = serializer.validated_data["payment_method"],
            amount         = serializer.validated_data["amount"],
            cheque_number  = serializer.validated_data.get("cheque_number", ""),
            cheque_bank    = serializer.validated_data.get("cheque_bank", ""),
            cheque_date    = serializer.validated_data.get("cheque_date"),
            bank_reference = serializer.validated_data.get("bank_reference", ""),
            bank_name      = serializer.validated_data.get("bank_name", ""),
            card_last_four = serializer.validated_data.get("card_last_four", ""),
            card_type      = serializer.validated_data.get("card_type", ""),
        )
 
        sale.refresh_from_db()
        return Response(SaleDetailSerializer(sale).data)
 
    # ── 5. Complete sale ──────────────────────────────────────────────
 
    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """
        POST /api/sales/{id}/complete/
 
        Validates → completes sale → decrements stock → triggers FBR submission.
        All wrapped in a DB transaction so nothing is partial on failure.
        """
        from .serializer import CompleteSaleSerializer, SaleDetailSerializer
        sale = self.get_object()
 
        # Validate
        serializer = CompleteSaleSerializer(
            data={}, context={"request": request, "sale": sale}
        )
        serializer.is_valid(raise_exception=True)
        sub = getattr(request, "subscription", None)
        if sub:
            can_add, reason = sub.check_sales_limit()
            if not can_add:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied(detail=reason)
 
        with transaction.atomic():
            # Complete the sale
            sale.complete()

            # Mark FBR submission as pending
            # Actual submission happens in Phase 3 via Celery task
            if sale.company.module_fbr_di:
                sale.fbr_submission_status = FBRSubmissionStatus.PENDING
                from digital_invoicing.tasks import submit_invoice_to_fbr
                submit_invoice_to_fbr.delay(sale.id)
            else:
                sale.fbr_submission_status = FBRSubmissionStatus.SKIPPED
            sale.save(update_fields=["fbr_submission_status", "updated_at"])
 
        return Response(SaleDetailSerializer(sale).data)
 
    # ── Validate invoice with FBR ─────────────────────────────────────
    
    @action(detail=True, methods=["post"], url_path="validate_fbr")
    def validate_fbr(self, request, pk=None):
        """POST /api/pos/sales/{id}/validate_fbr/"""
        sale = self.get_object()
        company = sale.company
        
        if not company.module_fbr_di:
            return Response({"detail": "FBR DI module is not enabled for this company."}, status=400)
            
        is_sandbox = True
        if company.fbr_sandbox_complete and company.fbr_production_token:
            is_sandbox = False
            token = company.fbr_production_token
        elif company.fbr_sandbox_token:
            is_sandbox = True
            token = company.fbr_sandbox_token
        else:
            return Response({"detail": "FBR token is not configured. Please set a Sandbox or Production token."}, status=400)
            
        from digital_invoicing.invoice_builder import FBRInvoiceBuilder
        from digital_invoicing.fbr_client import FBRClient, FBRAPIError
        
        builder = FBRInvoiceBuilder(sale)
        try:
            payload = builder.build()
            
            # Print to terminal
            print("\n" + "="*50)
            print(f"FBR VALIDATION TRIGGERED ({'SANDBOX' if is_sandbox else 'PRODUCTION'})")
            print(f"Token: {token}")
            import json
            print(f"Payload: {json.dumps(payload, indent=2)}")
            print("="*50 + "\n")
            
        except Exception as e:
            return Response({"detail": f"Failed to build invoice payload: {str(e)}"}, status=400)
            
        base_url = company.fbr_sandbox_endpoint if is_sandbox else company.fbr_production_endpoint
        client = FBRClient(token=token, base_url=base_url, is_sandbox=is_sandbox)
        try:
            start_time = __import__('time').time()
            res = client.validate_invoice(payload)
            latency_ms = int((__import__('time').time() - start_time) * 1000)
            
            sale.fbr_submission_status = "validated"
            sale.save(update_fields=["fbr_submission_status"])

            from digital_invoicing.models import FBRSubmissionLog
            FBRSubmissionLog.objects.create(
                company=company,
                sale=sale,
                environment="sandbox" if is_sandbox else "production",
                endpoint="validateinvoicedata_sb" if is_sandbox else "validateinvoicedata",
                local_invoice_id=sale.sale_number,
                fbr_invoice_id="",
                status_code="00",
                http_status=200,
                attempt=1,
                latency_ms=latency_ms,
                error_message=""
            )

            if hasattr(self, 'log_audit_action'):
                self.log_audit_action("validate_fbr", sale)

            return Response({"detail": "Invoice validated successfully with FBR.", "fbr_response": res})
        except FBRAPIError as e:
            latency_ms = int((__import__('time').time() - start_time) * 1000)
            from digital_invoicing.models import FBRSubmissionLog
            FBRSubmissionLog.objects.create(
                company=company,
                sale=sale,
                environment="sandbox" if is_sandbox else "production",
                endpoint="validateinvoicedata_sb" if is_sandbox else "validateinvoicedata",
                local_invoice_id=sale.sale_number,
                fbr_invoice_id="",
                status_code=e.error_code,
                http_status=200,
                attempt=1,
                latency_ms=latency_ms,
                error_message=e.message
            )
            return Response({"detail": str(e), "error_code": getattr(e, 'error_code', 'UNKNOWN')}, status=400)
        except Exception as e:
            latency_ms = int((__import__('time').time() - start_time) * 1000)
            from digital_invoicing.models import FBRSubmissionLog
            FBRSubmissionLog.objects.create(
                company=company,
                sale=sale,
                environment="sandbox" if is_sandbox else "production",
                endpoint="validateinvoicedata_sb" if is_sandbox else "validateinvoicedata",
                local_invoice_id=sale.sale_number,
                fbr_invoice_id="",
                status_code="ERROR",
                http_status=500,
                attempt=1,
                latency_ms=latency_ms,
                error_message=str(e)
            )
            return Response({"detail": f"FBR validation failed: {str(e)}"}, status=400)

    @action(detail=True, methods=["post"], url_path="log_download")
    def log_download(self, request, pk=None):
        sale = self.get_object()
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("download", sale)
        return Response({"detail": "Download logged successfully."})

    # ── Cancel sale ───────────────────────────────────────────────────
 
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """POST /api/sales/{id}/cancel/ — only DRAFT sales can be cancelled."""
        from .serializer import SaleDetailSerializer
        sale = self.get_object()
 
        if sale.status != SaleStatus.DRAFT:
            return Response(
                {"detail": f"Only DRAFT sales can be cancelled. "
                           f"This sale is {sale.get_status_display()}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        sale.status = SaleStatus.CANCELLED
        sale.save(update_fields=["status", "updated_at"])
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("update", sale) # explicitly log cancellation
        return Response(SaleDetailSerializer(sale).data)
 
    # ── List & retrieve ───────────────────────────────────────────────
 
    @action(detail=False, methods=["get"], url_path="list")
    def list_sales(self, request):
        """GET /api/sales/list/ — paginated sale history."""
        from .serializer import SaleListSerializer
        # Optional filters
        status_filter = request.query_params.get("status")
        qs = self.get_queryset()
        if status_filter:
            qs = qs.filter(status=status_filter)
 
        page       = self.paginate_queryset(qs)
        serializer = SaleListSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
 
    @action(detail=True, methods=["get"], url_path="detail")
    def retrieve_sale(self, request, pk=None):
        """GET /api/sales/{id}/detail/ — full receipt data."""
        from .serializer import SaleDetailSerializer
        sale = self.get_object()
        return Response(SaleDetailSerializer(sale).data)
 
    @action(detail=False, methods=["get"], url_path="drafts")
    def drafts(self, request):
        """GET /api/sales/drafts/ — all open DRAFT sales for this cashier."""
        from .serializer import SaleListSerializer
        qs = self.get_queryset().filter(
            cashier=request.user,
            status=SaleStatus.DRAFT,
        )
        serializer = SaleListSerializer(qs, many=True)
        return Response(serializer.data)
    

 
class SaleReturnViewSet(AuditLogMixin, viewsets.ModelViewSet):
    """
    Returns & Refunds management.
 
    create  POST /api/returns/
    retrieve GET  /api/returns/{id}/
    list    GET  /api/returns/
    confirm_refund POST /api/returns/{id}/confirm-refund/
    """
    permission_classes = [IsClientUser]
 
    def get_queryset(self):
        from pos.models import SaleReturn
        user = self.request.user
        if user.is_platform_admin:
            return SaleReturn.objects.all()
        return SaleReturn.objects.filter(
            company=user.company
        ).select_related(
            "original_sale", "credit_note_sale",
            "processed_by", "company"
        ).prefetch_related("lines").order_by("-created_at")
 
    @action(detail=False, methods=["post"], url_path="")
    def create_return(self, request):
        """
        POST /api/returns/
 
        Creates a return against a completed sale.
        Full flow in one atomic transaction:
        1. Validate input
        2. Create SaleReturn + SaleReturnLines
        3. Restore stock for returned items
        4. Create Credit Note Sale
        5. Trigger FBR credit note submission
        """
        from pos.models import (
            SaleReturn, SaleReturnLine,
            ReturnStatus, ReturnReason,
        )
        from pos.serializer import (
            CreateReturnSerializer, SaleReturnSerializer
        )
        from pos.models import Sale, SaleStatus, SaleType, FBRSubmissionStatus
 
        serializer = CreateReturnSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
 
        original_sale = serializer.context["original_sale"]
        lines_data    = serializer.validated_data["lines"]
        reason        = serializer.validated_data["reason"]
        reason_notes  = serializer.validated_data.get("reason_notes", "")
 
        # Determine full vs partial
        all_lines    = original_sale.lines.all()
        return_type  = "partial"
 
        # Check if all lines are being fully returned
        all_fully_returned = all(
            any(
                ld["original_line_id"] == ol.pk and
                float(ld["quantity_returned"]) >= float(ol.quantity)
                for ld in lines_data
            )
            for ol in all_lines
        )
        if all_fully_returned and len(lines_data) == all_lines.count():
            return_type = "full"
 
        with transaction.atomic():
            # ── Create SaleReturn ─────────────────────────────────────
            sale_return = SaleReturn(
                company       = request.user.company,
                original_sale = original_sale,
                processed_by  = request.user,
                return_type   = return_type,
                reason        = reason,
                reason_notes  = reason_notes,
                status        = ReturnStatus.PENDING,
            )
            sale_return.check_fbr_eligibility()
            sale_return.save()
 
            # ── Create SaleReturnLines + restore stock ─────────────────
            total_return_amount = 0
            total_return_tax    = 0
 
            for line_data in lines_data:
                original_line = line_data["original_line_obj"]
                qty_returned  = line_data["quantity_returned"]
 
                return_line = SaleReturnLine(
                    sale_return       = sale_return,
                    original_line     = original_line,
                    product_name      = original_line.product_name,
                    quantity_returned = qty_returned,
                    unit_price        = original_line.unit_price,
                    tax_rate_percent  = original_line.tax_rate_percent,
                )
                return_line.save()
 
                total_return_amount += float(return_line.return_line_total)
                total_return_tax    += float(return_line.return_tax)
 
                # Restore stock if product tracks inventory
                product = original_line.product
                if product.track_inventory:
                    product.refresh_from_db()
                    product.current_stock = (
                        float(product.current_stock) + float(qty_returned)
                    )
                    product.save(update_fields=["current_stock", "updated_at"])
                    return_line.stock_restored = True
                    return_line.save(update_fields=["stock_restored"])
 
            # ── Update SaleReturn totals ───────────────────────────────
            sale_return.total_return_amount = round(total_return_amount, 2)
            sale_return.total_return_tax    = round(total_return_tax, 2)
            sale_return.refund_amount       = round(total_return_amount, 2)
            sale_return.status              = ReturnStatus.COMPLETED
            sale_return.completed_at        = timezone.now()
            sale_return.save()
 
            # ── Mark original sale as returned ────────────────────────
            if return_type == "full":
                original_sale.status = SaleStatus.RETURNED
                original_sale.save(update_fields=["status", "updated_at"])
 
            # ── Create Credit Note Sale ───────────────────────────────
            credit_note = Sale(
                company       = request.user.company,
                cashier       = request.user,
                customer      = original_sale.customer,
                sale_type     = SaleType.CREDIT_NOTE,
                status        = SaleStatus.COMPLETED,
                original_sale = original_sale,
                subtotal      = sale_return.total_return_amount - sale_return.total_return_tax,
                total_tax     = sale_return.total_return_tax,
                total_amount  = sale_return.total_return_amount,
                amount_paid   = sale_return.total_return_amount,
                notes         = (
                    f"Credit Note for return {sale_return.return_number}. "
                    f"Reason: {sale_return.get_reason_display()}"
                ),
                completed_at  = timezone.now(),
            )
            credit_note.save()
 
            # ── Create credit note lines (negative quantities) ─────────
            from pos.models import SaleLine
            for return_line in sale_return.lines.all():
                orig = return_line.original_line
                SaleLine.objects.create(
                    sale               = credit_note,
                    product            = orig.product,
                    product_name       = return_line.product_name,
                    hs_code            = orig.hs_code,
                    unit_of_measure    = orig.unit_of_measure,
                    fbr_sale_type      = orig.fbr_sale_type,
                    tax_rate_percent   = orig.tax_rate_percent,
                    quantity           = return_line.quantity_returned,
                    unit_price         = return_line.unit_price,
                    discount_amount    = 0,
                    sales_tax_withheld = orig.sales_tax_withheld,
                    further_tax        = orig.further_tax,
                    extra_tax          = orig.extra_tax,
                    fed_payable        = orig.fed_payable,
                    fixed_retail_price = orig.fixed_retail_price,
                    sro_schedule_no    = orig.sro_schedule_no,
                    sro_item_serial_no = orig.sro_item_serial_no,
                    value_excl_tax     = return_line.return_value_excl_tax,
                    sales_tax_applicable = return_line.return_tax,
                    line_total         = return_line.return_line_total,
                )
 
            # ── Link credit note to return ─────────────────────────────
            sale_return.credit_note_sale = credit_note
            sale_return.save(update_fields=["credit_note_sale"])
 
            # ── Trigger FBR credit note submission ────────────────────
            if sale_return.fbr_eligible and request.user.company.module_fbr_di:
                credit_note.fbr_submission_status = FBRSubmissionStatus.PENDING
                credit_note.save(update_fields=["fbr_submission_status"])
                from digital_invoicing.tasks import submit_invoice_to_fbr
                submit_invoice_to_fbr.delay(credit_note.pk)
            else:
                credit_note.fbr_submission_status = FBRSubmissionStatus.SKIPPED
                credit_note.save(update_fields=["fbr_submission_status"])
 
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("create", sale_return)
        return Response(
            SaleReturnSerializer(sale_return).data,
            status=status.HTTP_201_CREATED,
        )
 
    @action(detail=True, methods=["post"], url_path="confirm-refund")
    def confirm_refund(self, request, pk=None):
        """
        POST /api/returns/{id}/confirm-refund/
 
        Marks the cash refund as physically paid to customer.
        Called after cashier hands cash back to customer.
        """
        from pos.models import SaleReturn
        from pos.serializer import SaleReturnSerializer
 
        sale_return = self.get_object()
 
        if sale_return.refund_paid:
            return Response(
                {"detail": "Refund has already been marked as paid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        sale_return.refund_paid    = True
        sale_return.refund_paid_at = timezone.now()
        sale_return.save(update_fields=["refund_paid", "refund_paid_at", "updated_at"])
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("update", sale_return)

        return Response(SaleReturnSerializer(sale_return).data)
 
    @action(detail=False, methods=["get"], url_path="list")
    def list_returns(self, request):
        """GET /api/returns/list/"""
        from pos.serializer import SaleReturnSerializer
        qs         = self.get_queryset()
        page       = self.paginate_queryset(qs)
        serializer = SaleReturnSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
 
    @action(detail=True, methods=["get"], url_path="detail")
    def retrieve_return(self, request, pk=None):
        """GET /api/returns/{id}/detail/"""
        from pos.serializer import SaleReturnSerializer
        return Response(SaleReturnSerializer(self.get_object()).data)
 
 
class DebitNoteViewSet(AuditLogMixin, viewsets.ModelViewSet):
    """
    Debit Notes management.
 
    create   POST /api/debit-notes/
    list     GET  /api/debit-notes/
    retrieve GET  /api/debit-notes/{id}/
    cancel   POST /api/debit-notes/{id}/cancel/
    """
    permission_classes = [IsClientUser]
 
    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            return DebitNote.objects.all()
        return DebitNote.objects.filter(
            company=user.company
        ).select_related(
            "original_sale", "debit_note_sale",
            "processed_by", "company"
        ).prefetch_related("lines").order_by("-created_at")
 
    @action(detail=False, methods=["post"], url_path="")
    def create_debit_note(self, request):
        """
        POST /api/debit-notes/
 
        Complete flow in one atomic transaction:
        1. Validate input + original sale
        2. Check FBR 72-hour eligibility
        3. Create DebitNote + DebitNoteLines
        4. Collect payment
        5. Create Debit Note Sale
        6. Trigger FBR submission
        """
        from pos.models import (
            Sale, SaleStatus, SaleType,
            SaleLine, SalePayment, FBRSubmissionStatus,
            PaymentMethod,
        )
 
        serializer = CreateDebitNoteSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
 
        original_sale  = serializer.context["original_sale"]
        lines_data     = serializer.validated_data["lines"]
        reason         = serializer.validated_data["reason"]
        reason_notes   = serializer.validated_data.get("reason_notes", "")
        payment_method = serializer.validated_data["payment_method"]
        amount_paid    = float(serializer.validated_data["amount_paid"])
 
        with transaction.atomic():
            # ── Create DebitNote ──────────────────────────────────────
            debit_note = DebitNote(
                company       = request.user.company,
                original_sale = original_sale,
                processed_by  = request.user,
                reason        = reason,
                reason_notes  = reason_notes,
                payment_method = payment_method,
                status        = DebitNoteStatus.DRAFT,
            )
            debit_note.check_fbr_eligibility()
            debit_note.save()
 
            # ── Create DebitNoteLines ─────────────────────────────────
            for line_data in lines_data:
                product_id       = line_data.get("product_id")
                original_line_id = line_data.get("original_line_id")
                description      = line_data.get("description", "")
 
                # Resolve product info
                product      = None
                original_ln  = None
                hs_code      = ""
                uom          = "Numbers, pieces, units"
                fbr_sale_type = line_data.get(
                    "fbr_sale_type", "Goods at standard rate (default)"
                )
                tax_rate = line_data.get("tax_rate_percent", "18%")
 
                if product_id:
                    from pos.models import Product
                    try:
                        product      = Product.objects.get(
                            pk      = product_id,
                            company = request.user.company,
                        )
                        description  = product.name
                        hs_code      = product.hs_code
                        uom          = product.unit_of_measure
                        fbr_sale_type = product.fbr_sale_type
                        tax_rate     = product.tax_rate_percent
                    except Product.DoesNotExist:
                        pass
 
                elif original_line_id:
                    try:
                        original_ln  = SaleLine.objects.get(
                            pk   = original_line_id,
                            sale = original_sale,
                        )
                        description   = (
                            f"Price correction: {original_ln.product_name}"
                        )
                        hs_code       = original_ln.hs_code
                        uom           = original_ln.unit_of_measure
                        fbr_sale_type = original_ln.fbr_sale_type
                        tax_rate      = original_ln.tax_rate_percent
                    except SaleLine.DoesNotExist:
                        pass
 
                DebitNoteLine.objects.create(
                    debit_note      = debit_note,
                    product         = product,
                    original_line   = original_ln,
                    description     = description,
                    hs_code         = hs_code,
                    unit_of_measure = uom,
                    fbr_sale_type   = fbr_sale_type,
                    tax_rate_percent = tax_rate,
                    quantity        = line_data["quantity"],
                    unit_price      = line_data["unit_price"],
                )
 
            # ── Compute totals ────────────────────────────────────────
            debit_note.compute_totals()
            total_amount = float(debit_note.total_amount)
 
            # ── Validate payment covers total ─────────────────────────
            if amount_paid < total_amount:
                raise serializers.ValidationError(
                    f"Amount paid (Rs. {amount_paid:.2f}) is less than "
                    f"total (Rs. {total_amount:.2f})."
                )
 
            change_given = round(amount_paid - total_amount, 2)
 
            # ── Mark payment collected ────────────────────────────────
            debit_note.amount_paid           = amount_paid
            debit_note.change_given          = change_given
            debit_note.payment_collected     = True
            debit_note.payment_collected_at  = timezone.now()
            debit_note.status                = DebitNoteStatus.COMPLETED
            debit_note.completed_at          = timezone.now()
            debit_note.save()
 
            # ── Create Debit Note Sale ────────────────────────────────
            dn_sale = Sale(
                company       = request.user.company,
                cashier       = request.user,
                customer      = original_sale.customer,
                sale_type     = SaleType.DEBIT_NOTE,
                status        = SaleStatus.COMPLETED,
                original_sale = original_sale,
                subtotal      = debit_note.total_amount - debit_note.total_tax,
                total_tax     = debit_note.total_tax,
                total_amount  = debit_note.total_amount,
                amount_paid   = amount_paid,
                change_given  = change_given,
                notes         = (
                    f"Debit Note {debit_note.debit_note_number}. "
                    f"Reason: {debit_note.get_reason_display()}. "
                    f"{reason_notes}"
                ),
                completed_at  = timezone.now(),
            )
            dn_sale.save()
 
            # ── Create sale lines on Debit Note Sale ──────────────────
            for dn_line in debit_note.lines.all():
                SaleLine.objects.create(
                    sale               = dn_sale,
                    product            = dn_line.product,
                    product_name       = dn_line.description,
                    hs_code            = dn_line.hs_code,
                    unit_of_measure    = dn_line.unit_of_measure,
                    fbr_sale_type      = dn_line.fbr_sale_type,
                    tax_rate_percent   = dn_line.tax_rate_percent,
                    quantity           = dn_line.quantity,
                    unit_price         = dn_line.unit_price,
                    discount_amount    = 0,
                    value_excl_tax     = dn_line.value_excl_tax,
                    sales_tax_applicable = dn_line.tax_amount,
                    line_total         = dn_line.line_total,
                )
 
            # ── Create payment record ─────────────────────────────────
            SalePayment.objects.create(
                sale           = dn_sale,
                payment_method = payment_method,
                amount         = debit_note.total_amount,
            )
 
            # ── Link debit note sale ──────────────────────────────────
            debit_note.debit_note_sale = dn_sale
            debit_note.save(update_fields=["debit_note_sale"])
 
            # ── Trigger FBR submission ────────────────────────────────
            if debit_note.fbr_eligible and request.user.company.module_fbr_di:
                dn_sale.fbr_submission_status = FBRSubmissionStatus.PENDING
                dn_sale.save(update_fields=["fbr_submission_status"])
                from digital_invoicing.tasks import submit_invoice_to_fbr
                submit_invoice_to_fbr.delay(dn_sale.pk)
            else:
                dn_sale.fbr_submission_status = FBRSubmissionStatus.SKIPPED
                dn_sale.save(update_fields=["fbr_submission_status"])
 
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("create", debit_note)
        return Response(
            DebitNoteSerializer(debit_note).data,
            status=status.HTTP_201_CREATED,
        )
 
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """
        POST /api/debit-notes/{id}/cancel/
        Only DRAFT debit notes can be cancelled.
        """
       
        dn = self.get_object()
 
        if dn.status != DebitNoteStatus.DRAFT:
            return Response(
                {"detail": "Only DRAFT debit notes can be cancelled."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        dn.status = DebitNoteStatus.CANCELLED
        dn.save(update_fields=["status", "updated_at"])
        if hasattr(self, 'log_audit_action'):
            self.log_audit_action("update", dn)
        return Response(DebitNoteSerializer(dn).data)
 
    @action(detail=False, methods=["get"], url_path="list")
    def list_debit_notes(self, request):
        """GET /api/debit-notes/list/"""
    
        qs         = self.get_queryset()
        page       = self.paginate_queryset(qs)
        serializer = DebitNoteSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
 
    @action(detail=True, methods=["get"], url_path="detail")
    def retrieve_debit_note(self, request, pk=None):
        """GET /api/debit-notes/{id}/detail/"""
        
        return Response(DebitNoteSerializer(self.get_object()).data)


from rest_framework import viewsets, filters, permissions
from rest_framework.pagination import PageNumberPagination
from companies.mixins import AuditLogMixin

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 1000

 
class HSCodeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = HSCode.objects.all()
    serializer_class = HSCodeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['code', 'description']
    pagination_class = StandardResultsSetPagination


from rest_framework.views import APIView
from django.db.models import Sum, F, Count
from datetime import timedelta

class DashboardStatsView(APIView):
    """
    Returns aggregate stats for the company dashboard.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        company = request.user.company
        if not company:
            return Response({"error": "User does not belong to a company"}, status=400)

        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        thirty_days_ago = now - timedelta(days=30)

        # Products
        products = Product.objects.filter(company=company)
        active_products = products.filter(is_active=True).count()
        
        # Stock Value
        stock_value = products.filter(track_inventory=True).aggregate(
            total_value=Sum(F('current_stock') * F('cost_price'))
        )['total_value'] or 0
        
        # Low Stock
        low_stock_products = products.filter(
            track_inventory=True,
            current_stock__lte=F('low_stock_threshold'),
            is_active=True
        ).values('id', 'name', 'current_stock', 'low_stock_threshold')[:5]

        # Customers
        total_customers = Customer.objects.filter(company=company).count()

        # Sales Base
        sales = Sale.objects.filter(company=company, status='completed')
        
        # Month Stats
        month_sales = sales.filter(completed_at__gte=start_of_month)
        invoices_this_month = month_sales.count()
        total_sales_this_month = month_sales.aggregate(t=Sum('total_amount'))['t'] or 0
        
        # Today Stats
        today_sales = sales.filter(completed_at__gte=start_of_today)
        sales_today = today_sales.aggregate(t=Sum('total_amount'))['t'] or 0
        
        # Average Invoice
        avg_invoice = (total_sales_this_month / invoices_this_month) if invoices_this_month > 0 else 0
        
        # FBR Stats
        sent_to_fbr = sales.filter(fbr_submission_status='SUCCESS').count()
        pending_validation = sales.filter(fbr_submission_status='PENDING').count()
        
        # Failed FBR
        failed_fbr = sales.filter(fbr_submission_status='FAILED').order_by('-completed_at').values(
            'id', 'sale_number', 'fbr_error_message', 'completed_at'
        )[:5]

        # Recent Invoices
        recent_invoices = sales.order_by('-completed_at').values(
            'id', 'sale_number', 'customer__name', 'total_amount', 'completed_at', 'fbr_submission_status'
        )[:5]
        
        # Sales Over Time Chart (Last 7 days)
        chart_data = []
        for i in range(7):
            d = now - timedelta(days=6-i)
            day_start = d.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            day_sales = sales.filter(completed_at__gte=day_start, completed_at__lt=day_end).aggregate(t=Sum('total_amount'))['t'] or 0
            chart_data.append({
                "date": day_start.strftime('%Y-%m-%d'),
                "total": float(day_sales)
            })

        return Response({
            "products": {
                "active": active_products,
            },
            "customers": {
                "total": total_customers,
            },
            "invoices": {
                "this_month_count": invoices_this_month,
                "this_month_total": float(total_sales_this_month),
            },
            "stock": {
                "value": float(stock_value),
            },
            "sales_today": float(sales_today),
            "avg_invoice": float(avg_invoice),
            "fbr": {
                "sent": sent_to_fbr,
                "pending": pending_validation,
            },
            "chart_data": chart_data,
            "recent_invoices": list(recent_invoices),
            "low_stock": list(low_stock_products),
            "failed_fbr": list(failed_fbr),
        })
