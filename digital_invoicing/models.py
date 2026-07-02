from django.db import models
from django.utils.translation import gettext_lazy as _

class ScenarioTestLog(models.Model):
    """
    Logs every attempt to run an FBR sandbox scenario.
    Provides history and the exact JSON payload for frontend inspection and editing.
    """
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SUCCESS = "success", _("Success")
        FAILED  = "failed",  _("Failed")

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="scenario_logs",
    )
    scenario_code = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    request_payload = models.JSONField(blank=True, null=True)
    response_payload = models.JSONField(blank=True, null=True)
    fbr_invoice_number = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Scenario Test Log")
        verbose_name_plural = _("Scenario Test Logs")

    def __str__(self):
        return f"{self.company.business_name} - {self.scenario_code} - {self.status}"

class FBRSubmissionLog(models.Model):
    """
    Persistently logs every PRAL API roundtrip for both Sandbox and Production.
    Used for FBR Submissions report and compliance tracking.
    """
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="fbr_submissions",
    )
    sale = models.ForeignKey(
        "pos.Sale",
        on_delete=models.CASCADE,
        related_name="fbr_submissions",
        null=True,
        blank=True
    )
    environment = models.CharField(max_length=20, choices=[("sandbox", "Sandbox"), ("production", "Production")])
    endpoint = models.CharField(max_length=50)
    local_invoice_id = models.CharField(max_length=100, blank=True, null=True)
    fbr_invoice_id = models.CharField(max_length=100, blank=True, null=True)
    status_code = models.CharField(max_length=10, blank=True, null=True)
    http_status = models.IntegerField(null=True, blank=True)
    attempt = models.IntegerField(default=1)
    latency_ms = models.IntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    request_payload = models.JSONField(blank=True, null=True)
    response_payload = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("FBR Submission Log")
        verbose_name_plural = _("FBR Submission Logs")
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["local_invoice_id"]),
        ]

    def __str__(self):
        return f"[{self.environment}] {self.endpoint} - {self.local_invoice_id} ({self.status_code})"
