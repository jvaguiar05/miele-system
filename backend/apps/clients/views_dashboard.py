from django.db.models import Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, serializers
from drf_spectacular.utils import extend_schema

from apps.clients.models import Client
from apps.perdcomps.models import PerDcomp


class DashboardStatsSerializer(serializers.Serializer):
    """Serializer para resposta das estatísticas do dashboard."""
    
    # Main cards
    total_active_clients = serializers.IntegerField()
    new_clients_this_month = serializers.IntegerField()
    perdcomps_vencimento_this_month = serializers.IntegerField()
    pending_approval_requests = serializers.IntegerField()
    
    # Chart data
    clients_last_6_months = serializers.ListField(child=serializers.DictField())
    perdcomps_last_6_months = serializers.ListField(child=serializers.DictField())
    
    # Additional stats
    clients_by_status = serializers.DictField()
    perdcomps_by_status = serializers.DictField()


@extend_schema(responses=DashboardStatsSerializer)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    """
    Endpoint para fornecer estatísticas do dashboard principal
    """
    try:
        now = timezone.now()
        current_month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        # Calcular os últimos 6 meses dinamicamente incluindo o mês atual
        six_months_ago = now - relativedelta(
            months=5
        )  # 5 meses atrás + mês atual = 6 meses
        six_months_start = six_months_ago.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        # === MAIN CARDS DATA ===

        # 1. Active clients and new clients this month
        total_active_clients = Client.objects.filter(
            is_active=True, deleted_at__isnull=True
        ).count()

        new_clients_this_month = Client.objects.filter(
            is_active=True, deleted_at__isnull=True, created_at__gte=current_month_start
        ).count()

        # 2. PerDcomps with vencimento this month
        next_month_start = current_month_start + relativedelta(months=1)
        perdcomps_vencimento_this_month = PerDcomp.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
            data_vencimento__gte=current_month_start,
            data_vencimento__lt=next_month_start,
        ).count()

        # 3. Total PerDcomps and new ones this month
        total_perdcomps = PerDcomp.objects.filter(
            is_active=True, deleted_at__isnull=True
        ).count()

        new_perdcomps_this_month = PerDcomp.objects.filter(
            is_active=True, deleted_at__isnull=True, created_at__gte=current_month_start
        ).count()

        # 4. Taxa de Aprovação (todas as PerDcomps do sistema, não apenas do ano)
        all_perdcomps = PerDcomp.objects.filter(is_active=True, deleted_at__isnull=True)

        total_all_perdcomps = all_perdcomps.count()

        # Define positive/finished statuses
        positive_statuses = [
            PerDcomp.Status.TRANSMITIDO,
            PerDcomp.Status.DEFERIDO,
            PerDcomp.Status.PARCIALMENTE_DEFERIDO,
        ]

        perdcomps_with_positive_status = all_perdcomps.filter(
            status__in=positive_statuses
        ).count()

        # Calculate approval rate
        approval_rate = 0
        if total_all_perdcomps > 0:
            approval_rate = round(
                (perdcomps_with_positive_status / total_all_perdcomps) * 100, 1
            )

        # === CHARTS DATA ===

        # 1. Clients registered in last 6 months (month by month) - dinâmico
        clients_by_month = []

        for i in range(6):
            # Calcular o mês dinamicamente (5 meses atrás até o mês atual)
            month_date = now - relativedelta(months=5 - i)
            month_start = month_date.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            month_end = month_start + relativedelta(months=1)

            clients_count = Client.objects.filter(
                is_active=True,
                deleted_at__isnull=True,
                created_at__gte=month_start,
                created_at__lt=month_end,
            ).count()

            # Get month name in Portuguese
            month_names = {
                1: "Jan",
                2: "Fev",
                3: "Mar",
                4: "Abr",
                5: "Mai",
                6: "Jun",
                7: "Jul",
                8: "Ago",
                9: "Set",
                10: "Out",
                11: "Nov",
                12: "Dez",
            }

            clients_by_month.append(
                {
                    "month": month_names[month_start.month],
                    "year": month_start.year,
                    "count": clients_count,
                }
            )

        # 2. PerDcomps registered in last 6 months (month by month) - dinâmico
        perdcomps_by_month = []

        for i in range(6):
            # Calcular o mês dinamicamente (5 meses atrás até o mês atual)
            month_date = now - relativedelta(months=5 - i)
            month_start = month_date.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            month_end = month_start + relativedelta(months=1)

            perdcomps_count = PerDcomp.objects.filter(
                is_active=True,
                deleted_at__isnull=True,
                created_at__gte=month_start,
                created_at__lt=month_end,
            ).count()

            month_names = {
                1: "Jan",
                2: "Fev",
                3: "Mar",
                4: "Abr",
                5: "Mai",
                6: "Jun",
                7: "Jul",
                8: "Ago",
                9: "Set",
                10: "Out",
                11: "Nov",
                12: "Dez",
            }

            perdcomps_by_month.append(
                {
                    "month": month_names[month_start.month],
                    "year": month_start.year,
                    "count": perdcomps_count,
                }
            )

        # 3. Status distribution for PerDcomps dos últimos 6 meses (não do ano todo)
        perdcomps_last_6_months = PerDcomp.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
            created_at__gte=six_months_start,
        )

        perdcomps_deferido = perdcomps_last_6_months.filter(
            status=PerDcomp.Status.DEFERIDO
        ).count()

        perdcomps_indeferido = perdcomps_last_6_months.filter(
            status=PerDcomp.Status.INDEFERIDO
        ).count()

        # In analysis = all other statuses (RASCUNHO, TRANSMITIDO, EM_PROCESSAMENTO, etc.)
        processing_statuses = [
            PerDcomp.Status.RASCUNHO,
            PerDcomp.Status.TRANSMITIDO,
            PerDcomp.Status.EM_PROCESSAMENTO,
        ]

        perdcomps_em_analise = perdcomps_last_6_months.filter(
            status__in=processing_statuses
        ).count()

        # Build response
        response_data = {
            "main_cards": {
                "clients": {
                    "total_active": total_active_clients,
                    "new_this_month": new_clients_this_month,
                },
                "perdcomps_expiring": {
                    "expiring_this_month": perdcomps_vencimento_this_month
                },
                "perdcomps_total": {
                    "total": total_perdcomps,
                    "new_this_month": new_perdcomps_this_month,
                },
                "approval_rate": {
                    "rate_percentage": approval_rate,
                    "approved_count": perdcomps_with_positive_status,
                    "total_count": total_all_perdcomps,  # Agora usando todas as perdcomps
                },
            },
            "charts": {
                "clients_last_6_months": clients_by_month,
                "perdcomps_last_6_months": perdcomps_by_month,
                "perdcomps_status_distribution": {
                    "deferido": perdcomps_deferido,
                    "indeferido": perdcomps_indeferido,
                    "em_analise": perdcomps_em_analise,
                },
            },
            "metadata": {
                "generated_at": now.isoformat(),
                "current_month": now.strftime("%Y-%m"),
                "current_year": now.year,
            },
        }

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Erro ao gerar estatísticas do dashboard: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
