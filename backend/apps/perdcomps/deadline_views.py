import csv
import io
from django.http import HttpResponse
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.identity.permissions import IsEmployeeOrAdmin
from apps.clients.dashboard_operations import build_operations_data
from .deadlines import automatic_due_date, alert_start, OPEN_STATUSES


class PreviewInput(serializers.Serializer):
    transmission = serializers.DateField()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def preview(request):
    query = PreviewInput(data=request.query_params)
    query.is_valid(raise_exception=True)
    due = automatic_due_date(query.validated_data["transmission"])
    return Response({"due": due.isoformat(), "alert_start": alert_start(due).isoformat()})


class ReportInput(serializers.Serializer):
    client = serializers.CharField(required=False, allow_blank=True, max_length=255)
    status = serializers.ChoiceField(choices=sorted(OPEN_STATUSES), required=False)
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    include_overdue = serializers.BooleanField(default=False)
    export = serializers.ChoiceField(choices=["csv"], required=False)

    def validate(self, attrs):
        if attrs.get("start") and attrs.get("end") and attrs["start"] > attrs["end"]:
            raise serializers.ValidationError("A data inicial deve ser anterior à final.")
        return attrs


def safe_cell(value):
    value = str(value if value is not None else "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def upcoming_report(request):
    query = ReportInput(data=request.query_params)
    query.is_valid(raise_exception=True)
    filters = query.validated_data
    dashboard = build_operations_data()
    rows = dashboard["alerts"]
    if not filters["include_overdue"]:
        rows = [r for r in rows if r["severity"] != "overdue"]
    term = filters.get("client", "").casefold()
    rows = [r for r in rows if term in (r["client"] + " " + r["cnpj"]).casefold()]
    if filters.get("status"):
        rows = [r for r in rows if r["status"] == filters["status"]]
    if filters.get("start"):
        rows = [r for r in rows if r["due"] >= filters["start"].isoformat()]
    if filters.get("end"):
        rows = [r for r in rows if r["due"] <= filters["end"].isoformat()]
    if filters.get("export") == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["Cliente", "CNPJ", "Processo", "Status", "Vencimento", "Dias úteis restantes", "Saldo cadastrado", "Situação"])
        for row in rows:
            writer.writerow([safe_cell(row[key]) for key in ("client", "cnpj", "number", "status_label", "due", "business_days", "balance", "severity")])
        response = HttpResponse("\ufeff" + stream.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="proximos-vencimentos.csv"'
        return response
    return Response({"results": rows, "count": len(rows), "reference_date": dashboard["reference_date"]})
