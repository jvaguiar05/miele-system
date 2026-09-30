from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("clients", "0012_version_selic_reports")]
    operations = [migrations.AddField(model_name="selicaccumulatedreport", name="original_content", field=models.BinaryField(blank=True, editable=False, null=True))]
