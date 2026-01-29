import re
from typing import Any, List, Dict, Optional, Tuple

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.contenttypes.models import ContentType

from apps.clients.models import Client, Address
from common.shared.models import Annotation


PIPE_SPLIT = re.compile(r"\s*\|\s*")


def only_digits(s: Any) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return re.sub(r"\D+", "", str(s))


def norm_str(s: Any) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return str(s).strip()


def parse_bool(v: Any) -> bool:
    s = norm_str(v).lower()
    if s in ("", "0", "false", "falso", "nao", "não", "n", "no", "nan", "null", "none"):
        return False
    if s in ("1", "true", "verdadeiro", "sim", "s", "yes", "y"):
        return True
    try:
        return float(s) != 0
    except Exception:
        return False


def parse_pipe_list(s: Any) -> List[str]:
    raw = norm_str(s)
    if not raw:
        return []
    raw = raw.strip().strip('"').strip("'")
    parts = [p.strip().strip('"').strip("'") for p in PIPE_SPLIT.split(raw)]
    return [p for p in parts if p]


def parse_quadro_societario(names_raw: Any, cargos_raw: Any) -> List[Dict[str, str]]:
    names = parse_pipe_list(names_raw)
    cargos = parse_pipe_list(cargos_raw)
    out: List[Dict[str, str]] = []

    n = min(len(names), len(cargos))
    for i in range(n):
        nome = names[i]
        cargo_txt = cargos[i]

        if "-" in cargo_txt:
            _, cargo_desc = cargo_txt.split("-", 1)
            cargo_desc = cargo_desc.strip()
        else:
            cargo_desc = cargo_txt.strip()

        if nome or cargo_desc:
            out.append({"nome": nome, "cargo": cargo_desc})

    return out


def parse_atividades(desc_raw: Any, cnaes_raw: Any) -> List[Dict[str, str]]:
    descs = parse_pipe_list(desc_raw)
    cnaes = parse_pipe_list(cnaes_raw)
    out: List[Dict[str, str]] = []

    n = min(len(descs), len(cnaes))
    for i in range(n):
        d = descs[i].strip()
        c = cnaes[i].strip()
        if d or c:
            out.append({"cnae": c, "descricao": d})

    return out


def parse_date(v: Any) -> Optional[Any]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    dt = pd.to_datetime(v, errors="coerce", dayfirst=True)
    if pd.isna(dt):
        return None
    return dt.date()


def norm_regime_tributacao(v: Any) -> Optional[str]:
    s = norm_str(v).lower()
    if not s:
        return None

    if "lucro real" in s or s == "real":
        return "lucro_real"
    if "lucro presum" in s or s == "presumido":
        return "lucro_presumido"

    if s in ("lucro_real", "lucro_presumido"):
        return s

    return None


def iter_chunks(df: pd.DataFrame, batch_size: int):
    total = len(df)
    for start in range(0, total, batch_size):
        yield start, df.iloc[start : start + batch_size]


