

from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class CompanyLogoStorage(S3Boto3Storage):
    """
    Storage for company logos.
    Path: company_{company_id}/logo/{filename}
    Called from Company.logo ImageField via upload_to.
    """
    location = ""    # we control full path via upload_to

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("file_overwrite", True)   # overwrite old logo on update
        super().__init__(*args, **kwargs)


class UserProfileStorage(S3Boto3Storage):
    """
    Storage for user profile images.
    Path: company_{company_id}/users/user_{user_id}/profile/{filename}
    """
    location = ""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("file_overwrite", True)
        super().__init__(*args, **kwargs)


class ProductImageStorage(S3Boto3Storage):
    """
    Storage for product images.
    Path: products/company_{company_id}/product_{product_id}/{filename}
    """
    location = ""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("file_overwrite", False)  # keep old images
        super().__init__(*args, **kwargs)


class InvoicePDFStorage(S3Boto3Storage):
    """
    Storage for generated invoice PDFs.
    Path: company_{company_id}/invoices/{year}/{month}/{filename}
    Private — not publicly accessible.
    """
    location        = ""
    default_acl     = "private"
    file_overwrite  = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


# ---------------------------------------------------------------------------
# upload_to functions
# These are passed to model ImageField/FileField as upload_to=
# They receive the model instance and filename and return the S3 path
# ---------------------------------------------------------------------------

def company_logo_upload_path(instance, filename):
    """
    Company logo upload path.
    S3 path: company_{id}/logo/{filename}

    Usage in Company model:
        logo = models.ImageField(upload_to=company_logo_upload_path)
    """
    import os
    ext      = os.path.splitext(filename)[1].lower()
    new_name = f"logo{ext}"
    return f"company_{instance.pk}/logo/{new_name}"


def user_profile_upload_path(instance, filename):
    """
    User profile image upload path.
    S3 path: company_{company_id}/users/user_{user_id}/profile/{filename}
    Platform users (no company): platform_users/user_{user_id}/profile/{filename}

    Usage in User model:
        profile_image = models.ImageField(upload_to=user_profile_upload_path)
    """
    import os
    ext      = os.path.splitext(filename)[1].lower()
    new_name = f"profile{ext}"

    if instance.company_id:
        return f"company_{instance.company_id}/users/user_{instance.pk}/profile/{new_name}"
    return f"platform_users/user_{instance.pk}/profile/{new_name}"


def product_image_upload_path(instance, filename):
    """
    Product image upload path.
    S3 path: products/company_{company_id}/product_{product_id}/{filename}

    Usage in Product model:
        image = models.ImageField(upload_to=product_image_upload_path)
    """
    import os
    ext      = os.path.splitext(filename)[1].lower()
    new_name = f"image{ext}"
    return f"products/company_{instance.company_id}/product_{instance.pk}/{new_name}"


def invoice_pdf_upload_path(instance, filename):
    """
    Invoice PDF upload path.
    S3 path: company_{company_id}/invoices/{year}/{month}/{sale_number}.pdf

    Usage in Sale model (future pdf field):
        invoice_pdf = models.FileField(upload_to=invoice_pdf_upload_path)
    """
    from django.utils import timezone
    now   = timezone.now()
    year  = now.strftime("%Y")
    month = now.strftime("%m")
    return (
        f"company_{instance.company_id}/invoices/{year}/{month}/"
        f"{instance.sale_number}.pdf"
    )

def payment_qr_upload_path(instance, filename):
    """
    Payment QR upload path.
    S3 path: company_{company_id}/payment_qrs/{filename}
    """
    import os
    ext = os.path.splitext(filename)[1].lower()
    # instance is CompanyPaymentMethodSettings, so it has a company_id
    # We will use original filename but sanitize or just use uuid
    import uuid
    new_name = f"{uuid.uuid4().hex}{ext}"
    return f"company_{instance.company_id}/payment_qrs/{new_name}"


