"""Read-only, allowlisted audit projection shared by JSON, CSV and dashboard."""
import csv
import io
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone
from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from apps.identity.permissions import IsEmployeeOrAdmin
from apps.clients.models import Client
from apps.perdcomps.models import PerDcomp
from apps.perdcomps.deadline_views import safe_cell
from .models import AuditLog
from .services import AuditService

SP = ZoneInfo("America/Sao_Paulo")
FIELDS = {
    "clients.client": {"razao_social", "nome_fantasia", "cnpj", "client_status", "is_active", "regime_tributacao", "recuperacao_judicial", "autorizado_para_envio"},
    "perdcomps.perdcomp": {"numero", "numero_perdcomp", "processo_protocolo", "cnpj", "data_transmissao", "data_vencimento", "data_competencia", "competencia", "tributo_pedido", "valor_pedido", "valor_compensado", "valor_recebido", "valor_saldo", "valor_selic", "status", "is_active"},
    "identity.user": {"username", "first_name", "last_name", "role", "approval_status", "is_active"},
    "approvals.approvalrequest": {"subject", "action", "status", "reason", "was_approved", "approval_notes"},
    "clients.quartersnapshot": {"year", "quarter", "kind", "note", "captured_by"},
    "clients.clientcontract": {"percentage", "starts_on", "ends_on", "reference", "notes", "billing_evolution_requested"},
}
LABELS = {"data_vencimento": "Vencimento", "data_transmissao": "Transmissão", "valor_saldo": "Saldo", "valor_pedido": "Valor pedido", "valor_recebido": "Valor recebido", "valor_compensado": "Valor compensado", "status": "Status", "razao_social": "Razão social", "numero_perdcomp": "Número PER/DCOMP", "is_active": "Ativo", "tributo_pedido": "Tributo", "client_status": "Status do cliente"}
RESOURCES = {"clients.client": "Cliente", "perdcomps.perdcomp": "PER/DCOMP", "identity.user": "Usuário", "approvals.approvalrequest": "Solicitação", "clients.quartersnapshot": "Posição trimestral", "clients.clientcontract": "Contrato percentual"}


class Filters(serializers.Serializer):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    user = serializers.CharField(required=False, max_length=200, allow_blank=True)
    client = serializers.CharField(required=False, max_length=200, allow_blank=True)
    perdcomp = serializers.CharField(required=False, max_length=200, allow_blank=True)
    action = serializers.ChoiceField(choices=AuditLog.AuditAction.choices, required=False)
    origin = serializers.ChoiceField(choices=["user", "system"], required=False)
    export = serializers.ChoiceField(choices=["csv"], required=False)

    def validate(self, attrs):
        today = timezone.localdate(timezone=SP)
        attrs.setdefault("start", attrs.get("end", today))
        attrs.setdefault("end", attrs["start"])
        if attrs["end"] == date.max:
            raise serializers.ValidationError("Data final fora do intervalo permitido.")
        if attrs["end"] < attrs["start"]:
            raise serializers.ValidationError("A data final deve ser igual ou posterior à inicial.")
        if (attrs["end"] - attrs["start"]).days > 365:
            raise serializers.ValidationError("Consulte no máximo 366 dias por vez.")
        return attrs


def scalar(value):
    # Structured fields are intentionally not emitted, even under an allowed name.
    return value if value is None or isinstance(value, (str, bool, int, float)) else "[Conteúdo estruturado omitido]"


