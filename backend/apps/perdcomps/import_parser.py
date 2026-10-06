"""Conservative native-text parser. No filename inference, OCR or financial posting."""
import re
import unicodedata
from datetime import datetime
from decimal import Decimal

VERSION = "web83-documentary-3-layouts"
PROTOCOL = r"\d{5}\.\d{5}\.\d{6}\.\d\.\d\.\d{2}-\d{4}"
CNPJ = r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"
MONEY = r"(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}"


def digits(value):
    return re.sub(r"\D", "", str(value or ""))


def fold(value):
    return "".join(c for c in unicodedata.normalize("NFD", value) if not unicodedata.combining(c)).lower()


def valid_cnpj(value):
    n = digits(value)
    if len(n) != 14 or len(set(n)) == 1:
        return False
    for length in (12, 13):
        weights = list(range(length - 7, 1, -1)) + list(range(9, 1, -1))
        remainder = sum(int(x) * w for x, w in zip(n[:length], weights)) % 11
        if int(n[length]) != (0 if remainder < 2 else 11 - remainder):
            return False
    return True


def decimal(value):
    if not re.fullmatch(MONEY, value.strip()):
        raise ValueError("Valor monetário inválido")
    normalized = value.replace(".", "").replace(",", ".")
    if len(normalized.split(".")[0]) > 20:
        raise ValueError("Valor monetário excede a precisão suportada")
    return str(Decimal(normalized))


FIELDS = {
    "name": (r"Nome Empresarial", "text"),
    "control": (r"Número de Controle", "text"),
    "created_on": (r"Data de Criação", "date"),
    "transmitted_on": (r"Data de Transmissão", "date"),
    "nature": (r"Tipo de Crédito", "text"),
    "taxation": (r"Forma de Tributação no Período", "text"),
    "period_type": (r"Tipo (?:do|de) Período do Crédito", "text"),
    "year": (r"Ano", "year"),
    "quarter": (r"Trimestre", "text"),
    "month": (r"Mês", "text"),
    "period": (r"Período (?:de Apuração|do Crédito)", "text"),
    "judicial": (r"(?:Crédito )?Oriundo de Ação Judicial", "bool"),
    "successor": (r"Crédito de Sucedida", "bool"),
    "prior_process": (r"Informado em Processo Administrativo Anterior", "bool"),
    "other_document": (r"Informado em Outro PER/DCOMP", "bool"),
    "process": (r"(?:Número|Nº) do Processo(?: Administrativo)?", "text"),
    "credit_holder": (r"CNPJ do Estabelecimento Detentor do Crédito", "text"),
    "initial_credit": (r"Valor Original do Crédito Inicial", "money"),
    "delivery_credit": (r"Crédito Original na Data de Entrega", "money"),
    "updated_credit": (r"Crédito Atualizado", "money"),
    "declared_selic": (r"Selic Acumulada", "money"),
    "eligible_credit": (r"Crédito Passível de Ressarcimento", "money"),
    "requested": (r"Valor do Pedido(?: de (?:Ressarcimento|Restituição|Reembolso))?", "money"),
    "used": (r"Total do Crédito Original Utilizado neste Documento", "money"),
    "declared_balance": (r"Saldo do Crédito Original", "money"),
    "total_debts": (r"Total dos Débitos deste Documento", "money"),
    "component_total": (r"Valor do Crédito Apurado", "money"),
    "deductions": (r"Valor das Deduções ou Descontos", "money"),
    "previous_use": (r"Valor Utilizado em Dcomps Anteriores", "money"),
}
DEBT_FIELDS = {
    "holder": (r"CNPJ do Detentor do Débito", "text"),
    "group": (r"Grupo de Tributo", "text"),
    "revenue": (r"Código da Receita/Denominação", "text"),
    "period": (r"Período de Apuração", "text"),
    "frequency": (r"Periodicidade", "text"),
    "due_on": (r"Data de Vencimento do Tributo/Quota", "date"),
    "principal": (r"Principal", "money"), "fine": (r"Multa", "money"),
    "interest": (r"Juros", "money"), "total": (r"Total", "money"),
    "dctf_receipt": (r"Número do Recibo de Transmissão DCTFWeb", "text"),
    "dctf_date": (r"Data de Transmissão DCTFWeb", "date"),
    "dctf_category": (r"Categoria DCTFWeb", "text"),
    "dctf_period": (r"Período Apuração DCTFWeb", "text"),
    "controlled_process": (r"Débito Controlado em Processo", "bool"),
    "process": (r"(?:Número|Nº) do Processo(?: Administrativo)?", "text"),
}
COMPONENT_FIELDS = {
    "code_description": (r"Código do Crédito", "text"),
    "assessed": (r"Valor do Crédito Apurado", "money"),
    "deductions": (r"Valor das Deduções ou Descontos", "money"),
    "previous_use": (r"Valor Utilizado em Dcomps Anteriores", "money"),
    "balance": (r"Saldo do Crédito", "money"),
    "used": (r"Valor do Crédito Utilizado Neste Documento", "money"),
}
RELATIONS = {
    "credit_origin": r"(?:N[º°o]|Número) do PER/DCOMP (?:Inicial|com Demonstrativo do Crédito)",
    "balance_reference": r"(?:Número|N[º°o]) do Último PER/DCOMP|Último PER/DCOMP",
    "rectifies": r"(?:Número|N[º°o]) do PER(?:/DCOMP)? Retificado",
    "cancels": r"(?:Número|N[º°o]) do PER/DCOMP Cancelado",
}


