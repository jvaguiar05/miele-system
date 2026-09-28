import uuid
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("clients", "0008_alter_client_client_status_and_more")]
    operations = [migrations.CreateModel(
        name="QuarterSnapshot",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
            ("year", models.PositiveSmallIntegerField()),
            ("quarter", models.PositiveSmallIntegerField()),
            ("kind", models.CharField(choices=[("position", "Posição parcial"), ("closing", "Fechamento")], max_length=10)),
            ("captured_at", models.DateTimeField(default=django.utils.timezone.now)),
            ("captured_by", models.CharField(max_length=255)),
            ("note", models.TextField(blank=True)),
            ("payload", models.JSONField()),
        ],
        options={"ordering": ["-captured_at", "-id"], "constraints": [models.UniqueConstraint(fields=("year", "quarter"), condition=models.Q(kind="closing"), name="one_closing_per_quarter")]},
    )]
