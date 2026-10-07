"""Bounded ingestion without extraction to user-controlled filesystem paths."""
import hashlib
import io
import json
import re
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import time
import zipfile

from .import_parser import parse_pages
from .ocr_package import OcrPackageProblem, is_ocr_package, load_ocr_package

MAX_FILES = 100
MAX_FILE = 10 * 1024 * 1024
MAX_TOTAL = 50 * 1024 * 1024
MAX_OCR_PAGES = 20
MAX_PROCESSING_SECONDS = 170


class ImportProblem(ValueError):
    pass


def extract_pdf(raw, ocr_page_budget=MAX_OCR_PAGES, timeout=165):
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("import_pdf_worker.py")), str(max(0, ocr_page_budget))],
            input=raw, capture_output=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode or len(result.stdout) > 6000000:
            return {"error": (
                "Este PDF em imagem excedeu os recursos seguros do servidor. "
                "Prepare-o com o Miele OCR Local e envie o pacote .miele.zip "
                "pelo mesmo botão Importar."
            )}
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        return {"error": (
            "Este PDF em imagem excedeu o tempo seguro do servidor. Prepare-o "
            "com o Miele OCR Local e envie o pacote .miele.zip pelo mesmo botão "
            "Importar."
        )}


def ingest(uploads, ocr_quota=None, process=True):
    if not uploads or len(uploads) > MAX_FILES:
        raise ImportProblem("Selecione de 1 a 100 arquivos.")
    entries, total = [], 0

    def append(name, raw, error=None, prepared=None):
        nonlocal total
        total += len(raw)
        if len(entries) >= MAX_FILES or total > MAX_TOTAL:
            raise ImportProblem("Lote excede 100 arquivos ou 50 MB descompactados.")
        name = name.replace("\\", "/").split("/")[-1][:255]
        name = re.sub(r"[\x00-\x1f\x7f]", "", name)
        entries.append({"name": name, "raw": raw, "error": error, "prepared": prepared})

    input_size = 0
    for upload in uploads:
        limit = MAX_TOTAL if upload.name.lower().endswith(".zip") else MAX_FILE
        raw = upload.read(limit + 1)
        input_size += len(raw)
        if len(raw) > limit or input_size > MAX_TOTAL:
            raise ImportProblem("Limite: PDF 10 MB; ZIP/lote 50 MB.")
        if not upload.name.lower().endswith(".zip"):
            append(upload.name, raw)
            continue
        if not raw.startswith(b"PK\x03\x04"):
            raise ImportProblem("Assinatura do ZIP inválida.")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_FILES:
                    raise ImportProblem("ZIP excede 100 itens.")
                if is_ocr_package(archive):
                    try:
                        for prepared in load_ocr_package(archive):
                            append(prepared["name"], prepared["raw"], prepared=prepared)
                    except OcrPackageProblem as exc:
                        raise ImportProblem(str(exc)) from None
                    continue
                for info in infos:
                    path = PurePosixPath(info.filename.replace("\\", "/"))
                    unsafe = (path.is_absolute() or ".." in path.parts or ":" in str(path)
                              or stat.S_ISLNK(info.external_attr >> 16) or bool(info.flag_bits & 1))
                    if unsafe:
                        append(info.filename, b"", "Item ZIP inseguro ou criptografado — bloqueado.")
                        continue
                    if info.is_dir():
                        continue
                    if info.file_size > MAX_FILE or info.file_size / max(info.compress_size, 1) > 100:
                        append(info.filename, b"", "Item ZIP excede o tamanho ou a compressão permitida.")
                        continue
                    if total + info.file_size > MAX_TOTAL:
                        raise ImportProblem("ZIP excede 50 MB descompactados.")
                    with archive.open(info) as stream:
                        content = stream.read(MAX_FILE + 1)
                    if len(content) > MAX_FILE:
                        raise ImportProblem("Item ZIP excede 10 MB.")
                    append(info.filename, content)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
            raise ImportProblem("ZIP corrompido, protegido ou não suportado.") from None
    pages, ocr_pages, cache, start = 0, 0, {}, time.monotonic()
    for index, entry in enumerate(entries):
        entry["index"] = index
        raw = entry["raw"]
        prepared = entry.pop("prepared", None)
        entry["sha256"] = prepared["sha256"] if prepared else hashlib.sha256(raw).hexdigest()
        entry["size"] = prepared["size"] if prepared else len(raw)
        entry["pages"] = prepared["pages"] if prepared else 0
        suffix = Path(entry["name"]).suffix.lower()
        if suffix != ".pdf":
            entry["error"] = entry["error"] or ("Backup DBK não suportado." if suffix == ".dbk" else "Arquivo não PDF — ignorado.")
        elif not raw.startswith(b"%PDF-"):
            entry["error"] = entry["error"] or "Assinatura de PDF inválida."
        if not process:
            continue
        if not entry["error"]:
            if prepared:
                entry["extraction"] = prepared["extraction"]
                pages += entry["pages"]
                if pages > 500:
                    raise ImportProblem("Lote excede 500 páginas. Divida-o em lotes menores.")
                continue
            remaining = MAX_PROCESSING_SECONDS - (time.monotonic() - start)
            if entry["sha256"] in cache:
                pass
            elif remaining <= 0:
                cache[entry["sha256"]] = (0, None, (
                    "Este arquivo não foi processado porque o lote atingiu o tempo "
                    "seguro. Divida os arquivos restantes em um novo lote."
                ))
            else:
                ocr_budget = MAX_OCR_PAGES - ocr_pages
                if ocr_quota is not None:
                    ocr_budget = min(ocr_budget, ocr_quota.remaining)
                extracted = extract_pdf(
                    raw,
                    ocr_budget,
                    timeout=min(165, remaining),
                )
                if "error" in extracted:
                    error = extracted["error"]
                    if extracted.get("ocr_quota_exceeded") and ocr_quota is not None:
                        error = ocr_quota.exceeded_message(extracted.get("ocr_required_pages"))
                        entry["ocr_quota_exceeded"] = True
                    cache[entry["sha256"]] = (0, None, error)
                else:
                    executed_ocr_pages = int((extracted.get("ocr") or {}).get("pages", 0))
                    if ocr_quota is not None and executed_ocr_pages:
                        ocr_quota.record(executed_ocr_pages)
                    parsed = parse_pages(extracted["pages"])
                    parsed["text_source"] = extracted.get("text_source", "native")
                    parsed["ocr"] = extracted.get("ocr")
                    if parsed["text_source"] == "ocr" and parsed["status"] == "no_text":
                        parsed["issues"] = ["OCR não reconheceu texto suficiente para uma importação segura."]
                    cache[entry["sha256"]] = (len(extracted["pages"]), parsed, None)
                    ocr_pages += executed_ocr_pages
            entry["pages"], entry["extraction"], entry["error"] = cache[entry["sha256"]]
            pages += entry["pages"]
            if pages > 500:
                raise ImportProblem("Lote excede 500 páginas. Divida-o em lotes menores.")
        if entry["error"]:
            entry["extraction"] = {"status": "rejected", "issues": [entry["error"]], "fields": {}, "kind": "unknown", "evidence": {}, "relations": [], "debts": [], "components": []}
    return entries
