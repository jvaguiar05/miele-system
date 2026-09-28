from datetime import date, timedelta
from decimal import Decimal
import csv
import io

from django.db import transaction, IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from apps.identity.permissions import IsEmployeeOrAdmin
from apps.perdcomps.models import PerDcomp
from apps.perdcomps.deadlines import OPEN_STATUSES
from apps.perdcomps.deadline_views import safe_cell
from common.audit.services import AuditService
from .models import Client, QuarterSnapshot
from .dashboard_operations import money


def current_position():
    today = timezone.localdate()
    quarter = (today.month - 1) // 3 + 1
    end = (date(today.year + 1, 1, 1) if quarter == 4 else date(today.year, quarter * 3 + 1, 1)) - timedelta(days=1)
    clients = {c.id: c for c in Client.objects.filter(is_active=True, deleted_at__isnull=True)}
    processes = PerDcomp.objects.filter(is_active=True, deleted_at__isnull=True, client_id__in=clients, status__in=OPEN_STATUSES).order_by("client_id", "id")
    rows, companies = [], {}
    total, missing = Decimal(0), 0
    for p in processes:
        client = clients[p.client_id]
        balance = money(p.valor_saldo)
        missing += int(balance is None)
        total += balance or Decimal(0)
        row = {"id": str(p.public_id), "number": p.numero_perdcomp, "client_id": str(client.public_id), "client": client.razao_social, "cnpj": client.cnpj, "status": p.get_status_display(), "due": p.data_vencimento.isoformat(), "balance": str(balance) if balance is not None else None}
        rows.append(row)
        company = companies.setdefault(p.client_id, {"id": str(client.public_id), "name": client.razao_social, "cnpj": client.cnpj, "count": 0, "balance": Decimal(0), "missing": 0})
        company["count"] += 1
        company["balance"] += balance or Decimal(0)
        company["missing"] += int(balance is None)
    return {"year": today.year, "quarter": quarter, "quarter_end": end.isoformat(), "reference_date": today.isoformat(), "balance": str(total), "missing": missing, "count": len(rows), "companies": [{**c, "balance": str(c["balance"])} for c in companies.values()], "processes": rows}


def summary(snapshot):
    return {"id": str(snapshot.public_id), "year": snapshot.year, "quarter": snapshot.quarter, "kind": snapshot.kind, "captured_at": snapshot.captured_at.isoformat(), "captured_by": snapshot.captured_by, "note": snapshot.note, "balance": snapshot.payload["balance"], "missing": snapshot.payload["missing"], "count": snapshot.payload["count"]}


class CaptureInput(serializers.Serializer):
    year = serializers.IntegerField(min_value=2000, max_value=9999)
    quarter = serializers.IntegerField(min_value=1, max_value=4)
    kind = serializers.ChoiceField(choices=["position", "closing"])
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def quarter_current(request):
    position = current_position()
    year, quarter = position["year"], position["quarter"]
    previous = QuarterSnapshot.objects.filter(kind="closing", year=year if quarter > 1 else year - 1, quarter=quarter - 1 if quarter > 1 else 4).first()
    closed = QuarterSnapshot.objects.filter(kind="closing", year=year, quarter=quarter).first()
    position["previous_closing"] = summary(previous) if previous else None
    position["difference"] = str(Decimal(position["balance"]) - Decimal(previous.payload["balance"])) if previous and not position["missing"] else None
    position["closing"] = summary(closed) if closed else None
    position["can_close"] = not closed and not position["missing"] and position["reference_date"] == position["quarter_end"]
    return Response(position)


@api_view(["GET", "POST"])
@permission_classes([IsEmployeeOrAdmin])
def quarter_snapshots(request):
    if request.method == "GET":
        pagination = PageNumberPagination()
        pagination.page_size = 20
        rows = pagination.paginate_queryset(QuarterSnapshot.objects.all(), request)
        return pagination.get_paginated_response([summary(s) for s in rows])
    if request.user.role != "admin":
        return Response({"detail": "Somente administradores podem registrar posições e fechamentos."}, status=403)
    serializer = CaptureInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    try:
        with transaction.atomic():
            position = current_position()
            if (values["year"], values["quarter"]) != (position["year"], position["quarter"]):
                return Response({"detail": "Só é possível registrar o trimestre atual; dados passados não são reconstruídos."}, status=400)
            if values["kind"] == "closing":
                if position["reference_date"] != position["quarter_end"]:
                    return Response({"detail": "O fechamento fica disponível no último dia do trimestre. Antes disso, salve uma posição parcial."}, status=400)
                if position["missing"]:
                    return Response({"detail": "Corrija os saldos ausentes ou inválidos antes de fechar."}, status=400)
            snapshot = QuarterSnapshot.objects.create(year=position["year"], quarter=position["quarter"], kind=values["kind"], captured_by=request.user.get_full_name() or request.user.username, note=values.get("note", ""), payload=position)
            AuditService.log_action("CUSTOM", snapshot, user=request.user, metadata={"type": "quarter_snapshot", "year": snapshot.year, "quarter": snapshot.quarter, "kind": snapshot.kind})
    except IntegrityError:
        return Response({"detail": "Este trimestre já tem um fechamento registrado."}, status=409)
    return Response(summary(snapshot), status=201)


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def quarter_snapshot_detail(request, public_id):
    snapshot = get_object_or_404(QuarterSnapshot, public_id=public_id)
    if request.query_params.get("export") == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["Ano", "Trimestre", "Tipo", "Capturado em", "Responsável", "Cliente", "CNPJ", "Processo", "Status", "Vencimento", "Saldo"])
        for p in snapshot.payload["processes"]:
            writer.writerow([safe_cell(v) for v in [snapshot.year, snapshot.quarter, snapshot.get_kind_display(), snapshot.captured_at.isoformat(), snapshot.captured_by, p["client"], p["cnpj"], p["number"], p["status"], p["due"], p["balance"]]])
        response = HttpResponse("\ufeff" + stream.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="trimestre-{snapshot.year}-{snapshot.quarter}.csv"'
        return response
    return Response({**summary(snapshot), "payload": snapshot.payload})
