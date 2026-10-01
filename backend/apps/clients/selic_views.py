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
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from rest_framework import serializers, status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.identity.permissions import IsEmployeeOrAdmin
from common.services.google_drive import drive_service
from .models import SelicAccumulatedRate, SelicAccumulatedReport
from .selic_parser import SelicPdfError, parse_accumulated_pdf, parse_monthly_pdf

MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
TOKEN_SALT = "selic-import-preview-v1"


def is_admin(request):
    return request.user.role == "admin"


def report_data(report, user):
    rows = list(report.rates.select_related("corrected_by"))
    return {"report_type": report.report_type, "id": str(report.public_id), "reference_year": report.reference_year, "reference_month": report.reference_month,
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
def selic_table(request, report_type="accumulated"):
    reports = SelicAccumulatedReport.objects.filter(report_type=report_type).select_related("imported_by")
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
def selic_import_preview(request, report_type="accumulated"):
    if not is_admin(request):
        return Response({"detail": "Somente administradores podem importar relatórios."}, status=403)
    upload = request.FILES.get("file")
    if not upload or upload.content_type != "application/pdf" or upload.size > 10 * 1024 * 1024:
        return Response({"file": ["Selecione um PDF de até 10 MB."]}, status=400)
    content = upload.read()
    try:
        parsed = parse_monthly_pdf(content) if report_type == "monthly" else parse_accumulated_pdf(content)
        parsed["report_type"] = report_type
    except SelicPdfError as exc:
        return Response({"file": [str(exc)]}, status=400)
    if SelicAccumulatedReport.objects.filter(file_sha256=parsed["sha256"]).exists():
        return Response({"file": ["Este PDF já foi importado."]}, status=409)
    latest = SelicAccumulatedReport.objects.filter(report_type=report_type, reference_year=parsed["reference_year"], reference_month=parsed["reference_month"]).first()
    changed = [] if not latest else [key for key in sorted(set(latest.extracted_data) | set(parsed["values"])) if latest.extracted_data.get(key) != parsed["values"].get(key)]
    payload = {"parsed": parsed, "filename": upload.name, "content": base64.b64encode(content).decode("ascii"), "user": request.user.pk}
    return Response({"token": signing.dumps(payload, salt=TOKEN_SALT, compress=True),
                     "preview": {**{k: v for k, v in parsed.items() if k != "values"}, "changed_count": len(changed),
                                 "changed_periods": changed[:20], "next_version": (latest.version + 1) if latest else 1}})


class ConfirmInput(serializers.Serializer):
    token = serializers.CharField()


@api_view(["POST"])
@permission_classes([IsEmployeeOrAdmin])
def selic_import_confirm(request, report_type="accumulated"):
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
    token_type = parsed.get("report_type", "accumulated")
    if token_type == "selic_accumulated_payment":
        token_type = "accumulated"
    if token_type != report_type:
        return Response({"detail": "A prévia pertence a outro tipo de relatório Selic."}, status=400)
    if SelicAccumulatedReport.objects.filter(file_sha256=parsed["sha256"]).exists():
        return Response({"token": ["Este PDF já foi importado."]}, status=409)
    content = base64.b64decode(payload["content"])
    drive_ready = all(getattr(settings, name, None) for name in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"))
    try:
        file_id = drive_service.upload_stream(io.BytesIO(content), payload["filename"], "selic", "application/pdf") if drive_ready else ""
    except HttpError as exc:
        if getattr(exc, "resp", None) is not None and exc.resp.status == 404:
            message = "A pasta Selic não foi encontrada ou a conta Google do Miele não possui acesso a ela. Confira GDRIVE_SELIC_FOLDER_ID e o compartilhamento da pasta."
        else:
            message = "O Google Drive recusou o envio do PDF. Confira a pasta e as credenciais do Miele."
        return Response({"detail": message}, status=status.HTTP_502_BAD_GATEWAY)
    except RefreshError:
        return Response({"detail": "A autorização do Google Drive expirou. Renove o refresh token configurado no backend."}, status=status.HTTP_502_BAD_GATEWAY)
    except Exception:
        return Response({"detail": "Não foi possível armazenar o PDF no Google Drive. Confira a configuração da pasta Selic."}, status=status.HTTP_502_BAD_GATEWAY)
    with transaction.atomic():
        same = SelicAccumulatedReport.objects.select_for_update().filter(report_type=report_type, reference_year=parsed["reference_year"], reference_month=parsed["reference_month"])
        version = (same.aggregate(value=Max("version"))["value"] or 0) + 1; same.update(is_active=False)
        report = SelicAccumulatedReport.objects.create(report_type=report_type, reference_year=parsed["reference_year"], reference_month=parsed["reference_month"], version=version,
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
def selic_rate_detail(request, report_id, year, month, report_type="accumulated"):
    if not is_admin(request):
        return Response({"detail": "Somente administradores podem corrigir taxas."}, status=403)
    source = get_object_or_404(SelicAccumulatedReport, public_id=report_id, report_type=report_type)
    if f"{year}-{month:02d}" not in source.extracted_data:
        return Response({"detail": "Só é possível corrigir uma competência existente no relatório."}, status=400)
    serializer = CorrectionInput(data=request.data); serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        peers = SelicAccumulatedReport.objects.select_for_update().filter(report_type=report_type, reference_year=source.reference_year, reference_month=source.reference_month)
        version = (peers.aggregate(value=Max("version"))["value"] or 0) + 1; peers.update(is_active=False)
        snapshot = dict(source.extracted_data); key = f"{year}-{month:02d}"; snapshot[key] = str(serializer.validated_data["rate"])
        report = SelicAccumulatedReport.objects.create(report_type=report_type, reference_year=source.reference_year, reference_month=source.reference_month, version=version,
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
def selic_original(request, report_id, report_type="accumulated"):
    report = get_object_or_404(SelicAccumulatedReport, public_id=report_id, report_type=report_type)
    if report.original_content:
        return FileResponse(io.BytesIO(bytes(report.original_content)), content_type="application/pdf", filename=report.original_file_name)
    if not report.original_file_id:
        return Response({"detail": "O arquivo original da carga inicial não está armazenado."}, status=404)
    return FileResponse(drive_service.download_stream(report.original_file_id), content_type="application/pdf", filename=report.original_file_name)
