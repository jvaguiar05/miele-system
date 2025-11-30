from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.contrib.auth import get_user_model

from .models import AuditLog
from .serializers import (
    AuditLogSerializer,
    AuditLogFilterSerializer,
    RecentLogsFilterSerializer,
)

User = get_user_model()


def get_internal_ids_from_public_ids(filters):
    """
    Converte public_ids (UUIDs) para IDs internos (integers) para filtros de auditoria.

    Args:
        filters (dict): Dicionário com filtros que podem conter public_ids

    Returns:
        dict: Filtros atualizados com IDs internos
    """
    updated_filters = filters.copy()

    # Converter user_id (public_id) para user_id interno
    if "user_id" in filters:
        try:
            user = User.objects.get(public_id=filters["user_id"])
            updated_filters["user_internal_id"] = user.id
        except User.DoesNotExist:
            # Se o usuário não existe, adicionar filtro que não retornará resultados
            updated_filters["user_internal_id"] = -1
        del updated_filters["user_id"]

    # Converter client_id (public_id) para filtro de recurso
    if "client_id" in filters:
        try:
            from apps.clients.models import Client

            client = Client.objects.get(public_id=filters["client_id"])
            updated_filters["client_internal_id"] = client.id
        except Client.DoesNotExist:
            updated_filters["client_internal_id"] = -1
        del updated_filters["client_id"]

    # Converter perdcomp_id (public_id) para filtro de recurso
    if "perdcomp_id" in filters:
        try:
            from apps.perdcomps.models import PerDcomp

            perdcomp = PerDcomp.objects.get(public_id=filters["perdcomp_id"])
            updated_filters["perdcomp_internal_id"] = perdcomp.id
        except PerDcomp.DoesNotExist:
            updated_filters["perdcomp_internal_id"] = -1
        del updated_filters["perdcomp_id"]

    return updated_filters


