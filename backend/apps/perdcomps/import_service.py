"""Preview in memory; confirmation is transactional and always revalidates inputs."""
import copy
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from apps.clients.models import Client
from common.audit.services import AuditService
from .document_models import (
    ImportBatch, ImportedDocument, ImportedFile, DocumentaryCredit, DocumentRelation,
    DocumentDebt, DocumentCreditComponent, DocumentUtilization, DocumentReview,
    ManualImportIssue,
)
from .models import PerDcomp
from .deadlines import automatic_due_date
from .financial import money, operational_balance
from .import_files import ImportProblem
from .import_parser import digits, fold, validate, VERSION, FIELDS, DEBT_FIELDS, COMPONENT_FIELDS


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def manifest(entries, changes):
    return digest({"files": sorted((e["sha256"], e["name"]) for e in entries), "changes": changes, "parser": VERSION})


def apply_reviews(entries, changes, user):
    if not isinstance(changes, list) or len(changes) > 500:
        raise ImportProblem("Lista de revisões inválida.")
    seen = set()
    for change in changes:
        if not isinstance(change, dict):
            raise ImportProblem("Revisão inválida.")
        sha, path = change.get("sha256"), change.get("field", "")
        reason = str(change.get("reason", "")).strip()
        if len(reason) < 10 or len(reason) > 2000 or (sha, path) in seen:
            raise ImportProblem("Cada correção exige justificativa de 10 a 2.000 caracteres e campo único.")
        seen.add((sha, path))
        affected = [e for e in entries if e["sha256"] == sha]
        if not affected:
            raise ImportProblem("Arquivo da revisão não pertence ao lote.")
        for entry in affected:
            extraction = copy.deepcopy(entry["extraction"])
            if extraction.get("layout") != "web83" or not extraction["fields"].get("protocol"):
                raise ImportProblem("Este leiaute não permite correção automática; use o cadastro manual.")
            parts = path.split(".")
            fields, spec = extraction["fields"], FIELDS
            key = parts[-1]
            if len(parts) == 3 and parts[0] in ("debts", "components") and parts[1].isdigit():
                fields = next((x for x in extraction[parts[0]] if x["sequence"] == int(parts[1])), None)
                spec = DEBT_FIELDS if parts[0] == "debts" else COMPONENT_FIELDS
            elif len(parts) != 1:
                raise ImportProblem("Campo de revisão inválido.")
            if key in ("cnpj", "protocol"):
                # Ownership cannot be reassigned through an import review.
                raise ImportProblem("Troca de titular/protocolo requer análise administrativa fora da importação.")
            if fields is None or key not in spec or spec[key][1] not in ("money", "text", "date", "year", "bool"):
                raise ImportProblem("Campo não editável nesta etapa.")
            value = change.get("value")
            kind = spec[key][1]
            if value is not None:
                if kind == "money":
                    try:
                        if not isinstance(value, str) or not re.fullmatch(r"\d{1,20}\.\d{2}", value):
                            raise ValueError()
                        value = str(Decimal(value))
                    except (ValueError, InvalidOperation):
                        raise ImportProblem("Informe o valor decimal com ponto e duas casas, por exemplo 1234.56.") from None
                elif kind == "date":
                    from datetime import date
                    try:
                        value = date.fromisoformat(value).isoformat()
                    except (ValueError, TypeError):
                        raise ImportProblem("Data de revisão inválida; use AAAA-MM-DD.") from None
                elif kind == "bool" and not isinstance(value, bool):
                    raise ImportProblem("Campo lógico exige verdadeiro ou falso.")
                elif kind == "year" and not re.fullmatch(r"(?:19|20)\d{2}", str(value)):
                    raise ImportProblem("Ano inválido.")
                elif kind == "text" and (not isinstance(value, str) or len(value) > 500):
                    raise ImportProblem("Texto inválido ou superior a 500 caracteres.")
            old = fields.get(key)
            fields[key] = value
            evidence = extraction["evidence"].get(path, {"page": None, "text": "Campo não extraído", "value": None, "parser_version": VERSION})
            extraction["evidence"][path] = {**evidence, "original_value": evidence.get("original_value", old), "value": value,
                "reviewed_by": user.pk, "reason": reason}
            extraction["issues"] = [s for s in extraction["issues"] if
                (s.startswith("Campo inválido:") or s.startswith("Valores conflitantes:") or s.startswith("Referência documental")
                 or s.startswith("Protocolo próprio") or s.startswith("Consolidação")) and path not in s]
            validate(extraction)
            entry["extraction"] = extraction


def canonical(key, value):
    if value is None:
        return None
    if key == "cnpj":
        return digits(value)
    if key == "nature":
        # Web receipt and demonstrative spell this same layout differently.
        value = fold(value).replace("ressarc/compens", "ressarcimento/compensacao")
        value = value.replace("pis/pasep nao-cumul -", "pis/pasep nao-cumulativo -")
        return re.sub(r"\s+", " ", re.sub(r"pa (?:apos jan/2014|a partir de janeiro de\s+2014)", "pa2014", value)).strip()
    return str(value)


