"""Local-only corpus check. Outputs metadata/issues, never personal PDF text."""
import json
from collections import Counter
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.perdcomps.import_files import ingest


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("directory")
        parser.add_argument("--summary-only", action="store_true")

    def handle(self, directory, **options):
        counts = Counter()
        for path in sorted(Path(directory).iterdir()):
            if not path.is_file():
                continue
            entry = ingest([SimpleUploadedFile(path.name, path.read_bytes())])[0]
            extraction = entry["extraction"]
            counts[extraction["status"]] += 1
            if options["summary_only"] and not (extraction.get("layout") == "web83" and extraction["status"] != "ready"):
                continue
            self.stdout.write(json.dumps({"file": path.name, "pages": entry["pages"], "kind": extraction["kind"],
                "status": extraction["status"], "issues": extraction["issues"], "debts": len(extraction["debts"]),
                "components": len(extraction["components"])}, ensure_ascii=True))
        self.stdout.write(json.dumps(dict(counts)))
