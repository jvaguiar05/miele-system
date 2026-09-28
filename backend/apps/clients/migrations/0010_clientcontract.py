import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("clients", "0009_quartersnapshot"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="ClientContract",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("percentage", models.DecimalField(decimal_places=4, max_digits=7)),
                ("starts_on", models.DateField()),
                ("ends_on", models.DateField(blank=True, null=True)),
                ("reference", models.CharField(blank=True, max_length=120)),
                ("notes", models.TextField(blank=True)),
                ("billing_evolution_requested", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("client", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contracts", to="clients.client")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_client_contracts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "client_contracts", "ordering": ["-starts_on", "-id"]},
        ),
        migrations.AddIndex(model_name="clientcontract", index=models.Index(fields=["client", "starts_on", "ends_on"], name="client_cont_client__bd934d_idx")),
    ]
