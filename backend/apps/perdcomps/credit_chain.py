"""Read-only projection of documentary PER/DCOMP credit chains.

This module intentionally does not calculate or persist an available credit.
The business rules for consolidating original documents, rectifications and
successive utilizations are still pending.  Its only job is to expose the
relations and the values already recorded in each source document.
"""

from collections import defaultdict

from django.db.models import BooleanField, Case, Prefetch, Value, When

from .document_models import ImportedDocument, ImportedFile


RELATION_KINDS = {"credit_origin", "balance_reference", "rectifies", "cancels"}
VERSION_RELATION_KINDS = {"rectifies", "cancels"}


def _text(value):
    if value is None or value == "":
        return None
    return str(value)


def _decimal_text(value):
    return None if value is None else format(value, "f")


def _operational_values(document):
    operational = document.legacy_document
    if not operational:
        return None
    return {
        "requested": _decimal_text(operational.valor_solicitado) or _text(operational.valor_pedido),
        "compensated": _decimal_text(operational.valor_compensado_declarado) or _text(operational.valor_compensado),
        "received": _decimal_text(operational.valor_recebido_banco) or _text(operational.valor_recebido),
        "balance": _text(operational.valor_saldo),
    }


def _documentary_values(document):
    data = document.data or {}
    utilization = getattr(document, "documentutilization", None)
    return {
        "requested": _text(data.get("requested")),
        "used": _decimal_text(utilization.declared) if utilization else _text(data.get("used")),
        "declared_balance": _text(data.get("declared_balance")),
    }


def _has_cycle(nodes, edges):
    adjacency = defaultdict(set)
    for source, target in edges:
        if source in nodes and target in nodes:
            adjacency[source].add(target)

    visiting = set()
    visited = set()

    def visit(protocol):
        if protocol in visiting:
            return True
        if protocol in visited:
            return False
        visiting.add(protocol)
        if any(visit(target) for target in adjacency[protocol]):
            return True
        visiting.remove(protocol)
        visited.add(protocol)
        return False

    return any(visit(protocol) for protocol in nodes if protocol not in visited)


def _components(protocols, relations):
    """Return connected protocol sets without interpreting a financial rule."""
    parent = {protocol: protocol for protocol in protocols}

    def find(value):
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for relation in relations:
        if relation.kind in RELATION_KINDS and relation.target_protocol:
            union(relation.source.protocol, relation.target_protocol)

    result = defaultdict(set)
    for protocol in parent:
        result[find(protocol)].add(protocol)
    return list(result.values())


def _file_item(file):
    return {
        "id": str(file.public_id),
        "name": file.original_name,
        "kind": file.kind,
        "pages": file.pages,
        "available": bool(file.drive_file_id or file.has_database_original),
        "storage": (
            "drive" if file.drive_file_id and file.database_released_at
            else "transition" if file.drive_file_id
            else "database"
        ),
    }


def _document_item(document, relations_by_source):
    data = document.data or {}
    return {
        "id": str(document.public_id),
        "operational_id": str(document.legacy_document.public_id) if document.legacy_document_id else None,
        "protocol": document.protocol,
        "source": "imported_pdf",
        "transmitted_on": _text(data.get("transmitted_on")),
        "modality": _text(data.get("modality")) or _text(document.modality),
        "nature": _text(data.get("nature")),
        "revision_kind": _text(document.revision_kind),
        "version_status": document.version_status,
        "superseded_by": document.superseded_by.protocol if document.superseded_by_id else None,
        "documentary_values": _documentary_values(document),
        "operational_values": _operational_values(document),
        "relations": [
            {
                "kind": relation.kind,
                "target_protocol": relation.target_protocol,
                "resolved": bool(relation.target_id or relation.legacy_target_id),
                "target_source": (
                    "imported_pdf" if relation.target_id
                    else "operational_only" if relation.legacy_target_id
                    else None
                ),
            }
            for relation in relations_by_source.get(document.protocol, [])
        ],
        "files": [_file_item(file) for file in document.files.all()],
    }


def _legacy_item(relation):
    operational = relation.legacy_target
    if not operational:
        return None
    return {
        "id": None,
        "operational_id": str(operational.public_id),
        "protocol": relation.target_protocol,
        "source": "operational_only",
        "transmitted_on": operational.data_transmissao.isoformat() if operational.data_transmissao else None,
        "modality": None,
        "nature": _text(operational.tributo_pedido),
        "revision_kind": None,
        "version_status": _text(operational.version_status),
        "superseded_by": operational.superseded_by.numero_perdcomp if operational.superseded_by_id else None,
        "documentary_values": {"requested": None, "used": None, "declared_balance": None},
        "operational_values": {
            "requested": _decimal_text(operational.valor_solicitado) or _text(operational.valor_pedido),
            "compensated": _decimal_text(operational.valor_compensado_declarado) or _text(operational.valor_compensado),
            "received": _decimal_text(operational.valor_recebido_banco) or _text(operational.valor_recebido),
            "balance": _text(operational.valor_saldo),
        },
        "relations": [],
        "files": [],
    }


