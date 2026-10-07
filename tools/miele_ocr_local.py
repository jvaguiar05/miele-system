"""Build auditable Miele OCR packages without using the Render web service CPU."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
BACKEND = REPOSITORY / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from apps.perdcomps.import_files import extract_pdf  # noqa: E402
from apps.perdcomps.import_parser import VERSION as PARSER_VERSION  # noqa: E402
from apps.perdcomps.import_parser import digits, parse_pages, valid_cnpj  # noqa: E402
from apps.perdcomps.ocr_package import (  # noqa: E402
    EXTRACTION_SCHEMA,
    MANIFEST_NAME,
    MAX_EXTRACTION_SIZE,
    MAX_EXTRACTION_TOTAL,
    MAX_PACKAGE_FILES,
    MAX_PDF_SIZE,
    SCHEMA,
    SCHEMA_VERSION,
    load_ocr_package,
)


TOOL_VERSION = "1.0.0"
PACKAGE_TARGET_BYTES = 45 * 1024 * 1024
PACKAGE_MAX_PAGES = 500
DEFAULT_OUTPUT = Path.home() / "Documents" / "Miele OCR"


def bounded_int(minimum, maximum):
    """Argparse validator with a compact help message."""
    def parse(value):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            raise argparse.ArgumentTypeError("informe um número inteiro") from None
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(
                f"informe um valor entre {minimum} e {maximum}"
            )
        return parsed

    return parse


def safe_name(value):
    value = Path(value).name
    value = re.sub(r"[\x00-\x1f\x7f]", "", value)
    value = re.sub(r"[^0-9A-Za-zÀ-ÿ._ -]+", "_", value).strip(" ._")
    return (value or "documento.pdf")[:180]


def collect_pdfs(inputs, output_root):
    found = {}
    output_root = output_root.resolve()
    for raw_input in inputs:
        source = Path(raw_input).expanduser().resolve()
        if not source.exists():
            raise ValueError(f"Caminho não encontrado: {source}")
        candidates = [source] if source.is_file() else source.rglob("*.pdf")
        for candidate in candidates:
            candidate = candidate.resolve()
            if candidate.suffix.lower() != ".pdf" or output_root in candidate.parents:
                continue
            found[str(candidate).lower()] = candidate
    return sorted(found.values(), key=lambda path: str(path).lower())


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def process_pdf(path, ocr_pages, timeout, staging):
    result = {"source": path, "name": safe_name(path.name), "status": "review", "issues": []}
    try:
        size = path.stat().st_size
        if size <= 0 or size > MAX_PDF_SIZE:
            raise ValueError("PDF vazio ou maior que 10 MB.")
        raw = path.read_bytes()
        if not raw.startswith(b"%PDF-"):
            raise ValueError("Assinatura de PDF inválida.")
        sha256 = hashlib.sha256(raw).hexdigest()
        extracted = extract_pdf(raw, ocr_page_budget=ocr_pages, timeout=timeout)
        if "error" in extracted:
            raise ValueError(extracted["error"])
        pages = extracted.get("pages")
        parsed = parse_pages(pages)
        source = extracted.get("text_source", "native")
        ocr = extracted.get("ocr")
        cnpj = digits(parsed.get("fields", {}).get("cnpj"))
        if not valid_cnpj(cnpj):
            raise ValueError("CNPJ titular não identificado com segurança.")
        extraction = {
            "schema": EXTRACTION_SCHEMA,
            "schema_version": 1,
            "sha256": sha256,
            "pages": pages,
            "text_source": source,
            "ocr": ocr,
        }
        encoded = json.dumps(extraction, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_EXTRACTION_SIZE:
            raise ValueError("Extração de texto excedeu 2 MB.")
        extraction_file = staging / f"{sha256}_{uuid.uuid4().hex}.json"
        extraction_file.write_bytes(encoded)
        result.update({
            "status": "ready" if parsed.get("status") == "ready" else "review",
            "issues": parsed.get("issues", []),
            "size": len(raw),
            "sha256": sha256,
            "pages": len(pages),
            "text_source": source,
            "ocr": ocr,
            "cnpj": cnpj,
            "protocol": digits(parsed.get("fields", {}).get("protocol")),
            "kind": parsed.get("kind", "unknown"),
            "extraction_file": extraction_file,
        })
    except (OSError, ValueError) as exc:
        result["issues"] = [str(exc)]
    return result


def chunks_for(files):
    chunk, size, pages, extraction_size = [], 0, 0, 0
    for item in sorted(files, key=lambda value: (value["protocol"], value["name"], value["sha256"])):
        item_extraction_size = item["extraction_file"].stat().st_size
        item_size = item["size"] + item_extraction_size
        if chunk and (
            len(chunk) >= MAX_PACKAGE_FILES
            or size + item_size > PACKAGE_TARGET_BYTES
            or pages + item["pages"] > PACKAGE_MAX_PAGES
            or extraction_size + item_extraction_size > MAX_EXTRACTION_TOTAL
        ):
            yield chunk
            chunk, size, pages, extraction_size = [], 0, 0, 0
        chunk.append(item)
        size += item_size
        pages += item["pages"]
        extraction_size += item_extraction_size
    if chunk:
        yield chunk


def write_package(destination, cnpj, part, files, created_at):
    package_id = str(uuid.uuid4())
    declared = []
    for index, item in enumerate(files, 1):
        if item["source"].stat().st_size != item["size"] or file_sha256(item["source"]) != item["sha256"]:
            raise ValueError(f"O PDF mudou durante o processamento: {item['name']}")
        internal_name = f"{index:03d}_{item['sha256'][:12]}_{safe_name(item['name'])}"
        pdf_path = f"originais/{internal_name}"
        extraction_path = f"extracoes/{item['sha256']}.json"
        declared.append({
            "original_name": item["name"],
            "path": pdf_path,
            "extraction_path": extraction_path,
            "sha256": item["sha256"],
            "size": item["size"],
            "pages": item["pages"],
        })
        item["package_pdf_path"] = pdf_path
        item["package_extraction_path"] = extraction_path
    manifest = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "package_id": package_id,
        "created_at": created_at,
        "client_cnpj": cnpj,
        "tool": {"name": "miele-ocr-local", "version": TOOL_VERSION, "parser_version": PARSER_VERSION},
        "files": declared,
    }
    path = destination / f"{cnpj}_parte_{part:03d}.miele.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        for item in files:
            archive.write(item["source"], item["package_pdf_path"])
            archive.write(item["extraction_file"], item["package_extraction_path"])
    try:
        with zipfile.ZipFile(path) as archive:
            validated = load_ocr_package(archive)
        if len(validated) != len(files):
            raise ValueError("A validação final retornou uma quantidade divergente de PDFs.")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path, package_id


def write_reports(run_root, results, packages, created_at):
    rows = []
    for item in results:
        rows.append({
            "arquivo": item["name"],
            "status": item["status"],
            "cnpj": item.get("cnpj", ""),
            "protocolo": item.get("protocol", ""),
            "paginas": item.get("pages", 0),
            "origem_texto": item.get("text_source", ""),
            "confianca_ocr": (item.get("ocr") or {}).get("confidence", ""),
            "sha256": item.get("sha256", ""),
            "observacoes": " | ".join(item.get("issues", [])),
        })
    with (run_root / "relatorio.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["arquivo", "status"])
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "tool": "miele-ocr-local",
        "tool_version": TOOL_VERSION,
        "created_at": created_at,
        "files": len(results),
        "ready": sum(item["status"] == "ready" for item in results),
        "review": sum(item["status"] == "review" for item in results),
        "duplicates": sum(item["status"] == "duplicate" for item in results),
        "ocr_files": sum(item.get("text_source") == "ocr" for item in results),
        "packages": packages,
    }
    (run_root / "resumo.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Prepara lotes OCR auditáveis para importação no Miele.")
    parser.add_argument("inputs", nargs="+", help="PDF(s) ou pasta(s) de entrada.")
    parser.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT),
                        help=f"Pasta de saída (padrão: {DEFAULT_OUTPUT}).")
    parser.add_argument("-w", "--workers", type=bounded_int(1, 4), default=1,
                        metavar="1-4", help="Processos simultâneos (padrão: 1).")
    parser.add_argument("--ocr-pages", type=bounded_int(1, 100), default=100,
                        metavar="1-100", help="Máximo de páginas OCR por PDF (padrão: 100).")
    parser.add_argument("--timeout", type=bounded_int(60, 1800), default=900,
                        metavar="60-1800", help="Tempo máximo por PDF, em segundos (padrão: 900).")
    args = parser.parse_args(argv)

    missing = [name for name in ("pypdf", "pypdfium2", "rapidocr", "onnxruntime")
               if importlib.util.find_spec(name) is None]
    if missing:
        raise SystemExit("Dependências locais ausentes: " + ", ".join(missing))

    output = Path(args.output).expanduser().resolve()
    created = datetime.now(timezone.utc)
    run_root = output / created.strftime("miele_ocr_%Y%m%d_%H%M%S")
    package_root = run_root / "pacotes"
    package_root.mkdir(parents=True, exist_ok=False)
    staging = run_root / ".work"
    staging.mkdir()
    paths = collect_pdfs(args.inputs, run_root)
    if not paths:
        raise SystemExit("Nenhum PDF foi encontrado.")
    print(f"Encontrados {len(paths)} PDF(s). OCR local iniciado com {args.workers} processo(s).")
    results = []
    package_report = []
    try:
        unique_paths = []
        prescan_hashes = {}
        for path in paths:
            try:
                sha256 = file_sha256(path)
            except OSError as exc:
                results.append({"source": path, "name": safe_name(path.name), "status": "review",
                                "issues": [f"Não foi possível ler o arquivo: {exc}"]})
                continue
            if sha256 in prescan_hashes:
                results.append({
                    "source": path,
                    "name": safe_name(path.name),
                    "status": "duplicate",
                    "sha256": sha256,
                    "issues": [f"Duplicado de {prescan_hashes[sha256].name}; OCR não repetido."],
                })
                print(f"[PRÉVIA] DUPLICATE: {path.name}")
                continue
            prescan_hashes[sha256] = path
            unique_paths.append(path)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_pdf, path, args.ocr_pages, args.timeout, staging): path for path in unique_paths}
            for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
                item = future.result()
                results.append(item)
                print(f"[{completed}/{len(unique_paths)}] {item['status'].upper()}: {item['name']}")

        seen_hashes = set()
        for item in sorted(results, key=lambda value: str(value["source"]).lower()):
            sha256 = item.get("sha256")
            if sha256 and sha256 in seen_hashes:
                item["status"] = "duplicate"
                item["issues"] = ["Arquivo duplicado pelo SHA-256; somente a primeira cópia foi empacotada."]
            elif sha256:
                seen_hashes.add(sha256)
        grouped = {}
        for item in results:
            if item.get("cnpj") and item["status"] != "duplicate":
                grouped.setdefault(item["cnpj"], []).append(item)
        for cnpj, files in sorted(grouped.items()):
            for part, chunk in enumerate(chunks_for(files), 1):
                path, package_id = write_package(package_root, cnpj, part, chunk, created.isoformat())
                package_report.append({
                    "file": path.name,
                    "package_id": package_id,
                    "client_cnpj": cnpj,
                    "documents": len(chunk),
                    "bytes": path.stat().st_size,
                })
        write_reports(run_root, sorted(results, key=lambda item: item["name"].lower()), package_report, created.isoformat())
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    ready = sum(item["status"] == "ready" for item in results)
    review = sum(item["status"] == "review" for item in results)
    duplicates = sum(item["status"] == "duplicate" for item in results)
    omitted = sum(not item.get("cnpj") and item["status"] != "duplicate" for item in results)
    print("\nResumo do Miele OCR Local")
    print(f"  PDFs encontrados: {len(results)} | Prontos: {ready} | Revisão: {review}")
    print(f"  Duplicados: {duplicates} | Sem pacote: {omitted} | Pacotes: {len(package_report)}")
    print(f"  Relatórios: {run_root}")
    if package_report:
        print(f"  Pacotes para importar: {package_root}")
        return 0
    print("Nenhum pacote foi criado. Consulte relatorio.csv antes de tentar novamente.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
