from django.db.models import Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.clients.models import Client
from apps.perdcomps.models import PerDcomp


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
        current_year_start = now.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )

        # Last 6 months for charts
        six_months_ago = now - timedelta(days=180)
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
        perdcomps_vencimento_this_month = PerDcomp.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
            data_vencimento__gte=current_month_start,
            data_vencimento__lt=current_month_start + timedelta(days=32),  # Next month
        ).count()

        # 3. Total PerDcomps and new ones this month
        total_perdcomps = PerDcomp.objects.filter(
            is_active=True, deleted_at__isnull=True
        ).count()

        new_perdcomps_this_month = PerDcomp.objects.filter(
            is_active=True, deleted_at__isnull=True, created_at__gte=current_month_start
        ).count()

        # 4. Taxa de Aprovação (PerDcomps this year with positive status)
        perdcomps_this_year = PerDcomp.objects.filter(
            is_active=True, deleted_at__isnull=True, created_at__gte=current_year_start
        )

        total_perdcomps_this_year = perdcomps_this_year.count()

        # Define positive/finished statuses
        positive_statuses = [
            PerDcomp.Status.TRANSMITIDO,
            PerDcomp.Status.DEFERIDO,
            PerDcomp.Status.PARCIALMENTE_DEFERIDO,
        ]

        perdcomps_with_positive_status = perdcomps_this_year.filter(
            status__in=positive_statuses
        ).count()

        # Calculate approval rate
        approval_rate = 0
        if total_perdcomps_this_year > 0:
            approval_rate = round(
                (perdcomps_with_positive_status / total_perdcomps_this_year) * 100, 1
            )

        # === CHARTS DATA ===

        # 1. Clients registered in last 6 months (month by month)
        clients_by_month = []
        current_date = six_months_start

        for i in range(6):
            month_start = current_date
            if current_date.month == 12:
                month_end = current_date.replace(
                    year=current_date.year + 1, month=1, day=1
                )
            else:
                month_end = current_date.replace(month=current_date.month + 1, day=1)

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
                    "month": month_names[current_date.month],
                    "year": current_date.year,
                    "count": clients_count,
                }
            )

            # Move to next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

        # 2. PerDcomps registered in last 6 months (month by month)
        perdcomps_by_month = []
        current_date = six_months_start

        for i in range(6):
            month_start = current_date
            if current_date.month == 12:
                month_end = current_date.replace(
                    year=current_date.year + 1, month=1, day=1
                )
            else:
                month_end = current_date.replace(month=current_date.month + 1, day=1)

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
                    "month": month_names[current_date.month],
                    "year": current_date.year,
                    "count": perdcomps_count,
                }
            )

            # Move to next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

        # 3. Status distribution for PerDcomps this year
        perdcomps_deferido = perdcomps_this_year.filter(
            status=PerDcomp.Status.DEFERIDO
        ).count()

        perdcomps_indeferido = perdcomps_this_year.filter(
            status=PerDcomp.Status.INDEFERIDO
        ).count()

        # In analysis = all other statuses (RASCUNHO, TRANSMITIDO, EM_PROCESSAMENTO, etc.)
        processing_statuses = [
            PerDcomp.Status.RASCUNHO,
            PerDcomp.Status.TRANSMITIDO,
            PerDcomp.Status.EM_PROCESSAMENTO,
        ]

        perdcomps_em_analise = perdcomps_this_year.filter(
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
                    "total_count": total_perdcomps_this_year,
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
