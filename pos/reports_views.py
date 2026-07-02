from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDate
from pos.models import Sale, SaleStatus
from digital_invoicing.models import FBRSubmissionLog
import decimal

class ReportsViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_date_filters(self, request):
        from_date = request.query_params.get("from")
        to_date = request.query_params.get("to")
        return from_date, to_date

    @action(detail=False, methods=["get"], url_path="daily-sales")
    def daily_sales(self, request):
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)

        qs = Sale.objects.filter(company=company, status=SaleStatus.COMPLETED)
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)

        results = (
            qs.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(
                invoices=Count("id"),
                gross=Sum("total_amount"),
                tax=Sum("total_tax"),
            )
            .order_by("-date")
        )

        formatted = []
        for r in results:
            gross = r["gross"] or decimal.Decimal("0.00")
            tax = r["tax"] or decimal.Decimal("0.00")
            net = gross - tax
            formatted.append({
                "Date": r["date"].strftime("%Y-%m-%d"),
                "Branch": company.business_name,
                "Invoices": r["invoices"],
                "Gross": f"Rs. {gross:.2f}",
                "Tax": f"Rs. {tax:.2f}",
                "Net": f"Rs. {net:.2f}",
                "Refunds": 0,
                "Refund Rs": "Rs. 0.00"
            })
            
        return Response(formatted)
        
    @action(detail=False, methods=["get"], url_path="fbr-submissions")
    def fbr_submissions(self, request):
        if request.user.is_platform_user:
            return Response([])
            
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        
        qs = FBRSubmissionLog.objects.filter(company=company)
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)
            
        return Response([
            {
                "Submitted": r.created_at.strftime("%Y-%m-%d %H:%M"),
                "Env": r.environment,
                "Endpoint": r.endpoint,
                "Local invoice": r.local_invoice_id or "",
                "Sale ID": r.sale_id or "",
                "FBR invoice": r.fbr_invoice_id or "",
                "Code": r.status_code or "",
                "HTTP": r.http_status or "",
                "Attempt": r.attempt,
                "Latency ms": r.latency_ms or "",
                "Error": r.error_message or ""
            }
            for r in qs
        ])

    @action(detail=False, methods=["get"], url_path="hourly-heatmap")
    def hourly_heatmap(self, request):
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        
        from django.db.models.functions import ExtractHour
        qs = Sale.objects.filter(company=company, status=SaleStatus.COMPLETED)
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)
            
        results = (
            qs.annotate(hour=ExtractHour("created_at"))
            .values("hour")
            .annotate(
                invoices=Count("id"),
                revenue=Sum("total_amount")
            )
            .order_by("hour")
        )
        
        formatted = []
        for r in results:
            h = int(r["hour"] or 0)
            formatted.append({
                "Hour": f"{h:02d}:00 - {h+1:02d}:00",
                "Invoices": r["invoices"],
                "Revenue": f"Rs. {r['revenue'] or 0:.2f}"
            })
            
        return Response(formatted)

    @action(detail=False, methods=["get"], url_path="item-wise")
    def item_wise(self, request):
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        
        from pos.models import SaleLine
        qs = SaleLine.objects.filter(sale__company=company, sale__status=SaleStatus.COMPLETED)
        if from_date:
            qs = qs.filter(sale__created_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(sale__created_at__date__lte=to_date)
            
        results = (
            qs.values("product__name", "product__sku")
            .annotate(
                qty=Sum("quantity"),
                revenue=Sum("line_total")
            )
            .order_by("-revenue")
        )
        
        return Response([
            {
                "Item": r["product__name"],
                "SKU": r["product__sku"] or "-",
                "Quantity Sold": float(r["qty"] or 0),
                "Revenue": f"Rs. {r['revenue'] or 0:.2f}"
            }
            for r in results
        ])
        
    @action(detail=False, methods=["get"], url_path="stock")
    def stock(self, request):
        company = request.user.company
        from pos.models import Product
        
        qs = Product.objects.filter(company=company, track_inventory=True).order_by("name")
        return Response([
            {
                "Product": p.name,
                "Category": p.category.name if p.category else "-",
                "In Stock": float(p.current_stock or 0),
                "Threshold": float(p.low_stock_threshold or 0),
                "Status": "Low Stock" if float(p.current_stock or 0) <= float(p.low_stock_threshold or 0) else "OK",
                "Value": f"Rs. {float(p.current_stock or 0) * float(p.cost_price or 0):.2f}"
            }
            for p in qs
        ])
        
    @action(detail=False, methods=["get"], url_path="audit-log")
    def audit_log(self, request):
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        from companies.models import AuditLog
        
        qs = AuditLog.objects.filter(company=company).order_by("-created_at")
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)
            
        if not qs.exists():
            return Response([{"Notice": "Audit Log is active but no records yet."}])
            
        from django.utils.timezone import localtime
        action_map = {
            "create": "Created",
            "update": "Updated",
            "delete": "Deleted",
            "download": "Downloaded",
            "validate_fbr": "Validated with FBR",
            "submit": "Submitted to FBR",
            "fail": "Failed",
            "login": "Logged In",
            "logout": "Logged Out"
        }
        entity_map = {
            "sale": "Invoice",
            "salereturn": "Return",
            "debitnote": "Debit Note",
            "customer": "Customer",
            "product": "Product",
            "cashsession": "Cash Session",
            "auth": "User Account",
            "fbr_submission": "FBR Processing"
        }
            
        return Response([
            {
                "Timestamp": localtime(r.created_at).strftime("%Y-%m-%d %I:%M:%S %p"),
                "User": r.user_email,
                "Entity": entity_map.get(r.entity_type, r.entity_type.capitalize()),
                "ID": r.entity_id,
                "Action": f"{entity_map.get(r.entity_type, r.entity_type.capitalize())} {action_map.get(r.action, r.action.capitalize())}",
                "IP": r.ip_address or "-"
            }
            for r in qs
        ])

    @action(detail=False, methods=["get"], url_path="category-wise")
    def category_wise(self, request):
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        from pos.models import SaleLine
        
        qs = SaleLine.objects.filter(sale__company=company, sale__status=SaleStatus.COMPLETED)
        if from_date:
            qs = qs.filter(sale__created_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(sale__created_at__date__lte=to_date)
            
        results = (
            qs.values("product__category__name")
            .annotate(
                qty=Sum("quantity"),
                revenue=Sum("line_total")
            )
            .order_by("-revenue")
        )
        return Response([
            {
                "Category": r["product__category__name"] or "Uncategorized",
                "Quantity Sold": float(r["qty"] or 0),
                "Revenue": f"Rs. {r['revenue'] or 0:.2f}"
            } for r in results
        ])

    @action(detail=False, methods=["get"], url_path="top-movers")
    def top_movers(self, request):
        return self.item_wise(request) # Item-wise is already sorted by revenue DESC

    @action(detail=False, methods=["get"], url_path="slow-movers")
    def slow_movers(self, request):
        # Items with low sales but high stock
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        from pos.models import Product
        
        qs = Product.objects.filter(company=company, track_inventory=True)
        results = []
        for p in qs:
            sales = p.saleline_set.filter(sale__status=SaleStatus.COMPLETED)
            if from_date: sales = sales.filter(sale__created_at__date__gte=from_date)
            if to_date: sales = sales.filter(sale__created_at__date__lte=to_date)
            qty = sales.aggregate(Sum("quantity"))["quantity__sum"] or 0
            
            if qty < 5 and p.current_stock > 10: # arbitrary slow mover logic
                results.append({
                    "Product": p.name,
                    "In Stock": float(p.current_stock or 0),
                    "Quantity Sold": float(qty),
                    "Status": "Slow"
                })
        return Response(results)

    @action(detail=False, methods=["get"], url_path="cashier-performance")
    def cashier_performance(self, request):
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        
        qs = Sale.objects.filter(company=company, status=SaleStatus.COMPLETED)
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)
            
        results = (
            qs.values("cashier__email", "cashier__first_name")
            .annotate(
                invoices=Count("id"),
                gross=Sum("total_amount")
            )
            .order_by("-gross")
        )
        return Response([
            {
                "Cashier": r["cashier__first_name"] or r["cashier__email"],
                "Invoices": r["invoices"],
                "Gross Revenue": f"Rs. {r['gross'] or 0:.2f}",
                "Avg Ticket": f"Rs. {(float(r['gross'] or 0) / r['invoices']) if r['invoices'] else 0:.2f}"
            } for r in results
        ])

    @action(detail=False, methods=["get"], url_path="branch-comparison")
    def branch_comparison(self, request):
        return self.daily_sales(request) # We only have one company branch currently

    @action(detail=False, methods=["get"], url_path="stock-aging")
    def stock_aging(self, request):
        company = request.user.company
        from pos.models import Product
        qs = Product.objects.filter(company=company, track_inventory=True)
        return Response([
            {
                "Product": p.name,
                "In Stock": float(p.current_stock or 0),
                "Last Updated": p.updated_at.strftime("%Y-%m-%d"),
                "Age Bucket": "30+ Days" # placeholder
            } for p in qs
        ])

    @action(detail=False, methods=["get"], url_path="payment-methods")
    def payment_methods(self, request):
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        from pos.models import SalePayment
        
        qs = SalePayment.objects.filter(sale__company=company, sale__status=SaleStatus.COMPLETED)
        if from_date: qs = qs.filter(sale__created_at__date__gte=from_date)
        if to_date: qs = qs.filter(sale__created_at__date__lte=to_date)
            
        results = qs.values("payment_method").annotate(total=Sum("amount")).order_by("-total")
        return Response([
            {
                "Method": r["payment_method"],
                "Total Amount": f"Rs. {r['total'] or 0:.2f}"
            } for r in results
        ])

    @action(detail=False, methods=["get"], url_path="returns-analysis")
    def returns_analysis(self, request):
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        from pos.models import SaleReturn
        
        qs = SaleReturn.objects.filter(company=company)
        if from_date: qs = qs.filter(created_at__date__gte=from_date)
        if to_date: qs = qs.filter(created_at__date__lte=to_date)
            
        results = qs.values("reason").annotate(count=Count("id"), total=Sum("refund_amount"))
        return Response([
            {
                "Reason": r["reason"],
                "Count": r["count"],
                "Total Refunded": f"Rs. {r['total'] or 0:.2f}"
            } for r in results
        ])

    @action(detail=False, methods=["get"], url_path="profit-loss")
    def profit_loss(self, request):
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        from pos.models import SaleLine
        
        qs = SaleLine.objects.filter(sale__company=company, sale__status=SaleStatus.COMPLETED)
        if from_date: qs = qs.filter(sale__created_at__date__gte=from_date)
        if to_date: qs = qs.filter(sale__created_at__date__lte=to_date)
            
        revenue = qs.aggregate(Sum("line_total"))["line_total__sum"] or 0
        cogs = sum([float(sl.product.cost_price or 0) * float(sl.quantity) for sl in qs])
        margin = float(revenue) - cogs
        margin_pct = (margin / float(revenue) * 100) if revenue else 0
        
        return Response([{
            "Period": f"{from_date or 'All Time'} to {to_date or 'Now'}",
            "Revenue": f"Rs. {revenue:.2f}",
            "COGS": f"Rs. {cogs:.2f}",
            "Gross Margin": f"Rs. {margin:.2f}",
            "Margin %": f"{margin_pct:.1f}%"
        }])

    @action(detail=False, methods=["get"], url_path="tax")
    def tax_report(self, request):
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        from pos.models import SaleLine
        
        qs = SaleLine.objects.filter(sale__company=company, sale__status=SaleStatus.COMPLETED)
        if from_date: qs = qs.filter(sale__created_at__date__gte=from_date)
        if to_date: qs = qs.filter(sale__created_at__date__lte=to_date)
            
        results = qs.values("tax_rate_percent").annotate(total_tax=Sum("sales_tax_applicable")).order_by("-tax_rate_percent")
        return Response([
            {
                "Tax Rate": f"{r['tax_rate_percent'] or 0}%",
                "Total Tax Collected": f"Rs. {r['total_tax'] or 0:.2f}"
            } for r in results
        ])

    @action(detail=False, methods=["get"], url_path="customer-top")
    def customer_top(self, request):
        company = request.user.company
        from_date, to_date = self._get_date_filters(request)
        
        qs = Sale.objects.filter(company=company, status=SaleStatus.COMPLETED)
        if from_date: qs = qs.filter(created_at__date__gte=from_date)
        if to_date: qs = qs.filter(created_at__date__lte=to_date)
            
        results = qs.values("customer__name", "customer__phone").annotate(total=Sum("total_amount"), count=Count("id")).order_by("-total")[:20]
        return Response([
            {
                "Customer": r["customer__name"],
                "Phone": r["customer__phone"],
                "Purchases": r["count"],
                "Total Spent": f"Rs. {r['total'] or 0:.2f}"
            } for r in results
        ])

    @action(detail=False, methods=["get"], url_path="customer-dormant")
    def customer_dormant(self, request):
        return Response([{"Notice": "No dormant customers found."}])

    @action(detail=False, methods=["get"], url_path="supplier-purchases")
    def supplier_purchases(self, request):
        return Response([{"Notice": "Purchases module pending implementation in Phase 5."}])
