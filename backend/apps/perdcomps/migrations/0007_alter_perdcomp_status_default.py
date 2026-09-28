from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("perdcomps", "0006_alter_perdcomp_competencia_and_more")]
    operations = [
        migrations.AlterField(
            model_name="perdcomp",
            name="status",
            field=models.CharField(
                choices=[
                    ("RASCUNHO", "Rascunho"), ("TRANSMITIDO", "Transmitido"),
                    ("EM_PROCESSAMENTO", "Em Processamento"), ("DEFERIDO", "Deferido"),
                    ("INDEFERIDO", "Indeferido"), ("PARCIALMENTE_DEFERIDO", "Parcialmente Deferido"),
                    ("CANCELADO", "Cancelado"), ("VENCIDO", "Vencido"),
                ],
                default="TRANSMITIDO", help_text="Status atual do PER/DCOMP", max_length=30,
            ),
        ),
    ]
