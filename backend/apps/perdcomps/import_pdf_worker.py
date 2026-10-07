"""Isolated, bounded PDF extraction with local OCR fallback.

Receives PDF bytes on stdin and emits JSON only. OCR is used solely on pages
without enough native text; originals never leave this process/machine.
"""
import io
import json
import os
import sys


NATIVE_TEXT_MIN = 20
DEFAULT_OCR_SCALE = 1.5


def _layout_text(result, width):
    """Rebuild a conservative text layout from OCR boxes."""
    if result is None or not getattr(result, "txts", None):
        return "", []
    boxes, texts, scores = result.boxes, result.txts, result.scores
    rows = []
    for box, text, score in zip(boxes, texts, scores):
        if not str(text).strip():
            continue
        left = min(float(point[0]) for point in box)
        top = min(float(point[1]) for point in box)
        bottom = max(float(point[1]) for point in box)
        rows.append({"left": left, "top": top, "bottom": bottom,
                     "height": max(1.0, bottom - top), "text": str(text).strip(), "score": float(score)})
    rows.sort(key=lambda item: (item["top"], item["left"]))
    grouped = []
    for item in rows:
        center = (item["top"] + item["bottom"]) / 2
        line = next((candidate for candidate in reversed(grouped[-3:])
                     if abs(candidate["center"] - center) <= max(candidate["height"], item["height"]) * 0.55), None)
        if line is None:
            line = {"center": center, "height": item["height"], "items": []}
            grouped.append(line)
        line["items"].append(item)
        count = len(line["items"])
        line["center"] = ((line["center"] * (count - 1)) + center) / count
        line["height"] = max(line["height"], item["height"])
    output, confidences = [], []
    for line in sorted(grouped, key=lambda item: item["center"]):
        parts, cursor = [], 0
        for item in sorted(line["items"], key=lambda value: value["left"]):
            column = max(0, min(180, round(item["left"] / max(float(width), 1.0) * 160)))
            spaces = max(1 if parts else 0, column - cursor)
            parts.append(" " * spaces + item["text"])
            cursor = column + len(item["text"])
            confidences.append(item["score"])
        output.append("".join(parts).rstrip())
    return "\n".join(output), confidences


def _ocr_pages(raw, pages, indexes):
    try:
        import numpy as np
        import pypdfium2 as pdfium
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise ValueError("OCR indisponível neste ambiente; instale as dependências de OCR do projeto.") from exc
    try:
        scale = float(os.getenv("PERDCOMP_OCR_SCALE", DEFAULT_OCR_SCALE))
    except ValueError:
        scale = DEFAULT_OCR_SCALE
    scale = min(2.25, max(1.25, scale))
    engine = RapidOCR()
    document = pdfium.PdfDocument(raw)
    confidences = []
    try:
        for index in indexes:
            page = document[index]
            width, height = page.get_size()
            if width <= 0 or height <= 0 or (width * scale) * (height * scale) > 8_000_000:
                page.close()
                raise ValueError("Página excede o limite seguro de renderização para OCR.")
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil().convert("RGB")
            try:
                text, scores = _layout_text(engine(np.asarray(image)), image.width)
                pages[index] = text
                confidences.extend(scores)
            finally:
                image.close()
                bitmap.close()
                page.close()
    finally:
        document.close()
    return confidences


def main():
    try:
        if sys.platform != "win32":
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (150, 150))
        from pypdf import PdfReader
        raw = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024 or not raw.startswith(b"%PDF-"):
            raise ValueError("Assinatura ou tamanho de PDF inválido.")
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted:
            raise ValueError("PDF protegido ou criptografado — importação bloqueada.")
        if len(reader.pages) > 100:
            raise ValueError("PDF excede o limite de 100 páginas.")
        pages = []
        for page in reader.pages:
            text = (page.extract_text(extraction_mode="layout") or "") if page.get("/Contents") is not None else ""
            if len(text) > 50000 or sum(map(len, pages)) + len(text) > 1000000:
                raise ValueError("PDF excede o limite de conteúdo extraível.")
            pages.append(text)
        needs_ocr = [index for index, text in enumerate(pages) if len(text.strip()) < NATIVE_TEXT_MIN]
        try:
            ocr_budget = max(0, int(sys.argv[1])) if len(sys.argv) > 1 else 20
        except ValueError:
            ocr_budget = 20
        ocr_enabled = os.getenv("PERDCOMP_OCR_ENABLED", "true").lower() not in ("0", "false", "no")
        if needs_ocr and ocr_enabled:
            if len(needs_ocr) > ocr_budget:
                print(json.dumps({
                    "error": "O PDF requer mais páginas OCR do que o saldo online disponível.",
                    "ocr_quota_exceeded": True,
                    "ocr_required_pages": len(needs_ocr),
                }))
                return
            scores = _ocr_pages(raw, pages, needs_ocr)
            if any(len(page) > 50000 for page in pages) or sum(map(len, pages)) > 1000000:
                raise ValueError("OCR excedeu o limite de conteúdo extraível.")
            recognized = sum(bool(pages[index].strip()) for index in needs_ocr)
            confidence = round(sum(scores) / len(scores), 4) if scores else 0.0
            print(json.dumps({"pages": pages, "text_source": "ocr", "ocr": {
                "engine": "rapidocr-3.9", "pages": len(needs_ocr), "recognized_pages": recognized,
                "confidence": confidence, "minimum_confidence": round(min(scores), 4) if scores else 0.0,
            }}))
        else:
            print(json.dumps({"pages": pages, "text_source": "native", "ocr": None}))
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
    except Exception:
        print(json.dumps({"error": "PDF corrompido ou ilegível."}))


if __name__ == "__main__":
    main()