def build_credit_chain_report(client):
    """Build a factual, read-only chain report for one client."""
    documents = list(
        ImportedDocument.objects.filter(client=client)
        .select_related("credit", "legacy_document", "superseded_by", "documentutilization")
        .prefetch_related(
            Prefetch(
                "files",
                queryset=ImportedFile.objects.only(
                    "id", "public_id", "document_id", "original_name", "kind", "pages",
                    "drive_file_id", "database_released_at",
                ).annotate(
                    has_database_original=Case(
                        When(original_content__isnull=False, then=Value(True)),
                        default=Value(False),
                        output_field=BooleanField(),
                    )
                ),
            ),
            "relations__target",
            "relations__legacy_target",
        )
        .order_by("created_at", "protocol")
    )
    document_by_protocol = {document.protocol: document for document in documents}
    relations = [
        relation
        for document in documents
        for relation in document.relations.all()
        if relation.kind in RELATION_KINDS
    ]
    relations_by_source = defaultdict(list)
    for relation in relations:
        relations_by_source[relation.source.protocol].append(relation)

    components = _components(document_by_protocol, relations)
    grouped = defaultdict(lambda: {"protocols": set(), "anchors": set(), "documented_anchors": set()})
    for component in components:
        component_documents = [document_by_protocol[p] for p in component if p in document_by_protocol]
        anchors = {
            document.credit.origin_protocol
            for document in component_documents
            if document.credit_id
        }
        documented_anchors = set(anchors)
        anchors.update(
            relation.target_protocol
            for document in component_documents
            for relation in relations_by_source.get(document.protocol, [])
            if relation.kind == "credit_origin"
        )
        group_key = sorted(anchors)[0] if len(anchors) == 1 else f"unanchored:{sorted(component)[0]}"
        grouped[group_key]["protocols"].update(component)
        grouped[group_key]["anchors"].update(anchors)
        grouped[group_key]["documented_anchors"].update(documented_anchors)

    chains = []
    total_pending = 0
    total_ambiguous = 0
    total_documents = 0
    for group_key, group in sorted(grouped.items(), key=lambda item: item[0]):
        protocols = group["protocols"]
        group_documents = [document_by_protocol[p] for p in protocols if p in document_by_protocol]
        group_relations = [
            relation
            for document in group_documents
            for relation in relations_by_source.get(document.protocol, [])
        ]
        issues = []
        pending = [r for r in group_relations if not r.target_id and not r.legacy_target_id]
        version_edges = [
            (relation.source.protocol, relation.target_protocol)
            for relation in group_relations
            if relation.kind in VERSION_RELATION_KINDS
        ]
        successors = defaultdict(set)
        for source, target in version_edges:
            successors[target].add(source)
        branches = {target: sources for target, sources in successors.items() if len(sources) > 1}
        cycle = _has_cycle(protocols, version_edges)
        anchor_candidates = sorted(group["anchors"])
        anchor_protocol = anchor_candidates[0] if len(anchor_candidates) == 1 else None
        origin_known = bool(
            anchor_protocol
            and (
                anchor_protocol in document_by_protocol
                or any(r.target_protocol == anchor_protocol and r.legacy_target_id for r in group_relations)
            )
        )

        if len(anchor_candidates) > 1:
            issues.append("A mesma cadeia possui mais de uma origem documental possível.")
        if branches:
            issues.append("Há mais de uma retificadora ou canceladora para a mesma versão.")
        if cycle:
            issues.append("Foi detectado um ciclo entre versões documentais.")
        if pending:
            issues.append(f"{len(pending)} referência(s) ainda não foram vinculadas a um documento cadastrado.")
        if anchor_protocol and not origin_known:
            issues.append("O protocolo de origem foi informado, mas o documento de origem ainda não foi importado.")
        if not anchor_candidates:
            issues.append("A origem do crédito não foi identificada com segurança.")

        ambiguous = len(anchor_candidates) > 1 or bool(branches) or cycle
        status = "ambiguous" if ambiguous else "attention" if issues else "documented"
        total_pending += len(pending)
        total_ambiguous += int(ambiguous)

        items = [_document_item(document, relations_by_source) for document in group_documents]
        imported_protocols = {item["protocol"] for item in items}
        for relation in group_relations:
            if relation.target_protocol in imported_protocols or not relation.legacy_target_id:
                continue
            legacy = _legacy_item(relation)
            if legacy:
                items.append(legacy)
                imported_protocols.add(relation.target_protocol)

        items.sort(key=lambda item: (item["transmitted_on"] or "", item["protocol"]))
        total_documents += len(items)
        chains.append({
            "id": anchor_protocol or group_key,
            "origin_protocol": anchor_protocol,
            "origin_status": (
                "documented" if anchor_protocol in group["documented_anchors"] and origin_known
                else "referenced" if anchor_protocol
                else "unknown"
            ),
            "status": status,
            "issues": issues,
            "documents": items,
            "relations": [
                {
                    "source_protocol": relation.source.protocol,
                    "kind": relation.kind,
                    "target_protocol": relation.target_protocol,
                    "resolved": bool(relation.target_id or relation.legacy_target_id),
                }
                for relation in group_relations
            ],
        })

    return {
        "client_id": str(client.public_id),
        "calculation": {
            "enabled": False,
            "status": "pending_business_rules",
            "message": (
                "Nenhum saldo consolidado foi calculado. Os valores abaixo são exibidos "
                "separadamente, exatamente como constam em cada documento e no cadastro operacional."
            ),
        },
        "counts": {
            "chains": len(chains),
            "documents": total_documents,
            "pending_references": total_pending,
            "ambiguous_chains": total_ambiguous,
        },
        "chains": chains,
    }
