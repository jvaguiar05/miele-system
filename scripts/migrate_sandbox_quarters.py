"""Back up the explicitly named local database, then apply quarter migrations."""
from pathlib import Path
from datetime import datetime
import os
import sqlite3
import sys

root = Path(__file__).resolve().parent.parent
database = root / ".sandbox" / "miele-sandbox.sqlite3"
if not database.is_file():
    raise SystemExit("Banco sandbox nao encontrado; nenhuma alteracao realizada.")
backup = database.with_name("backup-before-quarters-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".sqlite3")
with sqlite3.connect(database.as_uri() + "?mode=rw", uri=True) as source:
    with sqlite3.connect(backup) as target:
        source.backup(target)
        if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise SystemExit("Falha ao verificar backup; migracao cancelada.")
print("Backup verificado:", backup)
sys.path.insert(0, str(root / "backend"))
os.environ["DJANGO_SETTINGS_MODULE"] = "core.settings.sandbox"
import django
django.setup()
from django.conf import settings
if Path(settings.DATABASES["default"]["NAME"]).resolve() != database.resolve():
    raise SystemExit("Destino inesperado; migracao cancelada.")
from django.core.management import call_command
call_command("migrate", interactive=False)
