"""Read-only reports and the due-date audit trail."""
import csv
import io
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.clients.models import Client
from apps.clients.dashboard_operations import money
from apps.identity.permissions import IsEmployeeOrAdmin
from common.audit.models import AuditLog
from .deadline_views import safe_cell
from .deadlines import OPEN_STATUSES
from .models import PerDcomp


class ReportPagination(PageNumberPagination):
    page_size = 50


class StatusFilters(serializers.Serializer):
    client = serializers.CharField(required=False, max_length=255, allow_blank=True)
    client_id = serializers.UUIDField(required=False)
    client_ids = serializers.CharField(required=False, max_length=4000, allow_blank=True)
    status = serializers.ChoiceField(choices=PerDcomp.Status.choices, required=False)
    tax = serializers.CharField(required=False, max_length=255, allow_blank=True)
    date_field = serializers.ChoiceField(choices=["data_transmissao", "data_vencimento", "created_at"], default="data_transmissao")
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    scope = serializers.ChoiceField(choices=["all", "transmitted", "open"], default="all")
    export = serializers.ChoiceField(choices=["csv"], required=False)

    def validate(self, attrs):
        if attrs.get("start") and attrs.get("end") and attrs["start"] > attrs["end"]:
            raise serializers.ValidationError("A data inicial deve ser anterior à final.")
        if attrs.get("client_ids"):
            import uuid
            raw_ids = [item.strip() for item in attrs["client_ids"].split(",") if item.strip()]
            if len(raw_ids) > 100:
                raise serializers.ValidationError({"client_ids": "Selecione no máximo 100 clientes."})
            try:
                attrs["client_ids"] = [uuid.UUID(item) for item in raw_ids]
            except ValueError:
                raise serializers.ValidationError({"client_ids": "Há um identificador de cliente inválido."})
        return attrs


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def status_report(request):
    serializer = StatusFilters(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    filters = serializer.validated_data
    clients = Client.objects.filter(is_active=True, deleted_at__isnull=True)
    if filters.get("client_id"):
        clients = clients.filter(public_id=filters["client_id"])
    if filters.get("client_ids"):
        clients = clients.filter(public_id__in=filters["client_ids"])
    if filters.get("client"):
        clients = clients.filter(Q(razao_social__icontains=filters["client"]) | Q(cnpj__icontains=filters["client"]))
    client_map = {client.id: client for client in clients}
    records = PerDcomp.objects.filter(is_active=True, deleted_at__isnull=True, client_id__in=client_map)
    if filters.get("status"):
        records = records.filter(status=filters["status"])
    if filters.get("tax"):
        records = records.filter(tributo_pedido__icontains=filters["tax"])
    if filters["scope"] == "transmitted":
        records = records.filter(data_transmissao__lte=timezone.localdate()).exclude(status__in=["RASCUNHO", "CANCELADO"])
    elif filters["scope"] == "open":
        records = records.filter(status__in=OPEN_STATUSES)
    field = filters["date_field"] + ("__date" if filters["date_field"] == "created_at" else "")
    for bound, lookup in [("start", "gte"), ("end", "lte")]:
        if filters.get(bound):
            records = records.filter(**{f"{field}__{lookup}": filters[bound]})
    rows, counts = [], {key: 0 for key, _ in PerDcomp.Status.choices}
    total, balance, missing = Decimal(0), Decimal(0), 0
    for record in records.order_by("data_vencimento", "id").iterator():
        requested, remaining = money(record.valor_pedido), money(record.valor_saldo)
        total += requested or Decimal(0)
        balance += remaining or Decimal(0)
        missing += int(requested is None) + int(remaining is None)
        counts[record.status] = counts.get(record.status, 0) + 1
        rows.append({
            "id": str(record.public_id), "number": record.numero_perdcomp,
            "client": client_map[record.client_id].razao_social, "cnpj": record.cnpj,
            "status": record.status, "status_label": record.get_status_display(), "tax": record.tributo_pedido,
            "transmission": record.data_transmissao.isoformat() if record.data_transmissao else None,
            "due": record.data_vencimento.isoformat() if record.data_vencimento else None,
            "amount": str(requested) if requested is not None else None,
            "balance": str(remaining) if remaining is not None else None,
        })
    if filters.get("export"):
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["Cliente", "CNPJ", "Processo", "Status", "Tributo", "Transmissão", "Vencimento", "Valor pedido", "Saldo cadastrado"])
        for row in rows:
            writer.writerow([safe_cell(row[key]) for key in ["client", "cnpj", "number", "status_label", "tax", "transmission", "due", "amount", "balance"]])
        response = HttpResponse("\ufeff" + stream.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="relatorio-status.csv"'
        return response
    pagination = ReportPagination()
    page = pagination.paginate_queryset(rows, request)
    response = pagination.get_paginated_response(page)
    response.data["summary"] = {"amount": str(total), "balance": str(balance), "missing_values": missing, "statuses": counts}
    response.data["selected_clients"] = [
        {"id": str(client.public_id), "name": client.razao_social, "cnpj": client.cnpj}
        for client in client_map.values()
    ] if filters.get("client_id") or filters.get("client_ids") else []
    return response


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def deadline_history(request, public_id):
    record = get_object_or_404(PerDcomp, public_id=public_id, deleted_at__isnull=True)
    logs = AuditLog.objects.filter(
        content_type=ContentType.objects.get_for_model(PerDcomp), object_id=str(record.pk),
    ).filter(Q(new_data__has_key="data_vencimento") | Q(metadata__type="due_date_override")).select_related("user").order_by("-timestamp", "-id")
    rows, overrides = [], set()
    for log in logs:
        old = (log.old_data or {}).get("data_vencimento")
        new = (log.new_data or {}).get("data_vencimento")
        reason = (log.metadata or {}).get("reason") if (log.metadata or {}).get("type") == "due_date_override" else None
        key = (str(log.correlation_id), str(old), str(new))
        if reason:
            overrides.add(key)
        elif old == new or key in overrides:
            continue
        rows.append({"id": log.id, "timestamp": log.timestamp.isoformat(),
                     "user": (log.user.get_full_name() or log.user.username) if log.user else "Sistema / usuário indisponível",
                     "previous_due": old, "new_due": new, "reason": reason,
                     "kind": "exception" if reason else "initial" if log.action == "CREATE" else "change"})
    pagination = ReportPagination()
    page = pagination.paginate_queryset(rows, request)
    return pagination.get_paginated_response(page)
