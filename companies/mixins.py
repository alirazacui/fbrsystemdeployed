from companies.models import AuditLog

class AuditLogMixin:
    """
    Mixin for ViewSets to automatically generate AuditLog records.
    Hooks into perform_create, perform_update, and perform_destroy.
    """
    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')

    def log_audit_action(self, action, instance):
        request = self.request
        if not request.user or not request.user.is_authenticated:
            return
            
        company = getattr(request.user, "company", None)
        if not company:
            return
            
        AuditLog.objects.create(
            company=company,
            user_email=request.user.email,
            entity_type=instance._meta.model_name,
            entity_id=str(instance.pk),
            action=action,
            ip_address=self._get_client_ip(request)
        )

    def perform_create(self, serializer):
        super().perform_create(serializer)
        self.log_audit_action("create", serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self.log_audit_action("update", serializer.instance)

    def perform_destroy(self, instance):
        self.log_audit_action("delete", instance)
        super().perform_destroy(instance)
