from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("clients", "0013_selic_report_local_original")]
    operations = [
        migrations.AddField(model_name="selicaccumulatedreport", name="report_type", field=models.CharField(max_length=16, default="accumulated", choices=[("accumulated", "Acumulada"), ("monthly", "Mensal")])),
        migrations.RemoveConstraint(model_name="selicaccumulatedreport", name="unique_selic_report_version"),
        migrations.AddConstraint(model_name="selicaccumulatedreport", constraint=models.UniqueConstraint(fields=["report_type", "reference_year", "reference_month", "version"], name="unique_selic_kind_version")),
    ]
