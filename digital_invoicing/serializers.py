from rest_framework import serializers
from .models import ScenarioTestLog

class ScenarioTestLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScenarioTestLog
        fields = [
            "id",
            "company",
            "scenario_code",
            "status",
            "request_payload",
            "response_payload",
            "fbr_invoice_number",
            "error_message",
            "created_at",
        ]
