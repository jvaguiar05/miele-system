from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("perdcomps", "0011_importedfile_database_released_at_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="OcrDailyUsage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("usage_date", models.DateField(unique=True)),
                ("global_pages", models.PositiveIntegerField(default=0)),
                ("per_user", models.JSONField(default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "perdcomp_ocr_daily_usage"},
        ),
    ]