def project(log, clients, processes):
    old = log.old_data if isinstance(log.old_data, dict) else {}
    new = log.new_data if isinstance(log.new_data, dict) else {}
    metadata = log.metadata if isinstance(log.metadata, dict) else {}
    resource = log.resource_type
    changes = []
    for field in sorted(FIELDS.get(resource, set())):
        if field not in old and field not in new:
            continue
        before, after = scalar(old.get(field)), scalar(new.get(field))
        if AuditService._values_are_different(field, before, after):
            changes.append({"field": LABELS.get(field, field.replace("_", " ").capitalize()), "before": before, "after": after})
    data = {**old, **new}
    client, process, href = "", "", None
    obj = processes.get(str(log.object_id)) if resource == "perdcomps.perdcomp" else None
    if resource == "clients.client":
        company = clients.get(str(log.object_id))
        client = str(scalar(data.get("razao_social")) or (company["razao_social"] if company else "Cliente removido"))
        if company and not company["deleted_at"]:
            href = "/clients/" + str(company["public_id"])
    elif resource == "perdcomps.perdcomp":
        process = str(scalar(data.get("numero_perdcomp")) or (obj["numero_perdcomp"] if obj else "PER/DCOMP removida"))
        company = clients.get(str(data.get("client_id") or (obj["client_id"] if obj else "")))
        client = company["razao_social"] if company else str(scalar(data.get("cnpj")) or "Cliente indisponível")
        if obj and not obj["deleted_at"]:
            href = "/perdcomps/" + str(obj["public_id"])
    reason = metadata.get("reason") if metadata.get("type") == "due_date_override" else data.get("reason") if resource == "approvals.approvalrequest" else None
    reason = scalar(reason)
    origin = "Usuário" if log.user_id else "Sistema / autoria não registrada"
    resource_label = RESOURCES.get(resource, "Outro recurso")
    return {"id": log.id, "timestamp": log.timestamp.astimezone(SP).isoformat(), "user_name": (log.user.get_full_name() or log.user.username) if log.user else origin, "origin": origin,
            "action": log.action, "action_label": log.get_action_display(), "resource": resource_label,
            "entity": process or client or resource_label, "client": client, "perdcomp": process,
            "href": href, "changes": changes, "reason": reason}


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def daily_report(request):
    serializer = Filters(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    filters = serializer.validated_data
    start = datetime.combine(filters["start"], time.min, tzinfo=SP)
    end = datetime.combine(filters["end"] + timedelta(days=1), time.min, tzinfo=SP)
    logs = AuditLog.objects.filter(timestamp__gte=start, timestamp__lt=end).select_related("user", "content_type").order_by("-timestamp", "-id")
    if request.user.role != "admin":
        logs = logs.filter(user=request.user)
    if filters.get("user"):
        term = filters["user"]
        logs = logs.filter(Q(user__username__icontains=term) | Q(user__first_name__icontains=term) | Q(user__last_name__icontains=term))
    if filters.get("action"):
        logs = logs.filter(action=filters["action"])
    if filters.get("origin"):
        logs = logs.filter(user__isnull=filters["origin"] == "system")
    clients = {str(c["id"]): c for c in Client.objects.values("id", "public_id", "razao_social", "deleted_at")}
    processes = {str(p["id"]): p for p in PerDcomp.objects.values("id", "public_id", "numero_perdcomp", "client_id", "deleted_at")}
    rows = []
    for log in logs.iterator(chunk_size=500):
        row = project(log, clients, processes)
        if filters.get("client", "").casefold() not in row["client"].casefold():
            continue
        if filters.get("perdcomp", "").casefold() not in row["perdcomp"].casefold():
            continue
        rows.append(row)
    if filters.get("export"):
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["Evento", "Data/hora São Paulo", "Usuário", "Origem", "Ação", "Recurso", "Cliente", "PER/DCOMP", "Campo", "Antes", "Depois", "Justificativa"])
        for row in rows:
            for change in row["changes"] or [{"field": "", "before": "", "after": ""}]:
                writer.writerow([safe_cell(v) for v in [row["id"], row["timestamp"], row["user_name"], row["origin"], row["action_label"], row["entity"], row["client"], row["perdcomp"], change["field"], change["before"], change["after"], row["reason"]]])
        response = HttpResponse("\ufeff" + stream.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="atualizacoes-diarias.csv"'
        return response
    pagination = PageNumberPagination()
    pagination.page_size = 20
    page = pagination.paginate_queryset(rows, request)
    response = pagination.get_paginated_response(page)
    response.data.update(start=filters["start"].isoformat(), end=filters["end"].isoformat(), timezone="America/Sao_Paulo", scope="all" if request.user.role == "admin" else "own")
    return response