def merge_extractions(extractions):
    ordered = sorted(extractions, key=lambda e: e["kind"] != "demonstrative")
    merged = copy.deepcopy(ordered[0])
    conflicts = []
    for other in ordered[1:]:
        for key, value in other["fields"].items():
            previous = merged["fields"].get(key)
            if key in ("version", "program", "control", "name", "period_type"):
                pass  # Display differences remain in the original field evidence.
            elif previous is not None and value is not None and canonical(key, previous) != canonical(key, value):
                conflicts.append("Conflito entre evidências: " + key)
            if previous is None and value is not None:
                merged["fields"][key] = value
        for collection in ("debts", "components"):
            if merged[collection] and other[collection] and merged[collection] != other[collection]:
                conflicts.append("Conflito entre demonstrativos: " + collection)
            elif not merged[collection]:
                merged[collection] = copy.deepcopy(other[collection])
        for relation in other["relations"]:
            if relation not in merged["relations"]:
                merged["relations"].append(relation)
    for kind in ("credit_origin", "balance_reference", "rectifies", "cancels"):
        if len({digits(r["protocol"]) for r in merged["relations"] if r["kind"] == kind}) > 1:
            conflicts.append("Referências conflitantes: " + kind)
    return merged, sorted(set(conflicts))


def legacy_map(client):
    result = {}
    for obj in PerDcomp.objects.filter(client_id=client.pk, deleted_at__isnull=True).only("id", "cnpj", "numero_perdcomp"):
        number = digits(obj.numero_perdcomp)
        if len(number) == 24 and digits(obj.cnpj) == digits(client.cnpj):
            result.setdefault(number, []).append(obj)
    return result


def operational_values(fields):
    """Map declarations without treating them as realized compensation/payment."""
    transmitted = date.fromisoformat(fields["transmitted_on"])
    year = int(fields.get("year") or transmitted.year)
    quarter, month = fields.get("quarter"), fields.get("month")
    competence = fields.get("period") or month or quarter or str(year)
    competence_date = None
    if quarter:
        match = re.match(r"([1-4])", str(quarter))
        if match:
            number = int(match.group(1))
            competence = f"{number}º trimestre de {year}"
            competence_date = date(year, (number - 1) * 3 + 1, 1)
    elif month:
        months = {name: index + 1 for index, name in enumerate(
            "janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro".split())}
        number = months.get(fold(str(month)).split()[0])
        if number:
            competence_date = date(year, number, 1)
    modality = fields.get("modality") or ""
    declared = fields.get("requested")
    if declared is None and "compensacao" in modality:
        declared = fields.get("used") if fields.get("used") is not None else fields.get("total_debts")
    if declared is None:
        declared = fields.get("initial_credit")
    if declared is None:
        raise ImportProblem("Documento sem valor declarado seguro para o cadastro operacional.")
    return {
        "numero": fields.get("control") or fields["protocol"],
        "numero_perdcomp": fields["protocol"],
        "processo_protocolo": fields.get("process") or "",
        "data_transmissao": transmitted,
        "data_vencimento": automatic_due_date(transmitted),
        "data_competencia": competence_date,
        "tributo_pedido": (fields.get("credit_tax") or fields.get("nature") or "PER/DCOMP").upper(),
        "competencia": competence,
        "valor_pedido": str(Decimal(declared).quantize(Decimal("0.01"))),
    }


def realized_money(value):
    try:
        return money(value)
    except ValueError:
        return Decimal("0")


def documentary_values(fields, current=None):
    """Values evidenced by a declaration; no homologation or receipt is inferred."""
    modality = fold(fields.get("modality") or "")
    is_compensation = "compensacao" in modality
    is_request = any(kind in modality for kind in ("ressarcimento", "restituicao", "reembolso"))
    normalized = {
        "valor_solicitado": fields.get("requested"),
        "valor_compensado_declarado": fields.get("total_debts") if is_compensation else None,
        "credito_original_utilizado": fields.get("used"),
        "saldo_credito_original": fields.get("declared_balance"),
        "status_compensacao": (PerDcomp.CompensationStatus.DECLARADA_AGUARDANDO_HOMOLOGACAO
            if is_compensation else PerDcomp.CompensationStatus.NAO_APLICAVEL),
        "status_ressarcimento": (PerDcomp.ReimbursementStatus.SOLICITADO
            if is_request else PerDcomp.ReimbursementStatus.NAO_APLICAVEL),
    }
    extracted_compensated = fields.get("total_debts") if is_compensation else None
    proposed_compensated = extracted_compensated if extracted_compensated is not None else (
        current.valor_compensado if current else "")
    requested = operational_values(fields)["valor_pedido"]
    received = current.valor_recebido if current else ""
    try:
        balance = operational_balance(requested, proposed_compensated, received)
    except ValueError:
        # The document remains valid evidence, but the unresolved business mapping
        # must not produce a negative operational balance or overwrite manual data.
        proposed_compensated = current.valor_compensado if current else ""
        received = current.valor_recebido if current else ""
        if current:
            requested = current.valor_pedido
        try:
            balance = operational_balance(requested, proposed_compensated, received)
        except ValueError:
            balance = current.valor_saldo or "" if current else ""
    return {**normalized,
        "valor_compensado": str(Decimal(proposed_compensated).quantize(Decimal("0.01"))) if proposed_compensated not in (None, "") else "",
        "valor_recebido": current.valor_recebido if current else "",
        "valor_saldo": balance,
    }


