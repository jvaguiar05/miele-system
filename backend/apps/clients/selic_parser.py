import hashlib
import io
import re
import unicodedata
from datetime import datetime

from pypdf import PdfReader

MONTHS_PT = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


class SelicPdfError(ValueError):
    pass


def parse_monthly_pdf(content):
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text(extraction_mode="layout") for page in reader.pages]
    except Exception as exc:
        raise SelicPdfError("O arquivo não é um PDF legível.") from exc
    text = _plain("\n".join(pages))
    if "sicalc" not in text or "taxa de juros selic mensal" not in text or "acumulada para pagamento" in text:
        raise SelicPdfError("Selecione o relatório de Selic mensal do Sicalc nesta aba.")
    dates = set(re.findall(r"emitido\s+em\s+(\d{2}/\d{2}/\d{4})", text))
    if len(dates) != 1:
        raise SelicPdfError("A emissão do relatório está ausente ou divergente.")
    try:
        issued = datetime.strptime(dates.pop(), "%d/%m/%Y").date()
    except ValueError as exc:
        raise SelicPdfError("Data de emissão inválida.") from exc
    values = {}
    for page in pages:
        lines = page.splitlines()
        headers = [line for line in lines if re.fullmatch(r"\s*(?:(?:19|20)\d{2}\s*)+", line)]
        if len(headers) != 1:
            raise SelicPdfError("Não foi possível identificar as colunas de anos em todas as páginas.")
        columns = [(int(m.group()), (m.start() + m.end()) / 2) for m in re.finditer(r"(?:19|20)\d{2}", headers[0])]
        seen_months = set()
        for line in lines:
            label = re.match(r"\s*([a-z]+)\b", _plain(line))
            if not label or label.group(1) not in MONTHS_PT:
                continue
            month = MONTHS_PT[label.group(1)]
            if month in seen_months:
                raise SelicPdfError("Mês repetido na mesma página.")
            seen_months.add(month)
            for match in re.finditer(r"\d+,\d{2}(?!\d)", line):
                center = (match.start() + match.end()) / 2
                year, position = min(columns, key=lambda item: abs(item[1] - center))
                if abs(position - center) > 4:
                    raise SelicPdfError("Alinhamento ambíguo entre taxa e ano.")
                key = f"{year}-{month:02d}"
                if key in values:
                    raise SelicPdfError("Competência repetida no PDF.")
                values[key] = match.group().replace(",", ".")
        if len(seen_months) != 12:
            raise SelicPdfError("Página incompleta: confira os doze meses da tabela.")
    if not values:
        raise SelicPdfError("Nenhuma taxa mensal encontrada.")
    last = max(values)
    year, month = map(int, last.split("-"))
    expected = {f"{y}-{m:02d}" for y in range(1995, year + 1) for m in range(1, 13)
                if "1995-02" <= f"{y}-{m:02d}" <= last}
    if set(values) != expected or (year, month) >= (issued.year, issued.month):
        raise SelicPdfError("Tabela mensal incompleta ou com competência ainda não encerrada na emissão.")
    return {"report_type": "monthly", "reference_year": year, "reference_month": month,
            "issued_on": issued.isoformat(), "source": "Sicalc - Sistema de Cálculo de Acréscimos Legais",
            "page_count": len(pages), "value_count": len(values), "blank_count": 1 + 12 - month,
            "values": values, "sha256": hashlib.sha256(content).hexdigest()}


def _plain(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(c) != "Mn")


def parse_accumulated_pdf(content):
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text(extraction_mode="layout") for page in reader.pages]
    except Exception as exc:
        raise SelicPdfError("O arquivo não é um PDF legível.") from exc
    plain = _plain("\n".join(pages))
    if "sicalc" not in plain or "taxa de juros selic acumulada para pagamento" not in plain:
        raise SelicPdfError("O PDF não foi reconhecido como relatório acumulado do Sicalc.")
    reference = re.search(r"ate\s+(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})", plain)
    issued = re.search(r"emitido\s+em\s+(\d{2}/\d{2}/\d{4})", plain)
    if not reference or not issued:
        raise SelicPdfError("Não foi possível identificar a competência de pagamento e a emissão.")
    ref_month, ref_year = MONTHS_PT[reference.group(1)], int(reference.group(2))
    values = {}
    for page in pages:
        lines = page.splitlines()
        header = next((line for line in lines if len(re.findall(r"(?:19|20)\d{2}", line)) >= 2), "")
        years = [int(item) for item in re.findall(r"(?:19|20)\d{2}", header)]
        month = 0
        for line in lines[lines.index(header) + 1:] if header else []:
            raw_values = re.findall(r"\d{1,3},\d{2}", line)
            if not raw_values:
                continue
            month += 1
            target_years = years[-len(raw_values):] if years and years[0] == 1995 and month == 1 else years[:len(raw_values)]
            for year, raw in zip(target_years, raw_values):
                values[f"{year}-{month:02d}"] = raw.replace(",", ".")
    expected = (ref_year - 1995) * 12 + ref_month - 1
    if len(values) != expected or values.get(f"{ref_year}-{ref_month:02d}") is None:
        raise SelicPdfError(f"Tabela incompleta ou ambígua: esperados {expected} valores e encontrados {len(values)}.")
    return {"report_type": "selic_accumulated_payment", "reference_year": ref_year, "reference_month": ref_month,
            "issued_on": datetime.strptime(issued.group(1), "%d/%m/%Y").date().isoformat(),
            "source": "Sicalc - Sistema de Cálculo de Acréscimos Legais", "page_count": len(pages),
            "value_count": len(values), "blank_count": 1 + (12 - ref_month), "values": values,
            "sha256": hashlib.sha256(content).hexdigest()}
