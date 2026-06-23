"""
========================================================
pos/views.py  — Product & Category section
========================================================
"""
 
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
 
from common.permissions import IsOwnerOrAdmin, IsClientUser, IsActiveUser
from .models import Category, Product
from pos.serializer import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductStockUpdateSerializer,
)
 
 
class CategoryViewSet(
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
 
 
class CashSessionViewSet(GenericViewSet):
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
 
 
class SaleViewSet(GenericViewSet):
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
 
        product  = serializer.validated_data["product"]
        quantity = serializer.validated_data["quantity"]
        discount = serializer.validated_data.get("discount_amount", 0)
 
        # If product already on sale, update quantity instead of adding duplicate
        existing = sale.lines.filter(product=product).first()
        if existing:
            existing.quantity        = float(existing.quantity) + float(quantity)
            existing.discount_amount = float(existing.discount_amount) + float(discount)
            existing.save()
        else:
            line = SaleLine.from_product(sale, product, quantity, float(discount))
            line.save()
 
        sale.compute_totals()
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
 
        with transaction.atomic():
            # Complete the sale
            sale.complete()
 
            # Decrement stock for all lines where track_inventory=True
            for line in sale.lines.select_related("product").all():
                product = line.product
                if product.track_inventory:
                    # Double-check stock hasn't changed since validation
                    product.refresh_from_db()
                    if float(product.current_stock) < float(line.quantity):
                        raise serializer.ValidationError(
                            f"Stock for '{product.name}' changed during "
                            f"transaction. Please retry."
                        )
                    product.current_stock = (
                        float(product.current_stock) - float(line.quantity)
                    )
                    product.save(update_fields=["current_stock", "updated_at"])
 
            # Mark FBR submission as pending
            # Actual submission happens in Phase 3 via Celery task
            if sale.company.module_fbr_di:
                sale.fbr_submission_status = FBRSubmissionStatus.PENDING
            else:
                sale.fbr_submission_status = FBRSubmissionStatus.SKIPPED
            sale.save(update_fields=["fbr_submission_status", "updated_at"])
 
        return Response(SaleDetailSerializer(sale).data)
 
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