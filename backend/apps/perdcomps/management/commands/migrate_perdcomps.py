import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.contenttypes.models import ContentType

from apps.clients.models import Client
from apps.perdcomps.models import PerDcomp
from common.shared.models import Annotation


def norm_str(s: Any) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return str(s).strip()


def parse_date(v: Any) -> Optional[Any]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    dt = pd.to_datetime(v, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return None
    return dt.date()


def parse_money_as_text(v: Any) -> Optional[str]:
    s = norm_str(v)
    return s if s else None


def norm_status(v: Any) -> str:
    """
    Mapeia status do Excel para PerDcomp.Status.
    PerDcomp.Status choices: RASCUNHO, TRANSMITIDO, EM_PROCESSAMENTO, DEFERIDO, INDEFERIDO,
    PARCIALMENTE_DEFERIDO, CANCELADO, VENCIDO :contentReference[oaicite:2]{index=2}
    """
    s = norm_str(v).upper()
    if not s:
        return PerDcomp.Status.RASCUNHO

    # aceita já no formato interno
    if s in {c for c, _ in PerDcomp.Status.choices}:
        return s

    # normalizações comuns vindo do Excel
    mapping = {
        "RASCUNHO": PerDcomp.Status.RASCUNHO,
        "TRANSMITIDO": PerDcomp.Status.TRANSMITIDO,
        "EM PROCESSAMENTO": PerDcomp.Status.EM_PROCESSAMENTO,
        "EM_PROCESSAMENTO": PerDcomp.Status.EM_PROCESSAMENTO,
        "DEFERIDO": PerDcomp.Status.DEFERIDO,
        "INDEFERIDO": PerDcomp.Status.INDEFERIDO,
        "PARCIALMENTE DEFERIDO": PerDcomp.Status.PARCIALMENTE_DEFERIDO,
        "PARCIALMENTE_DEFERIDO": PerDcomp.Status.PARCIALMENTE_DEFERIDO,
        "CANCELADO": PerDcomp.Status.CANCELADO,
        "VENCIDO": PerDcomp.Status.VENCIDO,
    }
    return mapping.get(s, PerDcomp.Status.RASCUNHO)


def iter_chunks(df: pd.DataFrame, batch_size: int):
    total = len(df)
    for start in range(0, total, batch_size):
        yield start, df.iloc[start : start + batch_size]


def pick_first_col(row: pd.Series, candidates: List[str]) -> Any:
    for c in candidates:
        if c in row:
            return row.get(c)
    return None


class Command(BaseCommand):
    help = "Migra PER/DCOMPs a partir de planilha Excel (bulk, sem acionar __audit__); gera anotações obrigatórias."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="data/PerDcomps.xlsx",
            help="Caminho relativo/absoluto para o Excel (default: data/PerDcomps.xlsx)",
        )
        parser.add_argument(
            "--sheet",
            type=str,
            default="PerDcomp",
            help="Nome da aba (default: PerDcomp). Ex.: 'PERDCOMPs', 'TodasPerDComp', etc.",
        )
        parser.add_argument(
            "--migration-user-id",
            type=int,
            default=1,
            help="ID do usuário que será atribuído às anotações e created_by_id",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Tamanho do lote para bulk ops (default: 500)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Executa e faz rollback ao final (não grava nada).",
        )

    def handle(self, *args, **options):
        file_path: str = options["file"]
        sheet: str = options["sheet"]
        migration_user_id: int = options["migration_user_id"]
        batch_size: int = options["batch_size"]
        dry_run: bool = options["dry_run"]

        df = pd.read_excel(file_path, sheet_name=sheet)
        total = len(df)

        ct_perdcomp = ContentType.objects.get_for_model(PerDcomp)

        created_perdcomps = 0
        updated_perdcomps = 0
        created_annotations = 0
        failed = 0

        # Campos para bulk_update no PerDcomp (bater com model) :contentReference[oaicite:3]{index=3}
        PERDCOMP_UPDATE_FIELDS = [
            "client_id",
            "created_by_id",
            "cnpj",
            "numero",
            "numero_perdcomp",
            "processo_protocolo",
            "data_transmissao",
            "data_vencimento",
            "data_competencia",
            "tributo_pedido",
            "competencia",
            "valor_pedido",
            "valor_compensado",
            "valor_recebido",
            "valor_saldo",
            "valor_selic",
            "status",
            "is_active",
        ]

        def row_to_payload(row: pd.Series) -> Dict[str, Any]:
            cnpj = norm_str(pick_first_col(row, ["cnpj", "CNPJ"]))
            numero_perdcomp = norm_str(
                pick_first_col(
                    row,
                    [
                        "n° PER/DCOMP",
                        "nº PER/DCOMP",
                        "numero_perdcomp",
                        "numeroPerdcomp",
                        "perdcomp",
                    ],
                )
            )

            # alguns excels têm um "n°" genérico; se existir, vai para campo "numero"
            numero_doc = norm_str(pick_first_col(row, ["n°", "nº", "numero", "Número"]))

            processo_protocolo = norm_str(
                pick_first_col(
                    row, ["processoProtocolo", "processo_protocolo", "protocolo"]
                )
            )

            data_transmissao = parse_date(
                pick_first_col(
                    row, ["dataTransmissao", "data_transmissao", "transmissao"]
                )
            )
            data_vencimento = parse_date(
                pick_first_col(row, ["dataVencimento", "data_vencimento", "vencimento"])
            )
            data_competencia = parse_date(
                pick_first_col(row, ["dataCompetencia", "data_competencia"])
            )

            tributo_pedido = norm_str(
                pick_first_col(row, ["tributoPedido", "tributo_pedido", "tributo"])
            )
            competencia = norm_str(pick_first_col(row, ["competencia", "Competência"]))

            valor_pedido = parse_money_as_text(
                pick_first_col(
                    row, ["valorPedido", "valor_pedido", "valor", "valor_pedido_total"]
                )
            )

            payload = dict(
                cnpj=cnpj,
                numero_perdcomp=numero_perdcomp
                or None,  # model tem default; mas vamos respeitar o excel se tiver
                numero=numero_doc or None,
                processo_protocolo=processo_protocolo or None,
                data_transmissao=data_transmissao,
                data_vencimento=data_vencimento,
                data_competencia=data_competencia,
                tributo_pedido=tributo_pedido,
                competencia=competencia or None,
                valor_pedido=valor_pedido
                or "0",  # campo é obrigatório :contentReference[oaicite:4]{index=4}
                valor_compensado=parse_money_as_text(
                    pick_first_col(row, ["valorCompensado", "valor_compensado"])
                ),
                valor_recebido=parse_money_as_text(
                    pick_first_col(row, ["valorRecebido", "valor_recebido"])
                ),
                valor_saldo=parse_money_as_text(
                    pick_first_col(row, ["valorSaldo", "valor_saldo"])
                ),
                valor_selic=parse_money_as_text(
                    pick_first_col(row, ["valorSelic", "valor_selic"])
                ),
                status=norm_status(pick_first_col(row, ["status", "Status"])),
                is_active=True,
                created_by_id=migration_user_id,
            )

            return payload

        def row_to_note(row: pd.Series) -> Optional[str]:
            # Observações: tentamos várias grafias
            obs = norm_str(
                pick_first_col(
                    row,
                    [
                        "observacoes",
                        "observações",
                        "OBSERVAÇÕES",
                        "observacao",
                        "observação",
                        "Obs",
                        "OBS",
                    ],
                )
            )
            return obs if obs else None

        def process_chunk(chunk_df: pd.DataFrame) -> Tuple[int, int, int, int]:
            nonlocal failed

            rows: List[pd.Series] = []
            cnpjs: List[str] = []
            numeros_perdcomp: List[str] = []

            # Pré-validação + coleta chaves
            for _, row in chunk_df.iterrows():
                payload = row_to_payload(row)

                cnpj = payload["cnpj"]
                if not cnpj:
                    failed += 1
                    self.stderr.write("[PERDCOMP][FAIL] linha sem CNPJ")
                    continue

                # "numero_perdcomp" é a melhor chave do Excel. Se não vier, ainda dá pra criar,
                # mas perde idempotência. Aqui a gente aceita e deixa o default do model gerar.
                numero_perdcomp = payload["numero_perdcomp"] or ""

                # tributo_pedido é obrigatório no model :contentReference[oaicite:5]{index=5}
                if not payload["tributo_pedido"]:
                    failed += 1
                    self.stderr.write(
                        f"[PERDCOMP][FAIL] cnpj={cnpj} sem tributo_pedido"
                    )
                    continue

                rows.append(row)
                cnpjs.append(cnpj)
                if numero_perdcomp:
                    numeros_perdcomp.append(numero_perdcomp)

            if not rows:
                return (0, 0, 0, 0)

            # Clientes por CNPJ (map)
            clients_by_cnpj = Client.objects.filter(cnpj__in=cnpjs).in_bulk(
                field_name="cnpj"
            )

            # Carrega PerDcomps existentes por numero_perdcomp + cnpj (chave composta em memória)
            existing_map: Dict[str, PerDcomp] = {}
            if numeros_perdcomp:
                qs = PerDcomp.objects.filter(
                    numero_perdcomp__in=numeros_perdcomp, cnpj__in=cnpjs
                )
                for p in qs:
                    existing_map[f"{p.cnpj}|{p.numero_perdcomp}"] = p

            to_create: List[PerDcomp] = []
            to_update: List[PerDcomp] = []

            # annotations já existentes + pendentes de novos
            ann_to_create: List[Annotation] = []
            ann_pending_new: List[Tuple[int, Annotation]] = (
                []
            )  # idx do to_create -> annotation

            for row in rows:
                payload = row_to_payload(row)
                note = row_to_note(row)

                cnpj = payload["cnpj"]
                client = clients_by_cnpj.get(cnpj)
                if not client:
                    failed += 1
                    self.stderr.write(
                        f"[PERDCOMP][FAIL] cnpj={cnpj} não encontrado em clients"
                    )
                    continue

                payload["client_id"] = (
                    client.id
                )  # model usa bigint em vez de FK :contentReference[oaicite:6]{index=6}

                numero_perdcomp = payload["numero_perdcomp"]
                if numero_perdcomp:
                    key = f"{cnpj}|{numero_perdcomp}"
                    existing = existing_map.get(key)
                else:
                    existing = None

                if existing:
                    # update in-memory -> bulk_update
                    for k, v in payload.items():
                        setattr(existing, k, v)
                    to_update.append(existing)

                    # anotações são obrigatórias se tiver conteúdo
                    if note:
                        ann_to_create.append(
                            Annotation(
                                content_type=ct_perdcomp,
                                object_id=existing.id,
                                user_id=migration_user_id,
                                content={
                                    "tags": [],
                                    "text": note,
                                    "metadata": {
                                        "created_by": "migration",
                                    },
                                },
                            )
                        )
                else:
                    # create -> bulk_create
                    obj = PerDcomp(**payload)
                    to_create.append(obj)

                    if note:
                        ann_pending_new.append(
                            (
                                len(to_create) - 1,
                                Annotation(
                                    content_type=ct_perdcomp,
                                    object_id=0,  # preencher após bulk_create
                                    user_id=migration_user_id,
                                    content={
                                        "tags": [],
                                        "text": note,
                                        "metadata": {
                                            "created_by": "migration",
                                        },
                                    },
                                ),
                            )
                        )

            # bulk_create PerDcomp (sem disparar auditoria de save) — PerDcomp tem __audit__=True :contentReference[oaicite:7]{index=7}
            if to_create:
                PerDcomp.objects.bulk_create(to_create, batch_size=1000)

                # resolve object_id das anotações pendentes dos novos
                for idx, ann in ann_pending_new:
                    ann.object_id = to_create[idx].id
                    ann_to_create.append(ann)

            # bulk_update PerDcomp
            if to_update:
                PerDcomp.objects.bulk_update(
                    to_update, PERDCOMP_UPDATE_FIELDS, batch_size=1000
                )

            # annotations em bulk (sempre que houver conteúdo)
            if ann_to_create:
                Annotation.objects.bulk_create(ann_to_create, batch_size=2000)

            return (len(to_create), len(to_update), len(ann_to_create), 0)

        try:
            with transaction.atomic():
                for start, chunk in iter_chunks(df, batch_size):
                    c_new, c_upd, ann_created, _ = process_chunk(chunk)

                    created_perdcomps += c_new
                    updated_perdcomps += c_upd
                    created_annotations += ann_created

                    self.stdout.write(
                        f"[PERDCOMP] chunk start={start} new={c_new} upd={c_upd} ann={ann_created}"
                    )

                if dry_run:
                    raise RuntimeError("DRY_RUN_ROLLBACK")

        except RuntimeError as e:
            if str(e) == "DRY_RUN_ROLLBACK":
                self.stdout.write(
                    self.style.WARNING(
                        f"[PERDCOMP] dry-run ok (rollback feito). "
                        f"created={created_perdcomps} updated={updated_perdcomps} "
                        f"annotations={created_annotations} failed={failed} total={total}"
                    )
                )
                return
            raise

        self.stdout.write(
            self.style.SUCCESS(
                f"[PERDCOMP] done. created={created_perdcomps} updated={updated_perdcomps} "
                f"annotations={created_annotations} failed={failed} total={total}"
            )
        )
