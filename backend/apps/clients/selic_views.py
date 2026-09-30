import base64
import csv
import io
from decimal import Decimal

from django.core import signing
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.identity.permissions import IsEmployeeOrAdmin
from common.services.google_drive import drive_service
from .models import SelicAccumulatedRate, SelicAccumulatedReport
from .selic_parser import SelicPdfError, parse_accumulated_pdf

MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
TOKEN_SALT = "selic-import-preview-v1"


def is_admin(request):
    return request.user.role == "admin"


def report_data(report, user):
    rows = list(report.rates.select_related("corrected_by"))
    return {"id": str(report.public_id), "reference_year": report.reference_year, "reference_month": report.reference_month,
            "version": report.version, "issued_on": report.issued_on.isoformat() if hasattr(report.issued_on, "isoformat") else str(report.issued_on), "source": report.source,
            "file_name": report.original_file_name, "has_original": bool(report.original_file_id or report.original_content),
            "value_count": report.value_count, "blank_count": report.blank_count, "imported_at": report.imported_at.isoformat(),
            "imported_by": (report.imported_by.get_full_name() or report.imported_by.username) if report.imported_by else "Carga inicial",
            "values": {f"{r.year}-{r.month:02d}": f"{r.rate:.2f}" for r in rows},
            "corrections": [{"period": f"{r.year}-{r.month:02d}", "reason": r.correction_reason,
                             "by": (r.corrected_by.get_full_name() or r.corrected_by.username) if r.corrected_by else None,
                             "at": r.corrected_at.isoformat() if r.corrected_at else None} for r in rows if r.correction_reason],
            "can_edit": user.role == "admin"}


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def selic_table(request):
    reports = SelicAccumulatedReport.objects.select_related("imported_by")
    report = get_object_or_404(reports, public_id=request.query_params["report"]) if request.query_params.get("report") else reports.filter(is_active=True).first()
    if not report:
        return Response({"active": None, "versions": [], "can_edit": is_admin(request), "monthly_rates_available": False})
    if request.query_params.get("export") == "csv":
        stream = io.StringIO(); writer = csv.writer(stream, delimiter=";"); writer.writerow(["ano", *MONTHS])
        values = report_data(report, request.user)["values"]
        for year in range(1995, report.reference_year + 1):
            writer.writerow([year, *[values.get(f"{year}-{month:02d}", "").replace(".", ",") for month in range(1, 13)]])
        response = HttpResponse("\ufeff" + stream.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="selic-{report.reference_year}-{report.reference_month:02d}-v{report.version}.csv"'
        return response
    versions = [{"id": str(item.public_id), "reference_year": item.reference_year, "reference_month": item.reference_month,
                 "version": item.version, "issued_on": item.issued_on.isoformat(), "active": item.is_active} for item in reports]
    return Response({"active": report_data(report, request.user), "versions": versions, "can_edit": is_admin(request), "monthly_rates_available": False})


@api_view(["POST"])
@parser_classes([MultiPartParser])
@permission_classes([IsEmployeeOrAdmin])
def selic_import_preview(request):
    if not is_admin(request):
        return Response({"detail": "Somente administradores podem importar relatórios."}, status=403)
    upload = request.FILES.get("file")
    if not upload or upload.content_type != "application/pdf" or upload.size > 10 * 1024 * 1024:
        return Response({"file": ["Selecione um PDF de até 10 MB."]}, status=400)
    content = upload.read()
    try:
        parsed = parse_accumulated_pdf(content)
    except SelicPdfError as exc:
        return Response({"file": [str(exc)]}, status=400)
    if SelicAccumulatedReport.objects.filter(file_sha256=parsed["sha256"]).exists():
        return Response({"file": ["Este PDF já foi importado."]}, status=409)
    latest = SelicAccumulatedReport.objects.filter(reference_year=parsed["reference_year"], reference_month=parsed["reference_month"]).first()
    changed = [] if not latest else [key for key in sorted(set(latest.extracted_data) | set(parsed["values"])) if latest.extracted_data.get(key) != parsed["values"].get(key)]
    payload = {"parsed": parsed, "filename": upload.name, "content": base64.b64encode(content).decode("ascii"), "user": request.user.pk}
    return Response({"token": signing.dumps(payload, salt=TOKEN_SALT, compress=True),
                     "preview": {**{k: v for k, v in parsed.items() if k != "values"}, "changed_count": len(changed),
                                 "changed_periods": changed[:20], "next_version": (latest.version + 1) if latest else 1}})


class ConfirmInput(serializers.Serializer):
    token = serializers.CharField()


@api_view(["POST"])
@permission_classes([IsEmployeeOrAdmin])
def selic_import_confirm(request):
    if not is_admin(request):
        return Response({"detail": "Somente administradores podem confirmar importações."}, status=403)
    serializer = ConfirmInput(data=request.data); serializer.is_valid(raise_exception=True)
    try:
        payload = signing.loads(serializer.validated_data["token"], salt=TOKEN_SALT, max_age=900)
    except signing.BadSignature:
        return Response({"token": ["A prévia expirou ou foi alterada. Gere uma nova prévia."]}, status=400)
    if payload.get("user") != request.user.pk:
        return Response({"token": ["A prévia pertence a outro usuário."]}, status=403)
    parsed = payload["parsed"]
    if SelicAccumulatedReport.objects.filter(file_sha256=parsed["sha256"]).exists():
        return Response({"token": ["Este PDF já foi importado."]}, status=409)
    content = base64.b64decode(payload["content"])
    drive_ready = all(getattr(settings, name, None) for name in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"))
    file_id = drive_service.upload_stream(io.BytesIO(content), payload["filename"], "selic", "application/pdf") if drive_ready else ""
    with transaction.atomic():
        same = SelicAccumulatedReport.objects.select_for_update().filter(reference_year=parsed["reference_year"], reference_month=parsed["reference_month"])
        version = (same.aggregate(value=Max("version"))["value"] or 0) + 1; same.update(is_active=False)
        report = SelicAccumulatedReport.objects.create(reference_year=parsed["reference_year"], reference_month=parsed["reference_month"], version=version,
            issued_on=parsed["issued_on"], source=parsed["source"], original_file_name=payload["filename"], original_file_id=file_id,
            original_content=None if drive_ready else content, file_sha256=parsed["sha256"], extracted_data=parsed["values"],
            value_count=parsed["value_count"], blank_count=parsed["blank_count"], imported_by=request.user)
        SelicAccumulatedRate.objects.bulk_create([SelicAccumulatedRate(report=report, year=int(key[:4]), month=int(key[5:]), rate=Decimal(value)) for key, value in parsed["values"].items()])
    return Response(report_data(report, request.user), status=status.HTTP_201_CREATED)


class CorrectionInput(serializers.Serializer):
    rate = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("1000"))
    reason = serializers.CharField(min_length=5, max_length=1000)


@api_view(["PATCH"])
@permission_classes([IsEmployeeOrAdmin])
def selic_rate_detail(request, report_id, year, month):
    if not is_admin(request):
        return Response({"detail": "Somente administradores podem corrigir taxas."}, status=403)
    source = get_object_or_404(SelicAccumulatedReport, public_id=report_id)
    serializer = CorrectionInput(data=request.data); serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        peers = SelicAccumulatedReport.objects.select_for_update().filter(reference_year=source.reference_year, reference_month=source.reference_month)
        version = (peers.aggregate(value=Max("version"))["value"] or 0) + 1; peers.update(is_active=False)
        snapshot = dict(source.extracted_data); key = f"{year}-{month:02d}"; snapshot[key] = str(serializer.validated_data["rate"])
        report = SelicAccumulatedReport.objects.create(reference_year=source.reference_year, reference_month=source.reference_month, version=version,
            issued_on=source.issued_on, source=source.source + " (correção manual)", original_file_name=source.original_file_name,
            original_file_id=source.original_file_id, original_content=source.original_content,
            file_sha256=f"manual-{source.public_id}-{version}".ljust(64, "0")[:64], extracted_data=snapshot,
            value_count=len(snapshot), blank_count=source.blank_count, imported_by=request.user)
        SelicAccumulatedRate.objects.bulk_create([SelicAccumulatedRate(report=report, year=int(item[:4]), month=int(item[5:]), rate=Decimal(value),
            correction_reason=serializer.validated_data["reason"] if item == key else "", corrected_by=request.user if item == key else None,
            corrected_at=timezone.now() if item == key else None) for item, value in snapshot.items()])
    return Response(report_data(report, request.user))


@api_view(["GET"])
@permission_classes([IsEmployeeOrAdmin])
def selic_original(request, report_id):
    report = get_object_or_404(SelicAccumulatedReport, public_id=report_id)
    if report.original_content:
        return FileResponse(io.BytesIO(bytes(report.original_content)), content_type="application/pdf", filename=report.original_file_name)
    if not report.original_file_id:
        return Response({"detail": "O arquivo original da carga inicial não está armazenado."}, status=404)
    return FileResponse(drive_service.download_stream(report.original_file_id), content_type="application/pdf", filename=report.original_file_name)
