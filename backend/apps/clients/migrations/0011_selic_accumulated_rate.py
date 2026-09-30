from datetime import date
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


DATA = """1995;;440,11;437,51;433,25;429,00;424,96;420,94;417,10;413,78;410,69;407,81;405,03
1996;402,45;400,10;397,88;395,81;393,80;391,82;389,89;387,92;386,02;384,16;382,36;380,56
1997;378,83;377,16;375,52;373,86;372,28;370,67;369,07;367,48;365,89;364,22;361,18;358,21
1998;355,54;353,41;351,21;349,50;347,87;346,27;344,57;343,09;340,60;337,66;335,03;332,63
1999;330,45;328,07;324,74;322,39;320,37;318,70;317,04;315,47;313,98;312,60;311,21;309,61
2000;308,15;306,70;305,25;303,95;302,46;301,07;299,76;298,35;297,13;295,84;294,62;293,42
2001;292,15;291,13;289,87;288,68;287,34;286,07;284,57;282,97;281,65;280,12;278,73;277,34
2002;275,81;274,56;273,19;271,71;270,30;268,97;267,43;265,99;264,61;262,96;261,42;259,68
2003;257,71;255,88;254,10;252,23;250,26;248,40;246,32;244,55;242,87;241,23;239,89;238,52
2004;237,25;236,17;234,79;233,61;232,38;231,15;229,86;228,57;227,32;226,11;224,86;223,38
2005;222,00;220,78;219,25;217,84;216,34;214,75;213,24;211,58;210,08;208,67;207,29;205,82
2006;204,39;203,24;201,82;200,74;199,46;198,28;197,11;195,85;194,79;193,70;192,68;191,69
2007;190,61;189,74;188,69;187,75;186,72;185,81;184,84;183,85;183,05;182,12;181,28;180,44
2008;179,51;178,71;177,87;176,97;176,09;175,13;174,06;173,04;171,94;170,76;169,74;168,62
2009;167,57;166,71;165,74;164,90;164,13;163,37;162,58;161,89;161,20;160,51;159,85;159,12
2010;158,46;157,87;157,11;156,44;155,69;154,90;154,04;153,15;152,30;151,49;150,68;149,75
2011;148,89;148,05;147,13;146,29;145,30;144,34;143,37;142,30;141,36;140,48;139,62;138,71
2012;137,82;137,07;136,25;135,54;134,80;134,16;133,48;132,79;132,25;131,64;131,09;130,54
2013;129,94;129,45;128,90;128,29;127,69;127,08;126,36;125,65;124,94;124,13;123,41;122,62
2014;121,77;120,98;120,21;119,39;118,52;117,70;116,75;115,88;114,97;114,02;113,18;112,22
2015;111,28;110,46;109,42;108,47;107,48;106,41;105,23;104,12;103,01;101,90;100,84;99,68
2016;98,62;97,62;96,46;95,40;94,29;93,13;92,02;90,80;89,69;88,64;87,60;86,48
2017;85,39;84,52;83,47;82,68;81,75;80,94;80,14;79,34;78,70;78,06;77,49;76,95
2018;76,37;75,90;75,37;74,85;74,33;73,81;73,27;72,70;72,23;71,69;71,20;70,71
2019;70,17;69,68;69,21;68,69;68,15;67,68;67,11;66,61;66,15;65,67;65,29;64,92
2020;64,54;64,25;63,91;63,63;63,39;63,18;62,99;62,83;62,67;62,51;62,36;62,20
2021;62,05;61,92;61,72;61,51;61,24;60,93;60,57;60,14;59,70;59,21;58,62;57,85
2022;57,12;56,36;55,43;54,60;53,57;52,55;51,52;50,35;49,28;48,26;47,24;46,12
2023;45,00;44,08;42,91;41,99;40,87;39,80;38,73;37,59;36,62;35,62;34,70;33,81
2024;32,84;32,04;31,21;30,32;29,49;28,70;27,79;26,92;26,08;25,15;24,36;23,43
2025;22,42;21,43;20,47;19,41;18,27;17,17;15,89;14,73;13,51;12,23;11,18;9,96
2026;8,80;7,80;6,59;5,50;4,43;3,31;2,09;1,00;0,00;;;"""


def seed_rates(apps, schema_editor):
    Rate = apps.get_model("clients", "SelicAccumulatedRate")
    for line in DATA.splitlines():
        cells = line.split(";")
        year = int(cells[0])
        for month, raw in enumerate(cells[1:], 1):
            if raw:
                Rate.objects.update_or_create(year=year, month=month, defaults={
                    "rate": Decimal(raw.replace(",", ".")),
                    "source": "Sicalc - Sistema de Cálculo de Acréscimos Legais",
                    "issued_on": date(2026, 9, 25),
                })


class Migration(migrations.Migration):
    dependencies = [("clients", "0010_clientcontract"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="SelicAccumulatedRate", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("year", models.PositiveSmallIntegerField()), ("month", models.PositiveSmallIntegerField()),
            ("rate", models.DecimalField(decimal_places=2, max_digits=8)),
            ("source", models.CharField(default="Sicalc - Receita Federal", max_length=255)),
            ("issued_on", models.DateField(blank=True, null=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_selic_rates", to=settings.AUTH_USER_MODEL)),
        ], options={"db_table": "selic_accumulated_rates", "ordering": ["year", "month"]}),
        migrations.AddConstraint(model_name="selicaccumulatedrate", constraint=models.UniqueConstraint(fields=("year", "month"), name="unique_selic_accumulated_month")),
        migrations.AddConstraint(model_name="selicaccumulatedrate", constraint=models.CheckConstraint(condition=models.Q(("month__gte", 1), ("month__lte", 12)), name="selic_valid_month")),
        migrations.AddConstraint(model_name="selicaccumulatedrate", constraint=models.CheckConstraint(condition=models.Q(("rate__gte", 0)), name="selic_nonnegative_rate")),
        migrations.RunPython(seed_rates, migrations.RunPython.noop),
    ]
