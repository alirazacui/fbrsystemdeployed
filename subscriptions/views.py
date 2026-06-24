from django.shortcuts import render

# Create your views here.
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from django.db import transaction
from datetime import timedelta
from .models import *
from .serializers import *
from common.permissions import IsAdmin, IsActiveUser
 
 
class SubscriptionPlanViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    """
    Admin manages subscription plans.
 
    list     GET  /api/subscription-plans/
    create   POST /api/subscription-plans/
    retrieve GET  /api/subscription-plans/{id}/
    update   PUT  /api/subscription-plans/{id}/
    """
    queryset           = SubscriptionPlan.objects.all().order_by("price_per_month")
    serializer_class   = SubscriptionPlanSerializer
    permission_classes = [IsAdmin]
 
 
class CompanySubscriptionViewSet(GenericViewSet):
    """
    Admin manages company subscriptions.
 
    assign   POST /api/subscriptions/assign/
    extend   POST /api/subscriptions/{id}/extend/
    suspend  POST /api/subscriptions/{id}/suspend/
    reactivate POST /api/subscriptions/{id}/reactivate/
    list     GET  /api/subscriptions/
    status   GET  /api/subscriptions/my-status/  ← for company owner
    """
    permission_classes = [IsAdmin]
 
    def get_queryset(self):
        return CompanySubscription.objects.all().select_related(
            "company", "plan", "assigned_by"
        ).order_by("-created_at")
 
    @action(detail=False, methods=["post"], url_path="assign")
    def assign(self, request):
        """POST /api/subscriptions/assign/ — assign plan to company."""
        serializer = AssignPlanSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
 
        company = serializer.validated_data["company"]
        plan    = serializer.validated_data["plan"]
        notes   = serializer.validated_data.get("notes", "")
 
        with transaction.atomic():
            # Expire any existing active subscription
            CompanySubscription.objects.filter(
                company    = company,
                status__in = [
                    CompanySubscription.Status.ACTIVE,
                    CompanySubscription.Status.TRIAL,
                ],
            ).update(status=CompanySubscription.Status.EXPIRED)
 
            # Create new subscription
            start_date  = timezone.now().date()
            expiry_date = start_date + timedelta(days=plan.duration_days)
 
            sub_status = (
                CompanySubscription.Status.TRIAL
                if plan.is_trial
                else CompanySubscription.Status.ACTIVE
            )
 
            subscription = CompanySubscription.objects.create(
                company     = company,
                plan        = plan,
                status      = sub_status,
                start_date  = start_date,
                expiry_date = expiry_date,
                assigned_by = request.user,
                notes       = notes,
            )
 
            # Update company subscription fields
            company.subscription_plan   = plan.name.lower()
            company.subscription_status = sub_status
            company.subscription_start_date  = start_date
            company.subscription_expiry_date = expiry_date
            company.save(update_fields=[
                "subscription_plan",
                "subscription_status",
                "subscription_start_date",
                "subscription_expiry_date",
                "updated_at",
            ])
 
            # Log history
            SubscriptionHistory.objects.create(
                company      = company,
                plan         = plan,
                action       = SubscriptionHistory.Action.CREATED,
                performed_by = request.user,
                notes        = notes,
            )
 
        return Response(
            CompanySubscriptionSerializer(subscription).data,
            status=status.HTTP_201_CREATED,
        )
 
    @action(detail=True, methods=["post"], url_path="extend")
    def extend(self, request, pk=None):
        """POST /api/subscriptions/{id}/extend/"""
        subscription = CompanySubscription.objects.get(pk=pk)
        serializer   = ExtendSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
 
        subscription.extend(
            days         = serializer.validated_data["days"],
            notes        = serializer.validated_data.get("notes", ""),
            extended_by  = request.user,
        )
 
        # Sync company expiry date
        subscription.company.subscription_expiry_date = subscription.expiry_date
        subscription.company.save(update_fields=["subscription_expiry_date", "updated_at"])
 
        return Response(CompanySubscriptionSerializer(subscription).data)
 
    @action(detail=True, methods=["post"], url_path="suspend")
    def suspend(self, request, pk=None):
        """POST /api/subscriptions/{id}/suspend/"""
        subscription        = CompanySubscription.objects.get(pk=pk)
        subscription.status = CompanySubscription.Status.SUSPENDED
        subscription.save(update_fields=["status", "updated_at"])
 
        subscription.company.subscription_status = "suspended"
        subscription.company.save(update_fields=["subscription_status", "updated_at"])
 
        SubscriptionHistory.objects.create(
            company      = subscription.company,
            plan         = subscription.plan,
            action       = SubscriptionHistory.Action.SUSPENDED,
            performed_by = request.user,
            notes        = request.data.get("notes", ""),
        )
        return Response(CompanySubscriptionSerializer(subscription).data)
 
    @action(detail=True, methods=["post"], url_path="reactivate")
    def reactivate(self, request, pk=None):
        """POST /api/subscriptions/{id}/reactivate/"""
        subscription = CompanySubscription.objects.get(pk=pk)
 
        if subscription.expiry_date < timezone.now().date():
            return Response(
                {"error": "Cannot reactivate an expired subscription. Extend it first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        subscription.status = CompanySubscription.Status.ACTIVE
        subscription.save(update_fields=["status", "updated_at"])
 
        subscription.company.subscription_status = "active"
        subscription.company.save(update_fields=["subscription_status", "updated_at"])
 
        SubscriptionHistory.objects.create(
            company      = subscription.company,
            plan         = subscription.plan,
            action       = SubscriptionHistory.Action.REACTIVATED,
            performed_by = request.user,
        )
        return Response(CompanySubscriptionSerializer(subscription).data)
 
    @action(detail=False, methods=["get"], url_path="list")
    def list_subscriptions(self, request):
        """GET /api/subscriptions/list/"""
        qs         = self.get_queryset()
        page       = self.paginate_queryset(qs)
        serializer = CompanySubscriptionSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
 
    @action(
        detail=False, methods=["get"],
        url_path="my-status",
        permission_classes=[IsActiveUser],
    )
    def my_status(self, request):
        """
        GET /api/subscriptions/my-status/
        Company owner checks their own subscription status and limits.
        """
        try:
            sub = CompanySubscription.objects.select_related("plan").get(
                company    = request.user.company,
                status__in = [
                    CompanySubscription.Status.ACTIVE,
                    CompanySubscription.Status.TRIAL,
                    CompanySubscription.Status.EXPIRED,
                ],
            )
        except CompanySubscription.DoesNotExist:
            return Response(
                {"error": "No subscription found for your company."},
                status=status.HTTP_404_NOT_FOUND,
            )
 
        # Current usage counts
        company  = request.user.company
        from pos.models import Sale, SaleStatus
        from users.models import User
        now = timezone.now()
 
        return Response({
            "plan":            sub.plan.name,
            "status":          sub.status,
            "expiry_date":     str(sub.expiry_date),
            "days_remaining":  sub.days_remaining,
            "is_expiring_soon": sub.is_expiring_soon,
            "usage": {
                "products": {
                    "used":  company.products.filter(is_active=True).count(),
                    "limit": sub.plan.get_limit_display("max_products"),
                },
                "staff_users": {
                    "used":  User.objects.filter(
                        company=company,
                        role__in=["manager", "cashier", "salesperson"],
                    ).count(),
                    "limit": sub.plan.get_limit_display("max_users"),
                },
                "customers": {
                    "used":  company.customers.filter(
                        is_active=True, is_walk_in=False
                    ).count(),
                    "limit": sub.plan.get_limit_display("max_customers"),
                },
                "sales_this_month": {
                    "used":  Sale.objects.filter(
                        company      = company,
                        status       = SaleStatus.COMPLETED,
                        completed_at__year  = now.year,
                        completed_at__month = now.month,
                    ).count(),
                    "limit": sub.plan.get_limit_display("max_sales_per_month"),
                },
            },
        })
 