class AuditLogPagination(PageNumberPagination):
    """Paginação customizada para logs de auditoria."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema(
    tags=["Activities - Logs"],
    summary="Listar logs de auditoria",
    description="""
    Lista todos os logs de auditoria do sistema de forma paginada.
    
    Suporta filtros por:
    - Período (start_date, end_date)
    - Ação (action)
    - Tipo de recurso (resource_type) 
    - ID do recurso (resource_id)
    - Usuário (user_id)
    - ID de correlação (correlation_id)
    """,
    parameters=[
        OpenApiParameter(
            name="page",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Número da página",
        ),
        OpenApiParameter(
            name="page_size",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Número de itens por página (máximo 100)",
        ),
        OpenApiParameter(
            name="start_date",
            type=OpenApiTypes.DATETIME,
            location=OpenApiParameter.QUERY,
            description="Data inicial para filtrar os logs",
        ),
        OpenApiParameter(
            name="end_date",
            type=OpenApiTypes.DATETIME,
            location=OpenApiParameter.QUERY,
            description="Data final para filtrar os logs",
        ),
        OpenApiParameter(
            name="action",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Tipo de ação (CREATE, UPDATE, DELETE, LOGIN, etc.)",
        ),
        OpenApiParameter(
            name="resource_type",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Tipo de recurso (ex: clients.client, perdcomps.perdcomp)",
        ),
        OpenApiParameter(
            name="resource_id",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="ID do recurso afetado",
        ),
        OpenApiParameter(
            name="user_id",
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.QUERY,
            description="Public ID (UUID) do usuário que executou a ação",
        ),
        OpenApiParameter(
            name="client_id",
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.QUERY,
            description="Public ID (UUID) do cliente relacionado",
        ),
        OpenApiParameter(
            name="perdcomp_id",
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.QUERY,
            description="Public ID (UUID) do PER/DCOMP relacionado",
        ),
        OpenApiParameter(
            name="correlation_id",
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.QUERY,
            description="ID de correlação para rastrear ações relacionadas",
        ),
    ],
    responses={200: AuditLogSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def list_audit_logs(request):
    """Lista logs de auditoria com filtros e paginação."""

    # Validar filtros
    filter_serializer = AuditLogFilterSerializer(data=request.query_params)
    if not filter_serializer.is_valid():
        return Response(filter_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    filters = filter_serializer.validated_data

    # Converter public_ids para IDs internos
    filters = get_internal_ids_from_public_ids(filters)

    # Construir queryset com otimizações
    queryset = (
        AuditLog.objects.select_related("user", "content_type")
        .prefetch_related("content_object")
        .all()
    )

    # Aplicar filtros
    if "start_date" in filters:
        queryset = queryset.filter(timestamp__gte=filters["start_date"])

    if "end_date" in filters:
        queryset = queryset.filter(timestamp__lte=filters["end_date"])

    if "action" in filters:
        queryset = queryset.filter(action=filters["action"])

    if "user_internal_id" in filters:
        queryset = queryset.filter(user_id=filters["user_internal_id"])

    if "correlation_id" in filters:
        queryset = queryset.filter(correlation_id=filters["correlation_id"])

    # Filtrar por cliente específico (usando ID interno convertido)
    if "client_internal_id" in filters:
        try:
            client_content_type = ContentType.objects.get(
                app_label="clients", model="client"
            )
            queryset = queryset.filter(
                content_type=client_content_type,
                object_id=str(filters["client_internal_id"]),
            )
        except ContentType.DoesNotExist:
            queryset = queryset.none()

    # Filtrar por perdcomp específico (usando ID interno convertido)
    if "perdcomp_internal_id" in filters:
        try:
            perdcomp_content_type = ContentType.objects.get(
                app_label="perdcomps", model="perdcomp"
            )
            queryset = queryset.filter(
                content_type=perdcomp_content_type,
                object_id=str(filters["perdcomp_internal_id"]),
            )
        except ContentType.DoesNotExist:
            queryset = queryset.none()

    if "resource_type" in filters:
        try:
            app_label, model = filters["resource_type"].split(".")
            content_type = ContentType.objects.get(app_label=app_label, model=model)
            queryset = queryset.filter(content_type=content_type)
        except (ValueError, ContentType.DoesNotExist):
            return Response(
                {"error": "resource_type inválido"}, status=status.HTTP_400_BAD_REQUEST
            )

    if "resource_id" in filters:
        queryset = queryset.filter(object_id=filters["resource_id"])

    # Aplicar paginação
    paginator = AuditLogPagination()
    page = paginator.paginate_queryset(queryset, request)

    if page is not None:
        serializer = AuditLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # Fallback sem paginação
    serializer = AuditLogSerializer(queryset, many=True)
    return Response(serializer.data)


@extend_schema(
    tags=["Activities - Logs"],
    summary="Logs recentes",
    description="""
    Retorna logs de auditoria desde uma data específica.
    
    Útil para sincronização e atualizações em tempo real.
    """,
    parameters=[
        OpenApiParameter(
            name="since",
            type=OpenApiTypes.DATETIME,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Data a partir da qual buscar os logs",
        ),
        OpenApiParameter(
            name="limit",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Número máximo de logs (padrão: 100, máximo: 1000)",
        ),
    ],
    responses={200: AuditLogSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def recent_audit_logs(request):
    """Retorna logs recentes desde uma data específica."""

    # Validar parâmetros
    filter_serializer = RecentLogsFilterSerializer(data=request.query_params)
    if not filter_serializer.is_valid():
        return Response(filter_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    filters = filter_serializer.validated_data

    # Construir queryset com otimizações
    queryset = (
        AuditLog.objects.select_related("user", "content_type")
        .prefetch_related("content_object")
        .filter(timestamp__gte=filters["since"])
    )

    # Aplicar limite
    limit = filters.get("limit", 100)
    queryset = queryset[:limit]

    serializer = AuditLogSerializer(queryset, many=True)
    return Response(
        {
            "count": len(serializer.data),
            "since": filters["since"],
            "results": serializer.data,
        }
    )


@extend_schema(
    tags=["Activities - Logs"],
    summary="Meus logs",
    description="""
    Retorna todos os logs de auditoria relacionados ao usuário autenticado.
    
    Inclui ações executadas pelo usuário e ações que afetaram o usuário.
    """,
    parameters=[
        OpenApiParameter(
            name="page",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Número da página",
        ),
        OpenApiParameter(
            name="page_size",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Número de itens por página (máximo 100)",
        ),
        OpenApiParameter(
            name="action",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filtrar por tipo de ação",
        ),
        OpenApiParameter(
            name="start_date",
            type=OpenApiTypes.DATETIME,
            location=OpenApiParameter.QUERY,
            description="Data inicial",
        ),
        OpenApiParameter(
            name="end_date",
            type=OpenApiTypes.DATETIME,
            location=OpenApiParameter.QUERY,
            description="Data final",
        ),
    ],
    responses={200: AuditLogSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def my_audit_logs(request):
    """Retorna logs do usuário autenticado."""

    # Validar filtros básicos
    filter_data = {
        "page": request.query_params.get("page"),
        "page_size": request.query_params.get("page_size"),
        "action": request.query_params.get("action"),
        "start_date": request.query_params.get("start_date"),
        "end_date": request.query_params.get("end_date"),
    }

    # Remover valores None
    filter_data = {k: v for k, v in filter_data.items() if v is not None}

    filter_serializer = AuditLogFilterSerializer(data=filter_data)
    if not filter_serializer.is_valid():
        return Response(filter_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    filters = filter_serializer.validated_data
    user = request.user

    # Construir queryset - logs do usuário ou que afetaram o usuário
    from django.contrib.contenttypes.models import ContentType
    from django.db import models

    user_content_type = ContentType.objects.get_for_model(user)

    queryset = (
        AuditLog.objects.select_related("user", "content_type")
        .prefetch_related("content_object")
        .filter(
            models.Q(user=user)  # Ações executadas pelo usuário
            | models.Q(  # Ações que afetaram o usuário
                content_type=user_content_type, object_id=str(user.id)
            )
        )
    )

    # Aplicar filtros adicionais
    if "start_date" in filters:
        queryset = queryset.filter(timestamp__gte=filters["start_date"])

    if "end_date" in filters:
        queryset = queryset.filter(timestamp__lte=filters["end_date"])

    if "action" in filters:
        queryset = queryset.filter(action=filters["action"])

    # Aplicar paginação
    paginator = AuditLogPagination()
    page = paginator.paginate_queryset(queryset, request)

    if page is not None:
        serializer = AuditLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # Fallback sem paginação
    serializer = AuditLogSerializer(queryset, many=True)
    return Response(serializer.data)
