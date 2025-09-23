from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.db.models import Q
from common.approvals.models import ApprovalRequest
from common.approvals.services import ApprovalService
from .serializers import ApprovalRequestSerializer, ApprovalActionSerializer


class PingSerializer(serializers.Serializer):
    ok = serializers.BooleanField()


class PingView(APIView):
    authentication_classes = []
    permission_classes = []
    serializer_class = PingSerializer

    def get(self, request):
        return Response({"ok": True})


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
