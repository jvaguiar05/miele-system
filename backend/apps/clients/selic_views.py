import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import HttpResponse
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.identity.permissions import IsEmployeeOrAdmin
from apps.perdcomps.deadline_views import safe_cell
from .models import SelicAccumulatedRate


MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


class UpdateInput(serializers.Serializer):
    rate = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("1000"))
    issued_on = serializers.DateField(required=False, allow_null=True)
    source = serializers.CharField(required=False, max_length=255, allow_blank=False)


class ImportInput(serializers.Serializer):
    csv = serializers.CharField(max_length=100_000)
    issued_on = serializers.DateField(required=False, allow_null=True)
    source = serializers.CharField(required=False, max_length=255, default="Sicalc - Receita Federal")


def row_data(item):
    return {"year": item.year, "month": item.month, "rate": f"{item.rate:.2f}", "source": item.source,
            "issued_on": item.issued_on.isoformat() if item.issued_on else None,
            "updated_at": item.updated_at.isoformat(),
            "updated_by": (item.updated_by.get_full_name() or item.updated_by.username) if item.updated_by else "Carga inicial"}


def table_response(user=None, records=None):
    records = list(records if records is not None else SelicAccumulatedRate.objects.select_related("updated_by").all())
    years = sorted({item.year for item in records})
    values = {f"{item.year}-{item.month:02d}": str(item.rate) for item in records}
    latest = max(records, key=lambda item: (item.year, item.month), default=None)
    issued = max((item.issued_on for item in records if item.issued_on), default=None)
    return {"years": years, "months": MONTHS, "values": values, "results": [row_data(item) for item in records], "count": len(records),
            "latest_period": f"{latest.year}-{latest.month:02d}" if latest else None,
            "issued_on": issued.isoformat() if issued else None,
            "source": latest.source if latest else "Sicalc - Receita Federal",
            "can_edit": bool(user and user.role == "admin")}


@api_view(["GET", "POST"])
@permission_classes([IsEmployeeOrAdmin])
def selic_table(request):
    if request.method == "GET":
        records = SelicAccumulatedRate.objects.select_related("updated_by").all()
        if request.query_params.get("year"):
            try:
                records = records.filter(year=int(request.query_params["year"]))
            except ValueError:
                return Response({"year": ["Ano inválido."]}, status=400)
        if request.query_params.get("export") == "csv":
            stream = io.StringIO()
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["ano", "mes", "taxa_acumulada", "fonte", "data_referencia", "atualizado_por", "atualizado_em"])
            for item in records:
                row = row_data(item)
                writer.writerow([safe_cell(row[key]) for key in ["year", "month", "rate", "source", "issued_on", "updated_by", "updated_at"]])
            response = HttpResponse("\ufeff" + stream.getvalue(), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="selic-acumulada.csv"'
            return response
        return Response(table_response(request.user, records))
    if request.user.role != "admin":
        return Response({"detail": "Somente administradores podem importar a tabela Selic."}, status=status.HTTP_403_FORBIDDEN)
    serializer = ImportInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    reader = csv.reader(io.StringIO(serializer.validated_data["csv"].strip()), delimiter=";")
    rows = list(reader)
    if not rows or [cell.strip().lower() for cell in rows[0]][:13] != ["ano", *MONTHS]:
        return Response({"csv": ["Cabeçalho esperado: ano;jan;fev;mar;abr;mai;jun;jul;ago;set;out;nov;dez"]}, status=400)
    parsed = []
    try:
        for line_number, row in enumerate(rows[1:], 2):
            if not row or not any(cell.strip() for cell in row):
                continue
            year = int(row[0].strip())
            if len(row) < 13:
                row += [""] * (13 - len(row))
            for month, raw in enumerate(row[1:13], 1):
                raw = raw.strip()
                if raw:
                    parsed.append((year, month, Decimal(raw.replace(".", "").replace(",", "."))))
    except (ValueError, InvalidOperation) as exc:
        return Response({"csv": [f"Valor inválido próximo da linha {line_number}: {exc}"]}, status=400)
    with transaction.atomic():
        for year, month, rate in parsed:
            SelicAccumulatedRate.objects.update_or_create(year=year, month=month, defaults={
                "rate": rate, "source": serializer.validated_data["source"],
                "issued_on": serializer.validated_data.get("issued_on"), "updated_by": request.user,
            })
    result = table_response(request.user)
    result["imported"] = len(parsed)
    return Response(result)


@api_view(["PATCH"])
@permission_classes([IsEmployeeOrAdmin])
def selic_rate_detail(request, year, month):
    if request.user.role != "admin":
        return Response({"detail": "Somente administradores podem editar a tabela Selic."}, status=status.HTTP_403_FORBIDDEN)
    if year < 1995 or year > 2100 or month < 1 or month > 12:
        return Response({"detail": "Informe ano entre 1995 e 2100 e mês entre 1 e 12."}, status=400)
    serializer = UpdateInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    rate, _ = SelicAccumulatedRate.objects.update_or_create(year=year, month=month, defaults={
        **serializer.validated_data, "updated_by": request.user,
    })
    return Response(row_data(rate))
