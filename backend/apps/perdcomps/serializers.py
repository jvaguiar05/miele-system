from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import LossCompensation


class LossCompensationSerializer(serializers.ModelSerializer):
    """Serializer completo para LossCompensation."""
    
    compensation_percentage = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    
    @extend_schema_field(serializers.FloatField)
    def get_compensation_percentage(self, obj):
        """Calcular percentual de compensação."""
        return obj.compensation_percentage
    
    @extend_schema_field(serializers.BooleanField) 
    def get_is_overdue(self, obj):
        """Verificar se está em atraso."""
        return obj.is_overdue
    
    class Meta:
        model = LossCompensation
        fields = [
            'id', 'client', 'created_by', 'reference_number', 'loss_amount',
            'compensation_amount', 'loss_status', 'loss_type', 'description',
            'internal_notes', 'loss_date', 'approval_deadline', 'is_active',
            'created_at', 'updated_at', 'compensation_percentage', 'is_overdue'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class LossCompensationAnnotationSerializer(serializers.ModelSerializer):
    """Serializer apenas para campos não sensíveis."""
    
    class Meta:
        model = LossCompensation
        fields = ['description', 'internal_notes']


class LossCompensationSensitiveSerializer(serializers.ModelSerializer):
    """Serializer para campos sensíveis (requer aprovação)."""
    
    class Meta:
        model = LossCompensation
        fields = [
            'reference_number', 'loss_amount', 'compensation_amount',
            'loss_status', 'loss_type', 'loss_date', 'approval_deadline'
        ]