class Reader:
    def __init__(self, rows, output, prefix=""):
        self.rows, self.output, self.prefix = rows, output, prefix

    def record(self, key, value, row):
        self.output["evidence"][self.prefix + key] = {
            "page": row[0], "text": row[1].strip()[:1000], "value": value,
            "parser_version": VERSION,
        }
        return value

    def field(self, key, label, kind="text"):
        hits = []
        for row_index, row in enumerate(self.rows):
            match = re.match(r"^\s*(?:\d{4}\.\s*)?(?:" + label + r")\s*(?::\s*|\s+)(.+?)\s*$", row[1], re.I)
            if not match:
                continue
            raw = match[1].strip()
            evidence_row = row
            if raw.startswith("DCTFWeb") and "DCTFWeb" not in label:
                continue
            if kind == "text" and key in ("name", "nature", "revenue", "code_description"):
                for following in self.rows[row_index + 1:row_index + 3]:
                    indent = len(following[1]) - len(following[1].lstrip())
                    continuation = key == "nature" and re.fullmatch(r"(?:de )?\d{4}", following[1].strip())
                    if fold(following[1].strip()).startswith("dados do "):
                        break
                    if following[0] == row[0] and (indent >= max(match.start(1) - 3, 12) or continuation):
                        raw += " " + following[1].strip()
                        evidence_row = (row[0], evidence_row[1] + "\n" + following[1])
                    else:
                        break
            try:
                if kind == "money":
                    raw = decimal(raw.rstrip("%"))
                elif kind == "date":
                    raw = datetime.strptime(raw, "%d/%m/%Y").date().isoformat()
                elif kind == "year":
                    if not re.fullmatch(r"(?:19|20)\d{2}", raw):
                        raise ValueError()
                elif kind == "bool":
                    if fold(raw) not in ("sim", "nao"):
                        raise ValueError()
                    raw = fold(raw) == "sim"
                hits.append((raw, evidence_row))
            except (ValueError, ArithmeticError):
                self.output["issues"].append(f"Campo inválido: {self.prefix}{key}.")
        if not hits:
            return None
        if len({str(v) for v, _ in hits}) > 1:
            self.output["issues"].append(f"Valores conflitantes: {self.prefix}{key}.")
        return self.record(key, hits[0][0], hits[0][1])

    def fields(self, specs):
        return {key: self.field(key, *spec) for key, spec in specs.items()}