class Command(BaseCommand):
    help = "Migra clientes e endereços a partir de planilha Excel (bulk, sem acionar __audit__)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="data/Clientes.xlsx",
            help="Caminho relativo/absoluto para o Excel (default: data/Clientes.xlsx)",
        )
        parser.add_argument(
            "--migration-user-id",
            type=int,
            default=1,
            help="ID do usuário que será atribuído às anotações",
        )
        parser.add_argument(
            "--no-annotations",
            action="store_true",
            help="Não criar anotações a partir de 'anotacoes'/'documentacaoAnexa'",
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
        migration_user_id: int = options["migration_user_id"]
        create_annotations: bool = not options["no_annotations"]
        batch_size: int = options["batch_size"]
        dry_run: bool = options["dry_run"]

        df = pd.read_excel(file_path, sheet_name="Clientes")
        ct_client = ContentType.objects.get_for_model(Client)

        total = len(df)
        created_clients = 0
        updated_clients = 0
        created_addresses = 0
        updated_addresses = 0
        created_annotations = 0
        failed = 0

        # lista de campos do Client pra bulk_update (tem que bater com models)
        CLIENT_UPDATE_FIELDS = [
            "razao_social",
            "nome_fantasia",
            "inscricao_estadual",
            "inscricao_municipal",
            "tipo_empresa",
            "recuperacao_judicial",
            "telefone_comercial",
            "email_comercial",
            "website",
            "telefone_contato",
            "email_contato",
            "responsavel_financeiro",
            "contador_responsavel",
            "regime_tributacao",
            "contrato_social",
            "ultima_alteracao_contratual",
            "rg_cpf_socios",
            "certificado_digital",
            "autorizado_para_envio",
            "quadro_societario",
            "atividades",
            "address",  # para permitir atualizar endereço em bulk também (quando trocar)
        ]

        ADDRESS_UPDATE_FIELDS = [
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "municipio",
            "uf",
            "cep",
        ]

        def row_to_client_payload(row: pd.Series) -> Dict[str, Any]:
            quadro_societario = parse_quadro_societario(
                row.get("quadroSocietario"), row.get("cargos")
            )
            atividades = parse_atividades(row.get("atividades"), row.get("cnaes"))

            return dict(
                razao_social=norm_str(row.get("razaoSocial")),
                nome_fantasia=norm_str(row.get("nomeFantasia")),
                inscricao_estadual=norm_str(row.get("inscricaoEstadual")),
                inscricao_municipal=norm_str(row.get("inscricaoMunicipal")),
                tipo_empresa=norm_str(row.get("tipoDeEmpresa")),
                recuperacao_judicial=parse_bool(row.get("recuperacaoJudicial")),
                telefone_comercial=norm_str(row.get("telefoneComercial")),
                email_comercial=norm_str(row.get("emailComercial")),
                website=norm_str(row.get("webSite")),
                telefone_contato=norm_str(row.get("telefoneContato")),
                email_contato=norm_str(row.get("emailContato")),
                responsavel_financeiro=norm_str(row.get("responsavelFinanceiro")),
                contador_responsavel=norm_str(row.get("contadorResponsavel")),
                regime_tributacao=norm_regime_tributacao(row.get("regimeDeTributacao")),
                contrato_social=norm_str(row.get("contratoSocial")),
                ultima_alteracao_contratual=parse_date(
                    row.get("ultimaAlteracaoContratual")
                ),
                rg_cpf_socios=norm_str(row.get("rgCpfSocios")),
                certificado_digital=norm_str(row.get("certificadoDigital")),
                autorizado_para_envio=parse_bool(row.get("autorizadoParaEnvio")),
                quadro_societario=quadro_societario,
                atividades=atividades,
            )

        def row_to_address_payload(row: pd.Series) -> Dict[str, Any]:
            return dict(
                logradouro=norm_str(row.get("logradouro")),
                numero=norm_str(row.get("numero")),
                complemento=norm_str(row.get("complemento")),
                bairro=norm_str(row.get("bairro")),
                municipio=norm_str(row.get("municipio")),
                uf=norm_str(row.get("uf")),
                cep=norm_str(row.get("cep")),
            )

        def row_to_annotation_text(row: pd.Series) -> Optional[str]:
            note = norm_str(row.get("anotacoes"))
            doc_anexa = norm_str(row.get("documentacaoAnexa"))

            parts = []
            if note:
                parts.append(note)
            if doc_anexa:
                parts.append(f"[documentacaoAnexa] {doc_anexa}")

            if not parts:
                return None
            return "\n\n".join(parts)

        def process_chunk(
            chunk_df: pd.DataFrame,
        ) -> Tuple[int, int, int, int, int, int]:
            nonlocal failed

            # 1) Normaliza CNPJs do chunk
            rows = []
            cnpjs = []
            for _, row in chunk_df.iterrows():
                cnpj = norm_str(row.get("cnpj")).strip()
                if not cnpj:
                    failed += 1
                    self.stderr.write("[CLIENTS][FAIL] linha sem CNPJ")
                    continue
                rows.append(row)
                cnpjs.append(cnpj)

            if not rows:
                return (0, 0, 0, 0, 0, 0)

            # 2) Carrega existentes (por CNPJ)
            existing_by_cnpj = (
                Client.objects.filter(cnpj__in=cnpjs)
                .select_related("address")
                .in_bulk(field_name="cnpj")
            )

            # 3) Separa create/update
            addresses_to_create: List[Address] = []
            new_clients_to_create: List[Client] = []
            existing_clients_to_update: List[Client] = []
            existing_addresses_to_update: List[Address] = []
            annotations_to_create: List[Annotation] = []

            # guarda pares (row, addr_index) pra setar address no client após bulk_create de Address
            pending_new: List[Tuple[pd.Series, int]] = []

            for row in rows:
                cnpj = norm_str(row.get("cnpj")).strip()
                client_payload = row_to_client_payload(row)
                addr_payload = row_to_address_payload(row)

                existing = existing_by_cnpj.get(cnpj)

                if existing:
                    # ---- UPDATE (sem save) ----
                    # atualiza address existente (bulk_update)
                    if existing.address_id:
                        addr_obj = existing.address
                        for k, v in addr_payload.items():
                            setattr(addr_obj, k, v)
                        existing_addresses_to_update.append(addr_obj)
                    else:
                        # não tinha endereço: cria novo e depois aponta no client via bulk_update
                        addr_obj = Address(**addr_payload)
                        addresses_to_create.append(addr_obj)
                        pending_new.append((row, len(addresses_to_create) - 1))

                    # atualiza campos do client no objeto e bulk_update depois
                    for k, v in client_payload.items():
                        setattr(existing, k, v)
                    existing_clients_to_update.append(existing)

                else:
                    # ---- CREATE (sem save) ----
                    addr_obj = Address(**addr_payload)
                    addresses_to_create.append(addr_obj)
                    pending_new.append((row, len(addresses_to_create) - 1))

                    # cria client depois de ter addr.id
                    pass

                if create_annotations:
                    text = row_to_annotation_text(row)
                    if text:
                        if existing:
                            annotations_to_create.append(
                                Annotation(
                                    content_type=ct_client,
                                    object_id=existing.id,
                                    user_id=migration_user_id,
                                    content={
                                        "text": text,
                                        "source": "migration",
                                        "kind": "client_note",
                                    },
                                )
                            )
                        else:
                            pass

            # 4) bulk_create addresses
            if addresses_to_create:
                Address.objects.bulk_create(addresses_to_create, batch_size=2000)

            # 5) Para rows novos: cria Clients em bulk já com address preenchido
            new_annotations_late: List[Annotation] = []
            for row, addr_idx in pending_new:
                cnpj = norm_str(row.get("cnpj")).strip()
                existing = existing_by_cnpj.get(cnpj)

                if existing:
                    if not existing.address_id:
                        existing.address = addresses_to_create[addr_idx]
                    continue

                payload = row_to_client_payload(row)
                addr_obj = addresses_to_create[addr_idx]

                client_obj = Client(cnpj=cnpj, address=addr_obj, **payload)
                new_clients_to_create.append(client_obj)

                if create_annotations:
                    text = row_to_annotation_text(row)
                    if text:
                        # cria depois de client ter id (após bulk_create)
                        # vamos anexar na fase seguinte
                        new_annotations_late.append(
                            Annotation(
                                content_type=ct_client,
                                object_id=0,  # placeholder
                                user_id=migration_user_id,
                                content={
                                    "text": text,
                                    "source": "migration",
                                    "kind": "client_note",
                                },
                            )
                        )

            # 6) bulk_create clients novos
            if new_clients_to_create:
                Client.objects.bulk_create(new_clients_to_create, batch_size=1000)

                # agora preencher object_id nas annotations pendentes dos novos
                if create_annotations and new_annotations_late:
                    if len(new_annotations_late) != len(new_clients_to_create):
                        # não deveria acontecer, mas por segurança
                        pass
                    else:
                        for ann, cli in zip(
                            new_annotations_late, new_clients_to_create
                        ):
                            ann.object_id = cli.id
                        annotations_to_create.extend(new_annotations_late)

            # 7) bulk_update (sem save / sem audit)
            if existing_addresses_to_update:
                Address.objects.bulk_update(
                    existing_addresses_to_update, ADDRESS_UPDATE_FIELDS, batch_size=2000
                )

            if existing_clients_to_update:
                # garante que quem ganhou address novo (antes None) vai atualizar o FK também
                Client.objects.bulk_update(
                    existing_clients_to_update, CLIENT_UPDATE_FIELDS, batch_size=1000
                )

            # 8) annotations bulk_create
            if annotations_to_create:
                Annotation.objects.bulk_create(annotations_to_create, batch_size=2000)

            return (
                len(new_clients_to_create),
                len(existing_clients_to_update),
                len(addresses_to_create),
                len(existing_addresses_to_update),
                len(annotations_to_create),
                0,
            )

        # Execução
        try:
            with transaction.atomic():
                for start, chunk in iter_chunks(df, batch_size):
                    c_new, c_upd, a_created, a_upd, ann_created, _ = process_chunk(
                        chunk
                    )

                    created_clients += c_new
                    updated_clients += c_upd
                    created_addresses += a_created
                    updated_addresses += a_upd
                    created_annotations += ann_created

                    self.stdout.write(
                        f"[CLIENTS] chunk start={start} new_clients={c_new} upd_clients={c_upd} "
                        f"addr_created={a_created} addr_upd={a_upd} ann_created={ann_created}"
                    )

                if dry_run:
                    raise RuntimeError("DRY_RUN_ROLLBACK")
        except RuntimeError as e:
            if str(e) == "DRY_RUN_ROLLBACK":
                self.stdout.write(
                    self.style.WARNING(
                        f"[CLIENTS] dry-run ok (rollback feito). "
                        f"created_clients={created_clients} updated_clients={updated_clients} "
                        f"created_addresses={created_addresses} updated_addresses={updated_addresses} "
                        f"created_annotations={created_annotations} failed={failed} total={total}"
                    )
                )
                return
            raise

        self.stdout.write(
            self.style.SUCCESS(
                f"[CLIENTS] done. created_clients={created_clients} updated_clients={updated_clients} "
                f"created_addresses={created_addresses} updated_addresses={updated_addresses} "
                f"created_annotations={created_annotations} failed={failed} total={total}"
            )
        )
