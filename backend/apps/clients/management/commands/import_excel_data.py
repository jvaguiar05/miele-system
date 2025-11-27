import pandas as pd
import os
import datetime
import hashlib
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.clients.models import Client, Address
from apps.perdcomps.models import PerDcomp
from common.shared.models import Annotation

User = get_user_model()


class Command(BaseCommand):
    help = "Import clients and perdcomps data from Excel file directly to database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="MieleData.xlsx",
            help="Path to Excel file (default: MieleData.xlsx in project root)",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            default=1,
            help="User ID to assign as creator of records (default: 1)",
        )
        parser.add_argument(
            "--clients-sheet",
            type=str,
            default="Clients",
            help="Name of clients sheet in Excel (default: Clients)",
        )
        parser.add_argument(
            "--perdcomps-sheet",
            type=str,
            default="PerDComps",
            help="Name of perdcomps sheet in Excel (default: PerDComps)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )
        parser.add_argument(
            "--skip-clients",
            action="store_true",
            help="Skip clients import, only import perdcomps",
        )
        parser.add_argument(
            "--skip-perdcomps",
            action="store_true",
            help="Skip perdcomps import, only import clients",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only show warnings and errors, suppress info messages",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        user_id = options["user_id"]
        dry_run = options["dry_run"]

        # If file path is relative, make it relative to project root
        if not os.path.isabs(file_path):
            # Go up from backend to project root
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            file_path = os.path.join(project_root, file_path)

        if not os.path.exists(file_path):
            raise CommandError(f"Excel file not found: {file_path}")

        # Verify user exists
        try:
            user = User.objects.get(id=user_id)
            if not options.get("quiet"):
                self.stdout.write(f"Using user: {user.username} (ID: {user_id})")
        except User.DoesNotExist:
            raise CommandError(f"User with ID {user_id} not found")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        if not options.get("quiet"):
            self.stdout.write(f"Importing from: {file_path}")

        try:
            # Import clients
            if not options["skip_clients"]:
                clients_created = self.import_clients(
                    file_path, options["clients_sheet"], user_id, dry_run
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Clients processed: {clients_created}")
                )

            # Import perdcomps
            if not options["skip_perdcomps"]:
                perdcomps_created = self.import_perdcomps(
                    file_path, options["perdcomps_sheet"], user_id, dry_run, options
                )
                self.stdout.write(
                    self.style.SUCCESS(f"PerDcomps processed: {perdcomps_created}")
                )

        except Exception as e:
            raise CommandError(f"Import failed: {str(e)}")

    def clean_value(self, val, default=None):
        """Clean values and allow default if null"""
        if pd.isna(val) or str(val).strip() == "":
            return default
        if hasattr(val, "isoformat"):
            return val.isoformat()
        return str(val).strip() if val else default

    def clean_money(self, val):
        """Ensure monetary fields are sent as numeric string or 0.00"""
        if pd.isna(val) or str(val).strip() == "":
            return "0.00"
        return str(val).replace(",", ".")

    def parse_pipe_list(self, list_a, list_b, key_a, key_b):
        """Parse pipe-separated lists into list of dicts"""
        if pd.isna(list_a) or str(list_a).strip() == "":
            return []

        items_a = [x.strip() for x in str(list_a).split("|") if x.strip()]
        items_b = []

        if not pd.isna(list_b) and str(list_b).strip():
            items_b = [x.strip() for x in str(list_b).split("|")]

        # Ensure items_b has same length as items_a
        while len(items_b) < len(items_a):
            items_b.append(None)

        return [{key_a: a, key_b: b} for a, b in zip(items_a, items_b)]

    def parse_date(self, date_val):
        """Parse date value to timezone-aware datetime object"""
        if pd.isna(date_val):
            return None

        dt = None

        if isinstance(date_val, str):
            try:
                # Try parsing common date formats
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
                    try:
                        dt = datetime.datetime.strptime(date_val, fmt)
                        break
                    except ValueError:
                        continue
            except:
                pass
        elif hasattr(date_val, "to_pydatetime"):
            dt = date_val.to_pydatetime()
        elif isinstance(date_val, datetime.datetime):
            dt = date_val
        elif isinstance(date_val, datetime.date):
            dt = datetime.datetime.combine(date_val, datetime.time.min)

        # Make timezone-aware if we have a datetime
        if dt and dt.tzinfo is None:
            dt = timezone.make_aware(dt, timezone.get_current_timezone())

        return dt

    def clean_protocolo(self, protocolo_val):
        """Clean processo_protocolo value as text"""
        if pd.isna(protocolo_val):
            return None
        return str(protocolo_val).strip()

    def import_clients(self, file_path, sheet_name, user_id, dry_run=False):
        """Import clients from Excel sheet"""
        if not dry_run:
            self.stdout.write(f"Reading clients from sheet: {sheet_name}")

        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
        except ValueError as e:
            raise CommandError(f"Error reading sheet '{sheet_name}': {e}")

        if not dry_run:
            self.stdout.write(f"Found {len(df)} client records to process")

        created_count = 0
        client_content_type = ContentType.objects.get_for_model(Client)

        for index, row in df.iterrows():
            try:
                with transaction.atomic():
                    # Parse boolean field
                    rec_jud = (
                        str(
                            self.clean_value(row.get("recuperacaoJudicial", ""), "")
                        ).lower()
                        == "verdadeiro"
                    )

                    # Handle email - ensure we have one
                    email_final = self.clean_value(row.get("emailComercial"))
                    if not email_final:
                        email_final = self.clean_value(
                            row.get("emailContato"), default="sem_email@cadastro.com"
                        )

                    cnpj = self.clean_value(row.get("cnpj"))
                    if not cnpj:
                        # Generate a fallback CNPJ if missing
                        cnpj = f"00.000.000/0001-{str(index + 1).zfill(2)}"
                        self.stdout.write(
                            self.style.WARNING(
                                f"Row {index + 1}: Generated fallback CNPJ: {cnpj}"
                            )
                        )

                    razao_social = self.clean_value(row.get("razaoSocial"))
                    if not razao_social:
                        # Generate a fallback razao_social if missing
                        razao_social = f"EMPRESA IMPORTADA {index + 1}"
                        self.stdout.write(
                            self.style.WARNING(
                                f"Row {index + 1}: Generated fallback razao_social: {razao_social}"
                            )
                        )

                    # Check if client already exists
                    if Client.objects.filter(cnpj=cnpj).exists():
                        self.stdout.write(
                            self.style.WARNING(
                                f"Row {index + 1}: Client with CNPJ {cnpj} already exists, skipping"
                            )
                        )
                        continue

                    if dry_run:
                        self.stdout.write(
                            f"Would create client: {razao_social} ({cnpj})"
                        )
                        created_count += 1
                        continue

                    # Create address first
                    address = Address.objects.create(
                        logradouro=self.clean_value(row.get("logradouro"), ""),
                        numero=self.clean_value(row.get("numero"), ""),
                        complemento=self.clean_value(row.get("complemento"), ""),
                        bairro=self.clean_value(row.get("bairro"), ""),
                        municipio=self.clean_value(row.get("municipio"), ""),
                        uf=self.clean_value(row.get("uf"), ""),
                        cep=self.clean_value(row.get("cep"), ""),
                    )

                    # Create client
                    client = Client.objects.create(
                        razao_social=razao_social,
                        nome_fantasia=self.clean_value(row.get("nomeFantasia")),
                        cnpj=cnpj,
                        inscricao_estadual=self.clean_value(
                            row.get("inscricaoEstadual")
                        ),
                        inscricao_municipal=self.clean_value(
                            row.get("inscricaoMunicipal")
                        ),
                        tipo_empresa=self.clean_value(row.get("tipoDeEmpresa")),
                        recuperacao_judicial=rec_jud,
                        telefone_comercial=self.clean_value(
                            row.get("telefoneComercial")
                        ),
                        email_comercial=email_final,
                        website=self.clean_value(row.get("webSite")),
                        telefone_contato=self.clean_value(row.get("telefoneContato")),
                        email_contato=self.clean_value(row.get("emailContato")),
                        responsavel_financeiro=self.clean_value(
                            row.get("responsavelFinanceiro")
                        ),
                        contador_responsavel=self.clean_value(
                            row.get("contadorResponsavel")
                        ),
                        regime_tributacao=self.clean_value(
                            row.get("regimeDeTributacao")
                        ),
                        contrato_social=self.clean_value(row.get("contratoSocial")),
                        ultima_alteracao_contratual=self.parse_date(
                            row.get("ultimaAlteracaoContratual")
                        ),
                        rg_cpf_socios=self.clean_value(row.get("rgCpfSocios")),
                        certificado_digital=self.clean_value(
                            row.get("certificadoDigital")
                        ),
                        autorizado_para_envio=str(
                            self.clean_value(row.get("autorizadoParaEnvio", ""), "")
                        ).lower()
                        == "verdadeiro",
                        quadro_societario=self.parse_pipe_list(
                            row.get("quadroSocietario"),
                            row.get("cargos"),
                            "nome",
                            "cargo",
                        ),
                        atividades=self.parse_pipe_list(
                            row.get("cnaes"), row.get("atividades"), "cnae", "descricao"
                        ),
                        client_status=Client.ClientStatus.ACTIVE,
                        is_active=True,
                        address=address,
                    )

                    # Create annotation if exists
                    annotation_text = self.clean_value(row.get("anotacoes"))
                    if annotation_text:
                        Annotation.objects.create(
                            content_type=client_content_type,
                            object_id=client.id,
                            user_id=user_id,
                            content={
                                "text": annotation_text,
                                "priority": "medium",
                                "tags": ["importacao_excel"],
                                "category": "observacao",
                                "metadata": {
                                    "created_by_script": True,
                                    "user_id": user_id,
                                    "source": "excel_migration",
                                },
                            },
                        )

                    created_count += 1
                    # Removed success message to reduce log verbosity

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Row {index + 1}: Error creating client - {str(e)}"
                    )
                )
                continue

        return created_count

    def import_perdcomps(
        self, file_path, sheet_name, user_id, dry_run=False, options=None
    ):
        """Import perdcomps from Excel sheet"""
        if not dry_run:
            self.stdout.write(f"Reading perdcomps from sheet: {sheet_name}")

        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
        except ValueError as e:
            raise CommandError(f"Error reading sheet '{sheet_name}': {e}")

        if not dry_run:
            self.stdout.write(f"Found {len(df)} perdcomp records to process")

        created_count = 0
        skipped_count = 0
        perdcomp_content_type = ContentType.objects.get_for_model(PerDcomp)

        for index, row in df.iterrows():
            try:
                with transaction.atomic():
                    cnpj = self.clean_value(row.get("cnpj"))
                    if not cnpj:
                        # Generate a fallback CNPJ if missing
                        cnpj = f"00.000.000/0001-{str(index + 1).zfill(2)}"
                        self.stdout.write(
                            self.style.WARNING(
                                f"Row {index + 1}: Generated fallback CNPJ: {cnpj}"
                            )
                        )

                    # Find client by CNPJ or create a placeholder
                    try:
                        client = Client.objects.get(cnpj=cnpj, deleted_at__isnull=True)
                    except Client.DoesNotExist:
                        # Create a placeholder client for this CNPJ
                        self.stdout.write(
                            self.style.WARNING(
                                f"Row {index + 1}: Creating placeholder client for CNPJ {cnpj}"
                            )
                        )

                        if not dry_run:
                            # Create placeholder address
                            placeholder_address = Address.objects.create(
                                logradouro="",
                                numero="",
                                complemento="",
                                bairro="",
                                municipio="",
                                uf="",
                                cep="",
                            )

                            # Create placeholder client
                            client = Client.objects.create(
                                razao_social=f"CLIENTE PLACEHOLDER - {cnpj}",
                                nome_fantasia=None,
                                cnpj=cnpj,
                                email_comercial="placeholder@import.com",
                                client_status=Client.ClientStatus.PENDING,
                                is_active=True,
                                address=placeholder_address,
                            )
                        else:
                            # For dry run, create a mock client object
                            client = type(
                                "MockClient", (), {"id": 999999}
                            )()  # Mock client

                    numero_perdcomp = self.clean_value(row.get("nPerDComp"))
                    processo_protocolo = self.clean_protocolo(
                        row.get("processoProtocolo")
                    )

                    # If no numero_perdcomp AND no processo_protocolo, skip
                    if not numero_perdcomp and not processo_protocolo:
                        if not options.get("quiet"):
                            self.stdout.write(
                                self.style.WARNING(
                                    f"Row {index + 1}: Missing both numero_perdcomp and processo_protocolo, skipping"
                                )
                            )
                        skipped_count += 1
                        continue

                    # Check for duplicates ONLY if numero_perdcomp exists
                    # Don't consider empty numero_perdcomp as duplicates
                    if (
                        numero_perdcomp
                    ):  # Only check duplicates if numero_perdcomp has a value
                        if PerDcomp.objects.filter(
                            numero_perdcomp=numero_perdcomp, cnpj=cnpj
                        ).exists():
                            if not options.get("quiet"):
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"Row {index + 1}: PerDcomp {numero_perdcomp} for CNPJ {cnpj} already exists, skipping (duplicate numero_perdcomp)"
                                    )
                                )
                            skipped_count += 1
                            continue

                    # Handle dates with fallback logic
                    dt_competencia = self.parse_date(row.get("dataCompetencia"))
                    if not dt_competencia:
                        dt_competencia = self.parse_date(row.get("dataTransmissao"))
                    if not dt_competencia:
                        dt_competencia = timezone.now().date()

                    dt_vencimento = self.parse_date(row.get("dataVencimento"))
                    if not dt_vencimento:
                        dt_vencimento = timezone.now()

                    dt_transmissao = self.parse_date(row.get("dataTransmissao"))

                    if dry_run:
                        identifier = (
                            numero_perdcomp
                            if numero_perdcomp
                            else f"protocolo:{processo_protocolo}"
                        )
                        self.stdout.write(
                            f"Would create perdcomp: {identifier} for {cnpj}"
                        )
                        created_count += 1
                        continue

                    # Create perdcomp
                    perdcomp = PerDcomp.objects.create(
                        client_id=client.id,
                        created_by_id=user_id,
                        cnpj=cnpj,
                        numero=self.clean_value(row.get("numero"), ""),
                        numero_perdcomp=numero_perdcomp,
                        processo_protocolo=processo_protocolo,
                        data_transmissao=dt_transmissao,
                        data_vencimento=dt_vencimento,
                        data_competencia=dt_competencia,
                        tributo_pedido=self.clean_value(row.get("tributoPedido"), ""),
                        competencia=self.clean_value(row.get("competencia"), "Mensal"),
                        valor_pedido=self.clean_money(row.get("valorPedido")),
                        valor_compensado=self.clean_money(row.get("valorCompensado")),
                        valor_recebido=self.clean_money(row.get("valorRecebido")),
                        valor_saldo=self.clean_money(row.get("valorSaldo")),
                        valor_selic=self.clean_money(row.get("valorSelic")),
                        status=PerDcomp.Status.TRANSMITIDO,
                        is_active=True,
                    )

                    # Create annotation if exists
                    annotation_text = self.clean_value(row.get("anotacoes"))
                    if annotation_text:
                        Annotation.objects.create(
                            content_type=perdcomp_content_type,
                            object_id=perdcomp.id,
                            user_id=user_id,
                            content={
                                "text": annotation_text,
                                "priority": "medium",
                                "tags": ["importacao_excel"],
                                "category": "analise",
                                "metadata": {
                                    "created_by_script": True,
                                    "user_id": user_id,
                                    "source": "excel_migration",
                                },
                            },
                        )

                    created_count += 1
                    # Removed success message to reduce log verbosity

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Row {index + 1}: Error creating perdcomp - {str(e)}"
                    )
                )
                continue

        return created_count
