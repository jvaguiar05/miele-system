from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Q
from common.approvals.models import ApprovalRequest
from common.approvals.services import ApprovalService
from .serializers import ApprovalRequestSerializer, ApprovalActionSerializer
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample


class PingSerializer(serializers.Serializer):
    ok = serializers.BooleanField()


class PingView(APIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = PingSerializer

    @extend_schema(
        tags=["Admin"],
        summary="Verificação de saúde do admin",
        description="Endpoint simples para verificar se o admin está funcionando. Não requer autenticação.",
        responses={
            200: OpenApiResponse(
                description="Admin funcionando corretamente",
                examples=[OpenApiExample("Sucesso", value={"ok": True})],
            )
        },
    )
    def get(self, request):
        return Response({"ok": True})


@extend_schema(tags=["Admin"])
class ApprovalRequestAdminViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para administração de solicitações de aprovação.
    Apenas administradores podem acessar.
    """

    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = ApprovalRequestSerializer

    def get_queryset(self):
        """
        Retorna queryset com filtros opcionais.
        """
        queryset = ApprovalRequest.objects.all()

        # Filtros opcionais
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        resource_type_filter = self.request.query_params.get("resource_type")
        if resource_type_filter:
            queryset = queryset.filter(resource_type=resource_type_filter)

        requested_by_filter = self.request.query_params.get("requested_by")
        if requested_by_filter:
            queryset = queryset.filter(requested_by__username=requested_by_filter)

        return queryset

    @extend_schema(
        tags=["Admin"],
        summary="Listar solicitações de aprovação",
        description="Lista todas as solicitações de aprovação com filtros opcionais (status, resource_type, requested_by).",
        responses={
            200: OpenApiResponse(description="Lista de solicitações de aprovação"),
        },
    )
    def list(self, request, *args, **kwargs):
        """Lista todas as solicitações de aprovação."""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        tags=["Admin"],
        summary="Detalhar solicitação de aprovação",
        description="Retorna os detalhes de uma solicitação de aprovação específica.",
        responses={
            200: OpenApiResponse(description="Detalhes da solicitação de aprovação"),
            404: OpenApiResponse(description="Solicitação não encontrada"),
        },
    )
    def retrieve(self, request, *args, **kwargs):
        """Retorna uma solicitação de aprovação específica."""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        tags=["Admin"],
        summary="Aprovar ou rejeitar solicitação",
        description="Permite que administradores aprovem ou rejeitem solicitações de aprovação pendentes.",
        request=ApprovalActionSerializer,
        responses={
            200: OpenApiResponse(
                description="Solicitação processada com sucesso",
                examples=[OpenApiExample("Aprovado", value={"message": "Solicitação aprovada e executada com sucesso.", "approval_request": {}})],
            ),
            400: OpenApiResponse(description="Erro na validação ou processamento"),
            404: OpenApiResponse(description="Solicitação não encontrada"),
        },
    )
    @action(detail=True, methods=["post"], url_path="approve-reject")
    def approve_reject(self, request, pk=None):
        """
        Aprova ou rejeita uma solicitação de aprovação.
        """
        approval_request = self.get_object()
        serializer = ApprovalActionSerializer(
            data=request.data, context={"approval_request": approval_request}
        )
        serializer.is_valid(raise_exception=True)

        action_type = serializer.validated_data["approval_action"]
        notes = serializer.validated_data.get("notes", "")

        try:
            if action_type == "approve":
                success = ApprovalService.approve_request(
                    approval_request, request.user, notes
                )
                message = "Solicitação aprovada e executada com sucesso."
            else:
                success = ApprovalService.reject_request(
                    approval_request, request.user, notes
                )
                message = "Solicitação rejeitada com sucesso."

            if success:
                # Retornar a solicitação atualizada
                approval_request.refresh_from_db()
                response_serializer = ApprovalRequestSerializer(approval_request)
                return Response(
                    {"message": message, "approval_request": response_serializer.data}
                )
            else:
                return Response(
                    {"error": "Não foi possível processar a solicitação."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except Exception as e:
            return Response(
                {"error": f"Erro ao processar solicitação: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Admin"],
        summary="Listar solicitações pendentes",
        description="Retorna todas as solicitações de aprovação que estão aguardando análise.",
        responses={
            200: OpenApiResponse(
                description="Lista de solicitações pendentes",
                examples=[OpenApiExample("Lista pendentes", value=[])],
            )
        },
    )
    @action(detail=False, methods=["get"], url_path="pending")
    def pending(self, request):
        """
        Lista apenas solicitações pendentes.
        """
        # Filtrar apenas requests pendentes por padrão
        queryset = self.get_queryset().filter(status=ApprovalRequest.ApprovalStatus.PENDING)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=["Admin"],
        summary="Estatísticas de solicitações",
        description="Retorna estatísticas resumidas sobre solicitações de aprovação (pendentes, aprovadas, rejeitadas).",
        responses={
            200: OpenApiResponse(
                description="Estatísticas das solicitações",
                examples=[OpenApiExample("Stats", value={"pending": 5, "approved": 20, "rejected": 3, "total": 28})],
            )
        },
    )
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """
        Retorna estatísticas das solicitações de aprovação.
        """
        stats = {
            "pending": ApprovalRequest.objects.filter(
                status=ApprovalRequest.ApprovalStatus.PENDING
            ).count(),
            "approved": ApprovalRequest.objects.filter(
                status=ApprovalRequest.ApprovalStatus.APPROVED
            ).count(),
            "rejected": ApprovalRequest.objects.filter(
                status=ApprovalRequest.ApprovalStatus.REJECTED
            ).count(),
            "executed": ApprovalRequest.objects.filter(
                status=ApprovalRequest.ApprovalStatus.EXECUTED
            ).count(),
        }
        return Response(stats)
