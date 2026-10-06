"""Portable, bounded package format for OCR performed outside the web service."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import uuid
import zipfile
from datetime import datetime
from pathlib import PurePosixPath

from .import_parser import parse_pages, valid_cnpj


SCHEMA = "miele.perdcomp.ocr-package"
SCHEMA_VERSION = 1
EXTRACTION_SCHEMA = "miele.perdcomp.ocr-extraction"
MANIFEST_NAME = "miele-ocr-manifest.json"
MAX_PACKAGE_FILES = 49
MAX_PDF_SIZE = 10 * 1024 * 1024
MAX_PDF_TOTAL = 50 * 1024 * 1024
MAX_EXTRACTION_SIZE = 2 * 1024 * 1024
MAX_EXTRACTION_TOTAL = 10 * 1024 * 1024
MAX_PACKAGE_MEMBERS = 100
MAX_PAGES_PER_FILE = 100
MAX_TEXT_PER_PAGE = 50_000
MAX_TEXT_PER_FILE = 1_000_000


class OcrPackageProblem(ValueError):
    pass


def digits(value):
    return re.sub(r"\D", "", str(value or ""))


def _safe_path(value):
    value = str(value or "").replace("\\", "/")
    path = PurePosixPath(value)
    return bool(value) and not (
        path.is_absolute()
        or ".." in path.parts
        or ":" in value
        or any(not part or part in (".", "..") for part in path.parts)
    )


def _read_member(archive, info, limit, label):
    if info.file_size > limit or info.file_size / max(info.compress_size, 1) > 500:
        raise OcrPackageProblem(f"{label} excede o limite permitido.")
    with archive.open(info) as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise OcrPackageProblem(f"{label} excede o limite permitido.")
    return content


def _json_object(raw, label):
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OcrPackageProblem(f"{label} não contém JSON UTF-8 válido.") from None
    if not isinstance(value, dict):
        raise OcrPackageProblem(f"{label} deve conter um objeto JSON.")
    return value


def _validated_extraction(value, expected_sha):
    if value.get("schema") != EXTRACTION_SCHEMA or value.get("schema_version") != SCHEMA_VERSION:
        raise OcrPackageProblem("Versão da extração OCR não suportada.")
    if value.get("sha256") != expected_sha:
        raise OcrPackageProblem("A extração local não corresponde ao hash declarado.")
    pages = value.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES_PER_FILE:
        raise OcrPackageProblem("Quantidade de páginas da extração local inválida.")
    if any(not isinstance(page, str) or len(page) > MAX_TEXT_PER_PAGE for page in pages):
        raise OcrPackageProblem("Uma página da extração local excede o limite de texto.")
    if sum(len(page) for page in pages) > MAX_TEXT_PER_FILE:
        raise OcrPackageProblem("A extração local excede o limite total de texto.")
    source = value.get("text_source")
    if source not in ("native", "ocr"):
        raise OcrPackageProblem("Origem do texto local inválida.")
    ocr = value.get("ocr")
    if source == "ocr":
        if not isinstance(ocr, dict):
            raise OcrPackageProblem("Metadados do OCR local ausentes.")
        engine = ocr.get("engine")
        confidence = ocr.get("confidence")
        page_count = ocr.get("pages")
        if not isinstance(engine, str) or not engine[:100]:
            raise OcrPackageProblem("Motor do OCR local não informado.")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise OcrPackageProblem("Confiança do OCR local inválida.")
        if not isinstance(page_count, int) or not 0 <= page_count <= len(pages):
            raise OcrPackageProblem("Quantidade de páginas OCR inválida.")
        recognized = ocr.get("recognized_pages")
        minimum = ocr.get("minimum_confidence")
        if not isinstance(recognized, int) or not 0 <= recognized <= page_count:
            raise OcrPackageProblem("Quantidade de páginas reconhecidas pelo OCR inválida.")
        if minimum is not None and (not isinstance(minimum, (int, float)) or not 0 <= minimum <= 1):
            raise OcrPackageProblem("Confiança mínima do OCR local inválida.")
    elif ocr is not None:
        raise OcrPackageProblem("PDF com texto nativo não deve declarar execução de OCR.")
    return pages, source, ocr


def is_ocr_package(archive):
    return MANIFEST_NAME in {info.filename.replace("\\", "/") for info in archive.infolist() if not info.is_dir()}


def load_ocr_package(archive):
    """Validate a package and return normal importer entries without rerunning OCR."""
    infos = archive.infolist()
    if len(infos) > MAX_PACKAGE_MEMBERS:
        raise OcrPackageProblem("Pacote OCR excede 100 itens internos.")
    by_name = {}
    for info in infos:
        name = info.filename.replace("\\", "/")
        if not _safe_path(name) or stat.S_ISLNK(info.external_attr >> 16) or bool(info.flag_bits & 1):
            raise OcrPackageProblem("Pacote OCR contém item inseguro ou criptografado.")
        if info.is_dir():
            continue
        if name in by_name:
            raise OcrPackageProblem("Pacote OCR contém nomes internos duplicados.")
        by_name[name] = info
    manifest_info = by_name.get(MANIFEST_NAME)
    if manifest_info is None:
        raise OcrPackageProblem("Manifesto do pacote OCR ausente.")
    manifest = _json_object(
        _read_member(archive, manifest_info, MAX_EXTRACTION_SIZE, "Manifesto OCR"),
        "Manifesto OCR",
    )
    if manifest.get("schema") != SCHEMA or manifest.get("schema_version") != SCHEMA_VERSION:
        raise OcrPackageProblem("Versão do pacote OCR não suportada.")
    try:
        package_id = str(uuid.UUID(str(manifest.get("package_id"))))
    except (ValueError, TypeError, AttributeError):
        raise OcrPackageProblem("Identificador do pacote OCR inválido.") from None
    client_cnpj = digits(manifest.get("client_cnpj"))
    if not valid_cnpj(client_cnpj):
        raise OcrPackageProblem("CNPJ do pacote OCR inválido.")
    tool = manifest.get("tool")
    if not isinstance(tool, dict) or tool.get("name") != "miele-ocr-local":
        raise OcrPackageProblem("Ferramenta de origem do pacote OCR não reconhecida.")
    tool_version = str(tool.get("version") or "")[:40]
    if not re.fullmatch(r"[0-9A-Za-z._-]{1,40}", tool_version):
        raise OcrPackageProblem("Versão da ferramenta OCR inválida.")
    tool_parser_version = str(tool.get("parser_version") or "")[:80]
    if not re.fullmatch(r"[0-9A-Za-z._-]{1,80}", tool_parser_version):
        raise OcrPackageProblem("Versão do parser local inválida.")
    created_at = str(manifest.get("created_at") or "")[:64]
    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        raise OcrPackageProblem("Data de criação do pacote OCR inválida.") from None
    if parsed_created_at.tzinfo is None:
        raise OcrPackageProblem("Data de criação do pacote OCR deve conter fuso horário.")
    declared = manifest.get("files")
    if not isinstance(declared, list) or not 1 <= len(declared) <= MAX_PACKAGE_FILES:
        raise OcrPackageProblem("Pacote OCR deve conter de 1 a 49 PDFs.")

    allowed = {MANIFEST_NAME}
    entries = []
    pdf_total = 0
    extraction_total = 0
    seen_hashes = set()
    for item in declared:
        if not isinstance(item, dict):
            raise OcrPackageProblem("Item inválido no manifesto OCR.")
        pdf_path = str(item.get("path") or "").replace("\\", "/")
        extraction_path = str(item.get("extraction_path") or "").replace("\\", "/")
        expected_sha = str(item.get("sha256") or "").lower()
        original_name = str(item.get("original_name") or "")
        if not (_safe_path(pdf_path) and pdf_path.startswith("originais/") and pdf_path.lower().endswith(".pdf")):
            raise OcrPackageProblem("Caminho de PDF inválido no pacote OCR.")
        if not (_safe_path(extraction_path) and extraction_path.startswith("extracoes/") and extraction_path.lower().endswith(".json")):
            raise OcrPackageProblem("Caminho de extração inválido no pacote OCR.")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or expected_sha in seen_hashes:
            raise OcrPackageProblem("Hash ausente, inválido ou duplicado no pacote OCR.")
        if (not original_name or len(original_name) > 255 or "/" in original_name or "\\" in original_name
                or not original_name.lower().endswith(".pdf")
                or re.search(r"[\x00-\x1f\x7f]", original_name)):
            raise OcrPackageProblem("Nome original inválido no pacote OCR.")
        pdf_info = by_name.get(pdf_path)
        extraction_info = by_name.get(extraction_path)
        if pdf_info is None or extraction_info is None:
            raise OcrPackageProblem("PDF ou extração declarada não foi encontrada no pacote OCR.")
        raw = _read_member(archive, pdf_info, MAX_PDF_SIZE, "PDF do pacote OCR")
        pdf_total += len(raw)
        if pdf_total > MAX_PDF_TOTAL:
            raise OcrPackageProblem("Pacote OCR excede 50 MB de PDFs.")
        if not raw.startswith(b"%PDF-") or hashlib.sha256(raw).hexdigest() != expected_sha:
            raise OcrPackageProblem("PDF do pacote OCR não corresponde ao hash declarado.")
        if item.get("size") != len(raw):
            raise OcrPackageProblem("Tamanho do PDF diverge do manifesto OCR.")
        extraction_raw = _read_member(archive, extraction_info, MAX_EXTRACTION_SIZE, "Extração OCR")
        extraction_total += len(extraction_raw)
        if extraction_total > MAX_EXTRACTION_TOTAL:
            raise OcrPackageProblem("Pacote OCR excede 10 MB de texto extraído.")
        extraction_data = _json_object(extraction_raw, "Extração OCR")
        pages, source, ocr = _validated_extraction(extraction_data, expected_sha)
        if item.get("pages") != len(pages):
            raise OcrPackageProblem("Quantidade de páginas diverge do manifesto OCR.")
        parsed = parse_pages(pages)
        parsed["text_source"] = source
        parsed["ocr"] = ocr
        parsed["local_package"] = {
            "package_id": package_id,
            "tool": "miele-ocr-local",
            "tool_version": tool_version,
            "parser_version": tool_parser_version,
            "created_at": created_at,
            "extraction_source": source,
            "source_sha256": expected_sha,
        }
        if digits(parsed.get("fields", {}).get("cnpj")) != client_cnpj:
            raise OcrPackageProblem("O CNPJ extraído não corresponde ao cliente declarado no pacote OCR.")
        if source == "ocr" and parsed.get("status") == "no_text":
            parsed["issues"] = ["OCR local não reconheceu texto suficiente para uma importação segura."]
        entries.append({
            "name": original_name,
            "raw": raw,
            "error": None,
            "sha256": expected_sha,
            "size": len(raw),
            "pages": len(pages),
            "extraction": parsed,
            "package_prepared": True,
        })
        allowed.update((pdf_path, extraction_path))
        seen_hashes.add(expected_sha)
    extras = set(by_name) - allowed
    if extras:
        raise OcrPackageProblem("Pacote OCR contém arquivos não declarados no manifesto.")
    return entries