def parse_pages(pages):
    output = {"parser_version": VERSION, "kind": "unknown", "fields": {}, "debts": [],
              "components": [], "relations": [], "evidence": {}, "issues": [], "status": "review"}
    if not pages or sum(len(p.strip()) for p in pages) < 100:
        output.update(status="no_text", issues=["PDF sem texto nativo — importação manual necessária."])
        return output
    if any(len(p.strip()) < 20 for p in pages):
        output.update(status="no_text", issues=["PDF contém página sem texto nativo suficiente — importação manual necessária."])
        return output
    rows = [(page, line) for page, text in enumerate(pages, 1) for line in text.splitlines() if line.strip()]
    text = "\n".join(line for _, line in rows)
    if re.search(r"PER/DCOMP\s+7\.1", text, re.I):
        from .import_legacy_parser import classify_legacy
        return classify_legacy(output)
    reader = Reader(rows, output)
    receipt = "recibo de entrega" in fold(text)
    version = re.search(r"(?:PERDCOMP\s+|Versão:\s*)(8\.3\d)\b", text, re.I)
    if not version or (receipt and "PER/DCOMP WEB" not in text):
        output["issues"] = ["Leiaute não homologado — revisão manual necessária."]
        return output
    output.update(kind="receipt" if receipt else "demonstrative", layout="web83")
    fields = output["fields"]
    header_rows = []
    for row in rows:
        if re.match(r"\s*\d{3}\.\s*Débito\b", row[1]) or row[1].strip() == "CONSOLIDAÇÃO DOS CRÉDITOS":
            break
        header_rows.append(row)
    field_specs = dict(FIELDS)
    if receipt:
        field_specs["control"] = (
            r"Número de Controle(?: do (?:Pedido|Documento|Declaração) Retificador(?:a)?)?",
            "text",
        )
        field_specs["transmitted_on"] = (
            r"Data de Transmissão(?: do (?:Pedido|Documento|Declaração) Retificador(?:a)?)?",
            "date",
        )
    fields.update(Reader(header_rows, output).fields(field_specs))
    ver_row = next(row for row in rows if version[0] in row[1])
    fields["version"] = reader.record("version", version[1], ver_row)
    fields["program"] = reader.record("program", "PER/DCOMP Web", ver_row)
    if receipt:
        # Ownership is independent from protocol extraction, but remains
        # constrained to the declarant/solicitant block.
        identity = re.search(r"DADOS DO (?:DECLARANTE|SOLICITANTE)(.*?)DADOS D", text, re.S)
        match = re.search(r"CNPJ:\s*(" + CNPJ + ")", identity[1]) if identity else None
        if match:
            cnpj_row = next((r for r in rows if re.match(r"\s*CNPJ:", r[1])), None)
            if cnpj_row:
                fields["cnpj"] = reader.record("cnpj", match[1], cnpj_row)
    own = []
    for row in rows:
        if receipt:
            match = re.match(
                r"\s*Número (?:da Declaração|do Documento|do Pedido)(?: Retificador(?:a)?)?:\s*("
                + PROTOCOL + r")\s*$", row[1], re.I,
            )
            if match:
                own.append((None, match[1], row))
        else:
            match = re.match(r"\s*CNPJ\s+(" + CNPJ + r")\s+(" + PROTOCOL + r")\s*$", row[1])
            if match:
                own.append((match[1], match[2], row))
    if len({(cnpj, protocol) for cnpj, protocol, _ in own}) != 1:
        output["issues"].append("Protocolo próprio ausente ou PDF contém mais de um documento. Separe os PDFs.")
    elif own:
        cnpj, protocol, row = own[0]
        fields["protocol"] = reader.record("protocol", protocol, row)
        if not receipt:
            fields["cnpj"] = reader.record("cnpj", cnpj, row) if cnpj else None
    if receipt:
        heading = re.search(r"RECIBO DE ENTREGA (?:DA|DO)\s+(DECLARAÇÃO DE COMPENSAÇÃO|PEDIDO DE (?:RESSARCIMENTO|RESTITUIÇÃO|REEMBOLSO))", text, re.I)
        modality = heading[1] if heading else None
        fields["modality"] = reader.record("modality", fold(modality), next(r for r in rows if modality in r[1])) if modality else None
        kind = reader.field("revision_kind", "Tipo de Documento")
        fields["revision_kind"] = "original" if fold(kind or "") == "original" else "retificadora" if "retific" in fold(kind or "") else None
        hour = re.search(r"em \d{2}/\d{2}/\d{4} às (\d{2}:\d{2}:\d{2})", text)
        fields["transmitted_time"] = reader.record("transmitted_time", hour[1], next(r for r in rows if hour[0] in r[1])) if hour else None
    else:
        modality = reader.field("modality", "Tipo de Documento")
        fields["modality"] = fold(modality) if modality else None
        retifier = reader.field("revision_kind", "PER/DCOMP Retificador", "bool")
        fields["revision_kind"] = "retificadora" if retifier is True else "original" if retifier is False else None
    nature = fold(fields.get("nature") or "")
    fields["credit_tax"] = next((t for t in ("cofins", "pis", "ipi") if t in nature), None)
    if fields["credit_tax"]:
        output["evidence"]["credit_tax"] = {**output["evidence"]["nature"], "value": fields["credit_tax"]}
    for kind, label in RELATIONS.items():
        value = reader.field("relation." + kind, label)
        if value:
            if re.fullmatch(PROTOCOL, value):
                output["relations"].append({"kind": kind, "protocol": value})
            else:
                output["issues"].append("Referência documental inválida: " + kind)
    # Drop repeated headers, but retain original page numbers for evidence.
    body = [(p, s) for p, s in rows if not re.match(r"\s*(?:CNPJ\s+\d|Receita Federal|PEDIDO DE RESTITUIÇÃO,|\d+\s*$)", s)]
    starts = [i for i, (_, s) in enumerate(body) if re.match(r"\s*\d{3}\.\s*Débito\b", s)]
    for n, start in enumerate(starts):
        block = body[start:starts[n + 1] if n + 1 < len(starts) else len(body)]
        # The uppercase final TOTAL is not a second debt amount.
        block = [r for r in block if not re.match(r"\s*TOTAL\b", r[1])]
        seq = int(re.match(r"\s*(\d+)", block[0][1])[1])
        rr = Reader(block, output, f"debts.{seq}.")
        compensated_index = next((i for i, row in enumerate(block)
                                  if fold(row[1].strip()).rstrip(" :") == "valores compensados"), None)
        if compensated_index is None:
            debt = rr.fields(DEBT_FIELDS)
        else:
            money_keys = ("principal", "fine", "interest", "total")
            debt = rr.fields({key: spec for key, spec in DEBT_FIELDS.items() if key not in money_keys})
            original_reader = Reader(block[:compensated_index], output, f"debts.{seq}.")
            original_principal = original_reader.field("original_principal", r"Principal", "money")
            if original_principal is not None:
                debt["original_principal"] = original_principal
            compensated_reader = Reader(block[compensated_index + 1:], output, f"debts.{seq}.")
            debt.update(compensated_reader.fields({key: DEBT_FIELDS[key] for key in money_keys}))

            # Some Receita layouts omit an explicit zero row for Multa or
            # Juros. Infer only one omitted zero and only when the displayed
            # compensated total proves the arithmetic.
            missing = [key for key in ("fine", "interest") if debt.get(key) is None]
            if (len(missing) == 1 and debt.get("principal") is not None and debt.get("total") is not None
                    and all(debt.get(key) is not None for key in ("fine", "interest") if key not in missing)):
                known = Decimal(debt["principal"]) + sum(
                    (Decimal(debt[key]) for key in ("fine", "interest") if key not in missing), Decimal("0")
                )
                if known == Decimal(debt["total"]):
                    inferred_key = missing[0]
                    marker = block[compensated_index]
                    debt[inferred_key] = compensated_reader.record(inferred_key, "0.00", marker)
                    output["evidence"][f"debts.{seq}.{inferred_key}"]["reason"] = (
                        "Zero inferido porque o campo foi omitido em Valores Compensados e a soma confere com o total."
                    )
        debt["sequence"] = rr.record("sequence", seq, block[0])
        revenue = re.match(r"(\d{4})(?:-(\d{2}))?\s*-\s*(.*)", debt["revenue"] or "")
        for key, value in zip(("code", "extension", "description"), revenue.groups() if revenue else (None, None, None)):
            debt[key] = value
            if value:
                output["evidence"][f"debts.{seq}.{key}"] = {**output["evidence"][f"debts.{seq}.revenue"], "value": value}
        output["debts"].append(debt)
    # Only the consolidation section is a source of components, never repeated totals.
    active, blocks, block = False, [], []
    for row in body:
        normalized = fold(row[1].strip())
        if normalized == "consolidacao dos creditos":
            active = True
            continue
        if active and (normalized == "total" or normalized.startswith("creditos apurados")):
            if block:
                blocks.append(block)
            block, active = [], False
        if active:
            if re.match(r"\s*\d{4}\.", row[1]):
                if block:
                    blocks.append(block)
                block = []
            block.append(row)
    if block:
        blocks.append(block)
    consolidation_start = next((i for i, r in enumerate(body) if r[1].strip() == "CONSOLIDAÇÃO DOS CRÉDITOS"), None)
    if consolidation_start is not None:
        tail = body[consolidation_start + 1:]
        total_start = next((i for i, r in enumerate(tail) if r[1].strip() == "TOTAL"), None)
        if total_start is not None:
            total_rows = []
            for row in tail[total_start + 1:]:
                if row[1].strip() == "CRÉDITOS APURADOS":
                    break
                total_rows.append(row)
            fields.update(Reader(total_rows, output).fields({k: FIELDS[k] for k in ("component_total", "deductions", "previous_use")}))
    for block in blocks:
        match = re.match(r"\s*(\d{4})\.", block[0][1])
        if not match:
            output["issues"].append("Consolidação de componentes não reconhecida.")
            continue
        seq = int(match[1])
        rr = Reader(block, output, f"components.{seq}.")
        component = rr.fields(COMPONENT_FIELDS)
        component["sequence"] = rr.record("sequence", seq, block[0])
        code = re.match(r"([^\s-]+)\s*-\s*(.*)", component.get("code_description") or "")
        component["code"], component["description"] = code.groups() if code else (None, None)
        if code:
            for key in ("code", "description"):
                output["evidence"][f"components.{seq}.{key}"] = {
                    **output["evidence"][f"components.{seq}.code_description"], "value": component[key]}
        component["months"] = {}
        output["components"].append(component)
    # Monthly assessed amounts belong to their component, not to additional credits.
    monthly = False
    current = None
    months = "Janeiro Fevereiro Março Abril Maio Junho Julho Agosto Setembro Outubro Novembro Dezembro".split()
    for row in body:
        label = row[1].strip()
        if label == "VALORES APURADOS DO CRÉDITO":
            monthly = True
        elif label in ("TOTAIS", "SALDO DO CRÉDITO"):
            monthly, current = False, None
        elif monthly:
            match = re.match(r"(\d{4})\.\s*Crédito apurado no mês", label)
            if match:
                current = next((c for c in output["components"] if c["sequence"] == int(match[1])), None)
            elif current:
                for month in months:
                    match = re.match(month + r"\s+(" + MONEY + ")$", label, re.I)
                    if match:
                        rr = Reader([row], output, f"components.{current['sequence']}.months.")
                        current["months"][month] = rr.record(month, decimal(match[1]), row)
    # Interpreted values, including normalized enumerations, must match evidence.
    for key, value in fields.items():
        if key in output["evidence"]:
            output["evidence"][key]["value"] = value
    validate(output)
    return output


