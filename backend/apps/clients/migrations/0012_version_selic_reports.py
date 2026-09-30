import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def move_initial_rates(apps, schema_editor):
    Report = apps.get_model("clients", "SelicAccumulatedReport")
    Rate = apps.get_model("clients", "SelicAccumulatedRate")
    rates = list(Rate.objects.order_by("year", "month"))
    snapshot = {f"{item.year}-{item.month:02d}": f"{item.rate:.2f}" for item in rates}
    report = Report.objects.create(
        reference_year=2026, reference_month=9, version=1, issued_on="2026-09-25",
        source="Sicalc - Sistema de Cálculo de Acréscimos Legais", original_file_name="Selic Acumulada.pdf",
        file_sha256="initial-official-sicalc-september-2026".ljust(64, "0"), extracted_data=snapshot,
        value_count=len(rates), blank_count=4,
    )
    Rate.objects.update(report=report)


class Migration(migrations.Migration):
    dependencies = [("clients", "0011_selic_accumulated_rate"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="SelicAccumulatedReport", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
            ("reference_year", models.PositiveSmallIntegerField()), ("reference_month", models.PositiveSmallIntegerField()),
            ("version", models.PositiveSmallIntegerField(default=1)), ("issued_on", models.DateField()),
            ("source", models.CharField(default="Sicalc - Receita Federal", max_length=255)),
            ("original_file_name", models.CharField(max_length=255)), ("original_file_id", models.CharField(blank=True, max_length=255)),
            ("file_sha256", models.CharField(max_length=64, unique=True)), ("extracted_data", models.JSONField(default=dict)),
            ("value_count", models.PositiveIntegerField(default=0)), ("blank_count", models.PositiveIntegerField(default=0)),
            ("is_active", models.BooleanField(default=True)), ("imported_at", models.DateTimeField(auto_now_add=True)),
            ("imported_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="imported_selic_reports", to=settings.AUTH_USER_MODEL)),
        ], options={"db_table": "selic_accumulated_reports", "ordering": ["-reference_year", "-reference_month", "-version"]}),
        migrations.AddConstraint(model_name="selicaccumulatedreport", constraint=models.UniqueConstraint(fields=("reference_year", "reference_month", "version"), name="unique_selic_report_version")),
        migrations.RemoveConstraint(model_name="selicaccumulatedrate", name="unique_selic_accumulated_month"),
        migrations.AddField(model_name="selicaccumulatedrate", name="report", field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="rates", to="clients.selicaccumulatedreport")),
        migrations.AddField(model_name="selicaccumulatedrate", name="correction_reason", field=models.TextField(blank=True)),
        migrations.AddField(model_name="selicaccumulatedrate", name="corrected_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="selicaccumulatedrate", name="corrected_by", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="corrected_selic_rates", to=settings.AUTH_USER_MODEL)),
        migrations.RunPython(move_initial_rates, migrations.RunPython.noop),
        migrations.RemoveField(model_name="selicaccumulatedrate", name="source"),
        migrations.RemoveField(model_name="selicaccumulatedrate", name="issued_on"),
        migrations.RemoveField(model_name="selicaccumulatedrate", name="updated_at"),
        migrations.RemoveField(model_name="selicaccumulatedrate", name="updated_by"),
        migrations.AlterField(model_name="selicaccumulatedrate", name="report", field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rates", to="clients.selicaccumulatedreport")),
        migrations.AlterModelOptions(name="selicaccumulatedrate", options={"ordering": ["report", "year", "month"]}),
        migrations.AddConstraint(model_name="selicaccumulatedrate", constraint=models.UniqueConstraint(fields=("report", "year", "month"), name="unique_selic_report_month")),
    ]
