from celery import shared_task
import logging
from .models import *
logger = logging.getLogger(__name__)
 
 
@shared_task(name="subscriptions.check_expiring_subscriptions")
def check_expiring_subscriptions():
    """
    Runs daily. Checks for:
    1. Subscriptions expiring in 7 days → send warning email
    2. Subscriptions that have expired → mark as expired + block
    """
    from django.utils import timezone
    from datetime import timedelta
 
    today      = timezone.now().date()
    warn_date  = today + timedelta(days=7)
 
    # ── Send 7-day warning emails ─────────────────────────────────────
    expiring_soon = CompanySubscription.objects.filter(
        status__in          = [
            CompanySubscription.Status.ACTIVE,
            CompanySubscription.Status.TRIAL,
        ],
        expiry_date         = warn_date,
        expiry_warning_sent = False,
    ).select_related("company", "plan")
 
    for sub in expiring_soon:
        try:
            _send_expiry_warning_email(sub)
            sub.expiry_warning_sent    = True
            sub.expiry_warning_sent_at = timezone.now()
            sub.save(update_fields=[
                "expiry_warning_sent",
                "expiry_warning_sent_at",
                "updated_at",
            ])
            logger.info(
                f"[Subscriptions] Warning email sent for "
                f"{sub.company.business_name}"
            )
        except Exception as e:
            logger.error(
                f"[Subscriptions] Failed to send warning email "
                f"for {sub.company.business_name}: {e}"
            )
 
    # ── Expire overdue subscriptions ──────────────────────────────────
    expired = CompanySubscription.objects.filter(
        status__in  = [
            CompanySubscription.Status.ACTIVE,
            CompanySubscription.Status.TRIAL,
        ],
        expiry_date__lt = today,
    ).select_related("company", "plan")
 
    for sub in expired:
        try:
            sub.expire()
            _send_expiry_notification_email(sub)
            logger.info(
                f"[Subscriptions] Expired: {sub.company.business_name}"
            )
        except Exception as e:
            logger.error(
                f"[Subscriptions] Failed to expire "
                f"{sub.company.business_name}: {e}"
            )
 
    logger.info(
        f"[Subscriptions] Daily check complete. "
        f"Warnings sent: {expiring_soon.count()}, "
        f"Expired: {expired.count()}"
    )
 
 
def _send_expiry_warning_email(subscription):
    """Sends 7-day expiry warning to company owner."""
    from django.core.mail import send_mail
    from django.conf import settings
 
    owner = subscription.company.owner
    if not owner:
        return
 
    send_mail(
        subject=(
            f"[POS Platform] Your subscription expires in 7 days — "
            f"{subscription.company.business_name}"
        ),
        message=(
            f"Dear {owner.get_full_name() or owner.email},\n\n"
            f"Your {subscription.plan.name} subscription for "
            f"{subscription.company.business_name} will expire on "
            f"{subscription.expiry_date}.\n\n"
            f"After expiry, your POS access will be blocked.\n\n"
            f"Please contact your administrator to renew your subscription.\n\n"
            f"Days remaining: {subscription.days_remaining}\n\n"
            f"Thank you,\nPOS Platform Team"
        ),
        from_email = settings.DEFAULT_FROM_EMAIL,
        recipient_list = [owner.email],
        fail_silently  = False,
    )
 
 
def _send_expiry_notification_email(subscription):
    """Sends expiry notification to company owner."""
    from django.core.mail import send_mail
    from django.conf import settings
 
    owner = subscription.company.owner
    if not owner:
        return
 
    send_mail(
        subject=(
            f"[POS Platform] Your subscription has expired — "
            f"{subscription.company.business_name}"
        ),
        message=(
            f"Dear {owner.get_full_name() or owner.email},\n\n"
            f"Your {subscription.plan.name} subscription for "
            f"{subscription.company.business_name} expired on "
            f"{subscription.expiry_date}.\n\n"
            f"Your POS access has been blocked.\n\n"
            f"Please contact your administrator to renew your subscription.\n\n"
            f"Thank you,\nPOS Platform Team"
        ),
        from_email     = settings.DEFAULT_FROM_EMAIL,
        recipient_list = [owner.email],
        fail_silently  = False,
    )
