from rest_framework import serializers
from .models import Client


class ClientSerializer(serializers.ModelSerializer):
    """Serializer completo para Client."""
    
    class Meta:
        model = Client
        fields = [
            'id', 'cnpj', 'razao_social', 'nome_fantasia', 'email',
            'telefone', 'client_status', 'annotations', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ClientAnnotationSerializer(serializers.ModelSerializer):
    """Serializer apenas para campos não sensíveis (anotações)."""
    
    class Meta:
        model = Client
        fields = ['annotations']


class ClientSensitiveSerializer(serializers.ModelSerializer):
    """Serializer para campos sensíveis (requer aprovação)."""
    
    class Meta:
        model = Client
        fields = ['cnpj', 'razao_social', 'client_status', 'is_active']