def financial_mapping_issue(fields, current=None):
    modality = fold(fields.get("modality") or "")
    if "compensacao" not in modality or fields.get("total_debts") is None:
        return None
    requested = operational_values(fields)["valor_pedido"]
    try:
        operational_balance(requested, fields["total_debts"], current.valor_recebido if current else "")
    except ValueError:
        return ("O total declarado da compensação supera o valor atualmente mapeado como Pedido. "
                "Os valores documentais serão preservados, mas Compensado e Saldo não serão substituídos até a regra ser definida.")
    return None


def proposed_operational_values(fields, current=None):
    declared = operational_values(fields)
    mapping_issue = financial_mapping_issue(fields, current)
    if mapping_issue and current:
        declared["valor_pedido"] = current.valor_pedido
    return {**declared, **documentary_values(fields, current)}, mapping_issue


def serialized(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return "" if value is None else str(value)


def operational_plan(client, protocol, fields, legacy=None):
    legacy = legacy if legacy is not None else legacy_map(client)
    matches = legacy.get(protocol, [])
    try:
        current = matches[0] if len(matches) == 1 else None
        proposed, mapping_issue = proposed_operational_values(fields, current)
    except (ImportProblem, ValueError) as exc:
        return {"action": "manual", "reason": str(exc), "changes": [], "financial_confirmation_required": False,
            "financial_review_required": False, "financial_review_reason": None}
    if not matches:
        return {"action": "create", "reason": "Novo protocolo operacional.",
            "changes": [{"field": key, "old": None, "new": serialized(value),
                         "financial": key in {"valor_compensado", "valor_recebido", "valor_saldo"}}
                        for key, value in proposed.items()],
            "financial_confirmation_required": proposed.get("valor_compensado") not in (None, ""),
            "financial_review_required": bool(mapping_issue), "financial_review_reason": mapping_issue}
    if len(matches) > 1:
        return {"action": "conflict", "reason": "Há mais de um cadastro operacional com este protocolo.",
            "changes": [], "financial_confirmation_required": False,
            "financial_review_required": False, "financial_review_reason": None}
    current = matches[0]
    changes = []
    for key, new in proposed.items():
        old = getattr(current, key)
        old_value, new_value = serialized(old), serialized(new)
        if old_value != new_value:
            changes.append({"field": key, "old": old_value, "new": new_value,
                "financial": key in {"valor_compensado", "valor_recebido", "valor_saldo"}})
    financial_changes = [change for change in changes if change["financial"]]
    return {"action": "update" if changes else "link_only",
        "reason": ("Há valores financeiros divergentes; a atualização exige conferência explícita do usuário."
                   if financial_changes else "Atualização declaratória sem alteração financeira.") if changes
                  else "Cadastro operacional já corresponde ao documento.",
        "operational_id": str(current.public_id), "changes": changes,
        "financial_confirmation_required": bool(financial_changes),
        "financial_review_required": bool(mapping_issue), "financial_review_reason": mapping_issue}


def apply_operational(client, document, group, user, legacy, financial_confirmed=False):
    plan = operational_plan(client, group["key"], group["fields"], legacy)
    if plan["action"] in ("manual", "conflict"):
        raise ImportProblem(plan["reason"])
    if plan.get("financial_confirmation_required") and not financial_confirmed:
        raise ImportProblem("Confirme explicitamente os valores financeiros propostos antes de continuar.")
    if plan["action"] == "create":
        values, _ = proposed_operational_values(group["fields"])
        operational = PerDcomp.objects.create(client_id=client.pk, created_by_id=user.pk,
            cnpj=client.cnpj, status=PerDcomp.Status.TRANSMITIDO, valor_selic="", **values)
        AuditService.log_action("CUSTOM", operational, user=user, old_data=None,
            new_data={k: serialized(v) for k, v in values.items()},
            metadata={"type": "perdcomp_batch_operational_create", "document": str(document.public_id),
                      "financial_confirmed_by_user": financial_confirmed})
        legacy.setdefault(group["key"], []).append(operational)
        action = "created"
    else:
        operational = legacy[group["key"]][0]
        action = "linked"
        if plan["action"] == "update":
            values, _ = proposed_operational_values(group["fields"], operational)
            old_data, new_data = {}, {}
            for change in plan["changes"]:
                key = change["field"]
                old_data[key], new_data[key] = change["old"], change["new"]
                setattr(operational, key, values[key])
            operational.save(update_fields=[c["field"] for c in plan["changes"]] + ["updated_at"])
            AuditService.log_action("CUSTOM", operational, user=user, old_data=old_data, new_data=new_data,
                metadata={"type": "perdcomp_batch_operational_update", "document": str(document.public_id),
                          "financial_confirmed_by_user": financial_confirmed, "preserved": ["status"]})
            action = "updated"
    document.legacy_document = operational
    data = dict(document.data)
    data["operational_sync"] = {"action": action, "operational_id": str(operational.public_id),
        "at": timezone.now().isoformat(), "financial_confirmed_by_user": financial_confirmed}
    document.data = data
    document.save(update_fields=["legacy_document", "data", "updated_at"])
    return action


def build_preview(client, entries):
    known = {d.protocol: d for d in ImportedDocument.objects.filter(client=client).prefetch_related(
        Prefetch("files", queryset=ImportedFile.objects.defer("original_content")), "relations")}
    existing_hashes = set(ImportedFile.objects.filter(client=client).values_list("sha256", flat=True))
    legacy = legacy_map(client)
    grouped, files, seen = {}, [], set()
    for entry in entries:
        ex = entry["extraction"]
        f = ex["fields"]
        status = ex["status"]
        issues = list(ex["issues"])
        if f.get("cnpj") and digits(f["cnpj"]) != digits(client.cnpj):
            status, issues = "wrong_client", issues + ["CNPJ principal não corresponde ao cliente selecionado."]
        duplicate = entry["sha256"] in seen or entry["sha256"] in existing_hashes
        if duplicate and status == "ready":
            status = "duplicate"
        seen.add(entry["sha256"])
        item = {k: entry[k] for k in ("index", "name", "sha256", "size", "pages")}
        item.update(status=status, issues=issues, kind=ex["kind"], fields=f, extraction=ex, duplicate=duplicate)
        item["manual_eligible"] = entry["raw"].startswith(b"%PDF-")
        files.append(item)
        if f.get("protocol") and status not in ("wrong_client", "no_text", "rejected"):
            grouped.setdefault(digits(f["protocol"]), []).append(item)
    groups = []
    graph = {number: {r.target_protocol for r in d.relations.all()} for number, d in known.items()}
    for number, items in grouped.items():
        exs = [i["extraction"] for i in items]
        if number in known:
            exs += [f.extraction for f in known[number].files.all()]
        merged, conflicts = merge_extractions(exs)
        problems = sorted({s for i in items for s in i["issues"]} | set(conflicts))
        if len(legacy.get(number, [])) > 1:
            problems.append("Mais de um cadastro anterior corresponde ao protocolo; revisão administrativa necessária.")
        # Same normalized taxpayer must not silently belong to another client record.
        if ImportedDocument.objects.filter(cnpj=digits(client.cnpj), protocol=number).exclude(client=client).exists():
            problems.append("Identidade já vinculada a outro cadastro de cliente.")
        kinds = {e["kind"] for e in exs}
        # Any extraction produced outside the server requires the same explicit
        # human confirmation as OCR, even when the local tool found native text.
        ocr_extractions = [extraction for extraction in exs
                           if extraction.get("text_source") == "ocr" or extraction.get("local_package")]
        ocr_confidences = [float(extraction.get("ocr", {}).get("confidence", 0))
                           for extraction in ocr_extractions if extraction.get("ocr")]
        completeness = "complete" if {"receipt", "demonstrative"} <= kinds else "receipt_only" if "receipt" in kinds else "demonstrative_only"
        refs = merged["relations"]
        missing = [r for r in refs if digits(r["protocol"]) not in known and digits(r["protocol"]) not in grouped and digits(r["protocol"]) not in legacy]
        retifier = merged["fields"].get("revision_kind") == "retificadora"
        duplicate = all(i["sha256"] in existing_hashes for i in items)
        graph[number] = {digits(r["protocol"]) for r in refs}
        groups.append({"key": number, "fields": merged["fields"], "debts": merged["debts"], "components": merged["components"],
            "relations": refs, "files": [i["index"] for i in items], "issues": problems, "missing": missing,
            "completeness": "conflict" if conflicts else completeness, "retifier": retifier, "duplicate": duplicate,
            "ocr_used": bool(ocr_extractions),
            "ocr_confidence": round(min(ocr_confidences), 4) if ocr_confidences else None,
            "status": "conflict" if conflicts else "review" if problems else "duplicate" if duplicate else "retifier" if retifier else "missing_reference" if missing else "ready",
            "importable": not problems, "fiscal_status": "nao_consultada", "financial_effect": "nao_aplicado",
            "operational": operational_plan(client, number, merged["fields"], legacy)})
    replacement_map = {}
    for relation in DocumentRelation.objects.filter(source__client=client, kind__in=["rectifies", "cancels"]).select_related("source"):
        replacement_map.setdefault(relation.target_protocol, []).append((relation.kind, relation.source.protocol,
            relation.source.data.get("transmitted_on") or ""))
    for group in groups:
        for relation in group["relations"]:
            if relation["kind"] in ("rectifies", "cancels"):
                replacement_map.setdefault(digits(relation["protocol"]), []).append((relation["kind"], group["key"],
                    group["fields"].get("transmitted_on") or ""))
    for group in groups:
        replacements = sorted(replacement_map.get(group["key"], []), key=lambda item: (item[2], item[1]))
        if replacements:
            kind, successor, _ = replacements[-1]
            group["version"] = {"status": "cancelled" if kind == "cancels" else "superseded",
                "successor_protocol": successor,
                "message": "Versão anterior — nenhum dado da versão vigente será alterado."}
        else:
            group["version"] = {"status": "current", "successor_protocol": None, "message": "Versão vigente."}
    def cycle(start):
        pending = list(graph.get(start, ()))
        visited = set()
        while pending:
            node = pending.pop()
            if node == start:
                return True
            if node not in visited:
                visited.add(node)
                pending.extend(graph.get(node, ()))
        return False
    dates = {k: d.data.get("transmitted_on") for k, d in known.items()}
    dates.update({g["key"]: g["fields"].get("transmitted_on") for g in groups})
    for group in groups:
        if cycle(group["key"]):
            group["issues"].append("Referência circular entre documentos.")
        for ref in group["relations"]:
            source_date, target_date = dates.get(group["key"]), dates.get(digits(ref["protocol"]))
            if source_date and target_date and target_date > source_date:
                group["issues"].append("Documento referenciado foi transmitido depois deste documento.")
        if group["operational"]["action"] in ("manual", "conflict"):
            group["issues"].append(group["operational"]["reason"])
        if group["issues"]:
            group.update(importable=False, status="conflict" if group["completeness"] == "conflict" else "review")
    return {"client_id": str(client.public_id), "files": files, "groups": groups,
        "counts": {"files": len(files), "documents": len(groups), "importable": sum(g["importable"] for g in groups),
                   "rejected": sum(f["status"] in ("wrong_client", "no_text", "rejected") for f in files)},
        "notice": "Prévia sem gravação. Alterações financeiras só são aplicadas após conferência explícita do usuário."}


def resolve_references(client):
    documents = {d.protocol: d for d in ImportedDocument.objects.filter(client=client)}
    legacy = legacy_map(client)
    for relation in DocumentRelation.objects.filter(source__client=client):
        target = documents.get(relation.target_protocol)
        old = legacy.get(relation.target_protocol, [])
        relation.target = target
        relation.legacy_target = old[0] if len(old) == 1 else None
        relation.save(update_fields=["target", "legacy_target"])
    # Fixed-point propagation makes importing origin before/after usages equivalent.
    for _ in range(len(documents) + 1):
        changed = False
        for document in documents.values():
            references = list(document.relations.filter(kind__in=["credit_origin", "rectifies"]))
            origin = next((r for r in references if r.kind == "credit_origin"), references[0] if references else None)
            credit = None
            if origin:
                target = documents.get(origin.target_protocol)
                credit = target.credit if target else None
            elif (document.completeness != "receipt_only" and document.revision_kind == "original"
                  and document.data.get("initial_credit") is not None and document.data.get("other_document") is False
                  and not any(document.data.get(k) for k in ("judicial", "successor", "prior_process"))):
                credit, _ = DocumentaryCredit.objects.get_or_create(client=client, origin_protocol=document.protocol)
            if credit and document.credit_id != credit.pk:
                document.credit = credit
                document.save(update_fields=["credit", "updated_at"])
                changed = True
        if not changed:
            break


def synchronize_versions(client, user=None):
    """Mirror explicit rectification/cancellation chains; upload order is irrelevant."""
    documents = list(ImportedDocument.objects.filter(client=client).select_related("legacy_document"))
    desired = {document.protocol: (ImportedDocument.VersionStatus.CURRENT, None) for document in documents}
    relations = DocumentRelation.objects.filter(source__client=client, kind__in=["rectifies", "cancels"]).select_related("source")
    candidates = {}
    for relation in relations:
        candidates.setdefault(relation.target_protocol, []).append(relation)
    for target_protocol, options in candidates.items():
        relation = max(options, key=lambda item: (item.source.data.get("transmitted_on") or "", item.source.protocol))
        desired[target_protocol] = (
            ImportedDocument.VersionStatus.CANCELLED if relation.kind == "cancels" else ImportedDocument.VersionStatus.SUPERSEDED,
            relation.source,
        )
    for document in documents:
        status, successor = desired[document.protocol]
        changed = document.version_status != status or document.superseded_by_id != (successor.pk if successor else None)
        if changed:
            document.version_status, document.superseded_by = status, successor
            document.save(update_fields=["version_status", "superseded_by", "updated_at"])
        operational = document.legacy_document
        if not operational:
            continue
        operational_status = {
            ImportedDocument.VersionStatus.CURRENT: PerDcomp.VersionStatus.VIGENTE,
            ImportedDocument.VersionStatus.SUPERSEDED: PerDcomp.VersionStatus.SUBSTITUIDA,
            ImportedDocument.VersionStatus.PREVIOUS: PerDcomp.VersionStatus.VERSAO_ANTERIOR,
            ImportedDocument.VersionStatus.CANCELLED: PerDcomp.VersionStatus.CANCELADA,
        }[status]
        successor_operational = successor.legacy_document if successor else None
        if operational.version_status != operational_status or operational.superseded_by_id != (
            successor_operational.pk if successor_operational else None):
            old = {"version_status": operational.version_status,
                   "superseded_by": str(operational.superseded_by.public_id) if operational.superseded_by_id else None}
            operational.version_status, operational.superseded_by = operational_status, successor_operational
            if status == ImportedDocument.VersionStatus.SUPERSEDED:
                operational.status_compensacao = (PerDcomp.CompensationStatus.RETIFICADA
                    if operational.status_compensacao != PerDcomp.CompensationStatus.NAO_APLICAVEL
                    else operational.status_compensacao)
            elif status == ImportedDocument.VersionStatus.CANCELLED:
                operational.status_compensacao = (PerDcomp.CompensationStatus.CANCELADA
                    if operational.status_compensacao != PerDcomp.CompensationStatus.NAO_APLICAVEL
                    else operational.status_compensacao)
            operational.save(update_fields=["version_status", "superseded_by", "status_compensacao", "updated_at"])
            if user:
                AuditService.log_action("CUSTOM", operational, user=user, old_data=old,
                    new_data={"version_status": operational.version_status,
                              "superseded_by": str(successor_operational.public_id) if successor_operational else None},
                    metadata={"type": "perdcomp_version_resolution", "upload_order_ignored": True})
    # A document imported now may rectify an older operational record that has no
    # ImportedDocument yet. Preserve and version that record as well.
    for target_protocol, options in candidates.items():
        relation = max(options, key=lambda item: (item.source.data.get("transmitted_on") or "", item.source.protocol))
        target_operational = relation.target.legacy_document if relation.target_id else relation.legacy_target
        successor_operational = relation.source.legacy_document
        if not target_operational or not successor_operational:
            continue
        status = PerDcomp.VersionStatus.CANCELADA if relation.kind == "cancels" else PerDcomp.VersionStatus.SUBSTITUIDA
        if target_operational.version_status == status and target_operational.superseded_by_id == successor_operational.pk:
            continue
        old = {"version_status": target_operational.version_status,
               "superseded_by": str(target_operational.superseded_by.public_id) if target_operational.superseded_by_id else None}
        target_operational.version_status = status
        target_operational.superseded_by = successor_operational
        if relation.kind == "rectifies" and target_operational.status_compensacao != PerDcomp.CompensationStatus.NAO_APLICAVEL:
            target_operational.status_compensacao = PerDcomp.CompensationStatus.RETIFICADA
        elif relation.kind == "cancels" and target_operational.status_compensacao != PerDcomp.CompensationStatus.NAO_APLICAVEL:
            target_operational.status_compensacao = PerDcomp.CompensationStatus.CANCELADA
        target_operational.save(update_fields=["version_status", "superseded_by", "status_compensacao", "updated_at"])
        if user:
            AuditService.log_action("CUSTOM", target_operational, user=user, old_data=old,
                new_data={"version_status": status, "superseded_by": str(successor_operational.public_id)},
                metadata={"type": "perdcomp_version_resolution", "upload_order_ignored": True})


def stored_group(document):
    return {
        "key": document.protocol,
        "fields": document.data,
        "debts": [debt.data for debt in document.debts.all()],
        "components": [component.data for component in document.components.all()],
        "relations": [{"kind": relation.kind, "protocol": relation.target_protocol}
                      for relation in document.relations.all()],
        "retifier": document.revision_kind == "retificadora",
    }


def build_reprocess_preview(client):
    legacy = legacy_map(client)
    documents = list(ImportedDocument.objects.filter(client=client).prefetch_related("debts", "components", "relations", "files"))
    replacements = {}
    for document in documents:
        for relation in document.relations.all():
            if relation.kind in ("rectifies", "cancels"):
                replacements.setdefault(relation.target_protocol, []).append((
                    relation.kind, document.protocol, document.data.get("transmitted_on") or ""))
    results = []
    for document in documents:
        group = stored_group(document)
        plan = operational_plan(client, document.protocol, document.data, legacy)
        options = sorted(replacements.get(document.protocol, []), key=lambda item: (item[2], item[1]))
        version = ({"status": "cancelled" if options[-1][0] == "cancels" else "superseded",
                    "successor_protocol": options[-1][1],
                    "message": "Versão anterior — nenhum dado da versão vigente será alterado."}
                   if options else {"status": "current", "successor_protocol": None, "message": "Versão vigente."})
        results.append({"key": document.protocol, "document_id": str(document.public_id), "fields": document.data,
            "retifier": group["retifier"], "version": version, "operational": plan,
            "files": [{"id": str(file.public_id), "name": file.original_name, "kind": file.kind,
                       "sha256": file.sha256, "pages": file.pages} for file in document.files.all()],
            "needs_processing": plan["action"] != "link_only" or document.legacy_document_id is None or
                                document.version_status != version["status"]})
    pending = [item for item in results if item["needs_processing"]]
    return {"documents": pending,
        "counts": {"pending": len(pending), "financial_confirmation": sum(
            bool(item["operational"].get("financial_confirmation_required")) for item in pending)},
        "notice": "Arquivos já preservados no sistema. Nenhum novo upload é necessário."}


def reprocess_manifest(preview):
    return digest([{"key": item["key"], "version": item["version"], "operational": item["operational"]}
                   for item in preview["documents"]])


@transaction.atomic
def reprocess_documents(client, selected, financial_confirmed, user, reason):
    Client.objects.select_for_update().get(pk=client.pk)
    selected, financial_confirmed = set(selected), set(financial_confirmed)
    preview = build_reprocess_preview(client)
    available = {item["key"]: item for item in preview["documents"]}
    if not selected or not selected <= set(available):
        raise ImportProblem("A seleção mudou. Gere novamente a prévia dos documentos já importados.")
    if not financial_confirmed <= selected:
        raise ImportProblem("A confirmação financeira deve pertencer aos documentos selecionados.")
    required = {key for key in selected if available[key]["operational"].get("financial_confirmation_required")}
    if not required <= financial_confirmed:
        raise ImportProblem("Confira e autorize explicitamente todas as alterações financeiras propostas.")
    if (required or any(available[key]["retifier"] for key in selected)) and len(reason.strip()) < 10:
        raise ImportProblem("Informe uma justificativa de conferência com pelo menos 10 caracteres.")
    fingerprint = digest({"operation": "reprocess", "selected": sorted(selected),
                          "confirmed": sorted(financial_confirmed), "preview": reprocess_manifest(preview)})
    previous = ImportBatch.objects.filter(client=client, fingerprint=fingerprint).first()
    if previous:
        return {**previous.summary, "batch_id": str(previous.public_id), "repeated": True}
    batch = ImportBatch.objects.create(client=client, fingerprint=fingerprint, created_by=user)
    legacy = legacy_map(client)
    counts = {"created": 0, "updated": 0, "linked": 0}
    documents = {document.protocol: document for document in ImportedDocument.objects.filter(
        client=client, protocol__in=selected).prefetch_related("debts", "components", "relations")}
    for key in sorted(selected):
        document = documents[key]
        group = stored_group(document)
        action = apply_operational(client, document, group, user, legacy, key in financial_confirmed)
        counts[action] += 1
        DocumentReview.objects.create(document=document, batch=batch, reviewer=user, changes=[
            {"source": "reprocess", **change} for change in available[key]["operational"]["changes"]],
            reason=reason.strip() or "Registro operacional de documento já importado.")
    resolve_references(client)
    synchronize_versions(client, user)
    summary = {"documents": len(selected), "operational": counts, "financial_confirmed": len(financial_confirmed),
        "published_at": timezone.now().isoformat(), "source": "already_imported"}
    batch.summary = summary
    batch.save(update_fields=["summary"])
    AuditService.log_action("CREATE", batch, new_data=summary, user=user,
        metadata={"operation": "perdcomp_reprocess_existing", "parser": VERSION})
    return {**summary, "batch_id": str(batch.public_id), "repeated": False}


@transaction.atomic
def publish(client, entries, selected, changes, user, reason, manual_selected=None, financial_confirmed=None,
            ocr_confirmed=None):
    # Lock the client row before checking uniqueness, including the first import.
    Client.objects.select_for_update().get(pk=client.pk)
    selected = set(selected)
    manual_selected = set(manual_selected or [])
    financial_confirmed = set(financial_confirmed or [])
    ocr_confirmed = set(ocr_confirmed or [])
    if not financial_confirmed <= selected:
        raise ImportProblem("A confirmação financeira deve pertencer aos documentos selecionados.")
    if not ocr_confirmed <= selected:
        raise ImportProblem("A confirmação do OCR deve pertencer aos documentos selecionados.")
    manual_entries = [e for e in entries if e["sha256"] in manual_selected]
    if len(manual_entries) != len(manual_selected) or any(not e["raw"].startswith(b"%PDF-") for e in manual_entries):
        raise ImportProblem("Seleção de tratamento manual contém arquivo inválido ou ausente.")
    if any(digits(e["extraction"]["fields"].get("protocol")) in selected for e in manual_entries):
        raise ImportProblem("O mesmo PDF não pode ser publicado automaticamente e enviado para tratamento manual.")
    filtered = [e for e in entries if digits(e["extraction"]["fields"].get("protocol")) in selected]
    preview = build_preview(client, filtered)
    groups = preview["groups"]
    if (not selected and not manual_selected) or {g["key"] for g in groups} != selected or any(not g["importable"] for g in groups):
        raise ImportProblem("Seleção contém pendências ou mudou desde a prévia. Refaça a conferência.")
    required_confirmations = {g["key"] for g in groups if g["operational"].get("financial_confirmation_required")}
    required_ocr_confirmations = {g["key"] for g in groups if g.get("ocr_used")}
    if not required_confirmations <= financial_confirmed:
        raise ImportProblem("Confira e autorize explicitamente todas as alterações financeiras propostas.")
    if not required_ocr_confirmations <= ocr_confirmed:
        raise ImportProblem("Confira e autorize explicitamente os documentos interpretados por OCR.")
    if any(g["retifier"] for g in groups) and len(reason.strip()) < 10:
        raise ImportProblem("Retificadoras exigem justificativa para preservar a cadeia de versões.")
    if required_confirmations and len(reason.strip()) < 10:
        raise ImportProblem("Alterações financeiras exigem uma justificativa de conferência com pelo menos 10 caracteres.")
    if required_ocr_confirmations and len(reason.strip()) < 10:
        raise ImportProblem("Documentos interpretados por OCR exigem uma justificativa de conferência com pelo menos 10 caracteres.")
    fingerprint = digest({"files": sorted({e["sha256"] for e in filtered + manual_entries}), "changes": changes,
                          "selected": sorted(selected), "manual": sorted(manual_selected),
                          "financial_confirmed": sorted(financial_confirmed),
                          "ocr_confirmed": sorted(ocr_confirmed)})
    previous = ImportBatch.objects.filter(client=client, fingerprint=fingerprint).first()
    if previous:
        return {**previous.summary, "batch_id": str(previous.public_id), "repeated": True}
    batch = ImportBatch.objects.create(client=client, fingerprint=fingerprint, created_by=user)
    legacy = legacy_map(client)
    created, attached = 0, 0
    operational_counts = {"created": 0, "updated": 0, "linked": 0}
    for group in groups:
        fields = group["fields"]
        document, new = ImportedDocument.objects.get_or_create(cnpj=digits(client.cnpj), protocol=group["key"], defaults={
            "client": client, "protocol_original": fields["protocol"], "modality": fields["modality"],
            "revision_kind": fields["revision_kind"], "completeness": group["completeness"], "data": fields,
        })
        created += new
        document.data = fields
        document.completeness = group["completeness"]
        document.save()
        for entry in filtered:
            if digits(entry["extraction"]["fields"].get("protocol")) != group["key"]:
                continue
            if ImportedFile.objects.filter(client=client, sha256=entry["sha256"]).exists():
                continue
            # The immutable original is durable in the same DB transaction. Drive
            # synchronization can be performed separately; no orphan external upload.
            ImportedFile.objects.create(client=client, document=document, batch=batch, sha256=entry["sha256"],
                original_name=entry["name"], kind=entry["extraction"]["kind"], pages=entry["pages"],
                original_content=entry["raw"], parser_version=VERSION, extraction=entry["extraction"])
            attached += 1
        for debt in group["debts"]:
            DocumentDebt.objects.get_or_create(document=document, sequence=debt["sequence"], defaults={
                **{key: debt.get(key) for key in ("principal", "fine", "interest", "total")}, "data": debt})
        for component in group["components"]:
            DocumentCreditComponent.objects.get_or_create(document=document, sequence=component["sequence"], defaults={
                **{key: component.get(key) for key in ("assessed", "deductions", "previous_use", "balance", "used")}, "data": component})
        if fields.get("used") is not None:
            DocumentUtilization.objects.get_or_create(document=document, defaults={"declared": fields["used"]})
        for relation in group["relations"]:
            DocumentRelation.objects.get_or_create(source=document, kind=relation["kind"], target_protocol=digits(relation["protocol"]))
        doc_hashes = {e["sha256"] for e in filtered if digits(e["extraction"]["fields"].get("protocol")) == group["key"]}
        review_changes = [c for c in changes if c["sha256"] in doc_hashes]
        DocumentReview.objects.create(document=document, batch=batch, reviewer=user, changes=review_changes,
            reason=reason.strip() or "Conferência e integração operacional dos valores declarados.")
        action = apply_operational(client, document, group, user, legacy, group["key"] in financial_confirmed)
        operational_counts[action] += 1
    manual_created = 0
    for entry in manual_entries:
        _, was_created = ManualImportIssue.objects.get_or_create(client=client, sha256=entry["sha256"], defaults={
            "batch": batch, "original_name": entry["name"], "pages": entry["pages"],
            "original_content": entry["raw"], "extraction": entry["extraction"],
            "issues": entry["extraction"].get("issues", []), "created_by": user})
        manual_created += int(was_created)
    resolve_references(client)
    synchronize_versions(client, user)
    summary = {"created": created, "attached": attached, "documents": len(groups),
        "pending_references": DocumentRelation.objects.filter(source__client=client, target__isnull=True, legacy_target__isnull=True).count(),
        "financial_effect": "valores_conferidos_pelo_usuario", "published_at": timezone.now().isoformat(),
        "ocr_confirmed": len(ocr_confirmed),
        "operational": operational_counts, "manual_pending_created": manual_created,
        "files": [{"name": e["name"], "sha256": e["sha256"],
            "selected": digits(e["extraction"]["fields"].get("protocol")) in selected,
            "extraction_status": e["extraction"]["status"]} for e in entries]}
    batch.summary = summary
    batch.save(update_fields=["summary"])
    AuditService.log_action("CREATE", batch, new_data=summary, user=user,
        metadata={"operation": "perdcomp_documentary_import", "parser": VERSION})
    return {**summary, "batch_id": str(batch.public_id), "repeated": False}