def validate(output):
    f, errors = output["fields"], output["issues"]
    for required in ("cnpj", "protocol", "modality", "revision_kind", "transmitted_on", "nature"):
        if not f.get(required):
            errors.append("Campo essencial ausente: " + required)
    if f.get("cnpj") and not valid_cnpj(f["cnpj"]):
        errors.append("CNPJ principal inválido.")
    if f.get("protocol") and not re.fullmatch(PROTOCOL, f["protocol"]):
        errors.append("Formato de protocolo inválido.")
    if f.get("modality") not in ("pedido de ressarcimento", "pedido de restituicao", "pedido de reembolso", "declaracao de compensacao"):
        errors.append("Modalidade não suportada ou não identificada.")
    if f.get("quarter") and not re.fullmatch(r"[1-4]º Trimestre", f["quarter"], re.I):
        errors.append("Trimestre do crédito inválido.")
    if f.get("created_on") and f.get("transmitted_on") and f["created_on"] > f["transmitted_on"]:
        errors.append("Criação posterior à transmissão.")
    if f.get("year") and f.get("transmitted_on") and int(f["year"]) > int(f["transmitted_on"][:4]):
        errors.append("Ano do crédito posterior à transmissão.")
    if f.get("other_document") and not any(r["kind"] == "credit_origin" for r in output["relations"]):
        errors.append("Crédito informado em outro PER/DCOMP sem referência identificável.")
    if f.get("revision_kind") == "retificadora" and not any(r["kind"] == "rectifies" for r in output["relations"]):
        errors.append("Retificadora sem protocolo retificado identificável.")
    if any(digits(r["protocol"]) == digits(f.get("protocol")) for r in output["relations"]):
        errors.append("Documento não pode referenciar a si próprio.")
    for collection in ("debts", "components"):
        sequences = [row["sequence"] for row in output[collection]]
        if len(sequences) != len(set(sequences)):
            errors.append("Sequências repetidas em " + collection)
    for debt in output["debts"]:
        if debt.get("holder") and not valid_cnpj(debt["holder"]):
            errors.append(f"Débito {debt['sequence']}: CNPJ detentor inválido.")
        values = [debt.get(k) for k in ("principal", "fine", "interest", "total")]
        if any(v is None for v in values):
            errors.append(f"Débito {debt['sequence']}: valores incompletos.")
        elif sum(Decimal(v) for v in values[:3]) != Decimal(values[3]):
            errors.append(f"Débito {debt['sequence']}: principal + multa + juros difere do total.")
    def check_sum(items, field, total, message):
        if items and total is not None:
            if any(x.get(field) is None for x in items) or sum(Decimal(x[field]) for x in items) != Decimal(total):
                errors.append(message)
    check_sum(output["debts"], "total", f.get("total_debts"), "Soma dos débitos difere do total declarado.")
    check_sum(output["components"], "assessed", f.get("component_total") if f.get("component_total") is not None else f.get("initial_credit"), "Soma dos componentes difere do total consolidado.")
    for key in ("deductions", "previous_use"):
        check_sum(output["components"], key, f.get(key), "Soma dos componentes difere do total: " + key)
    for component in output["components"]:
        if component["months"] and component.get("assessed") is not None and sum(Decimal(v) for v in component["months"].values()) != Decimal(component["assessed"]):
            errors.append(f"Componente {component['sequence']}: soma mensal divergente.")
    values = [f.get(k) for k in ("delivery_credit", "used", "declared_balance")]
    if all(v is not None for v in values) and Decimal(values[0]) - Decimal(values[1]) != Decimal(values[2]):
        errors.append("Crédito na entrega menos utilização difere do saldo declarado.")
    if output["kind"] == "demonstrative" and "compensacao" in (f.get("modality") or ""):
        if not output["debts"] or f.get("total_debts") is None:
            errors.append("DCOMP sem débitos completos ou total identificável.")
    errors[:] = list(dict.fromkeys(errors))
    output["status"] = "review" if errors else "ready"
