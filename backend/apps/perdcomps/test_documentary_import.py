import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch
import zipfile

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, SimpleTestCase, override_settings
from django.test import TransactionTestCase
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from apps.clients.models import Client
from .import_parser import parse_pages, digits, decimal, valid_cnpj
from .import_files import ingest, extract_pdf, ImportProblem
from .import_service import (build_preview, publish, apply_reviews, build_reprocess_preview,
    reprocess_documents)
from .financial import operational_balance
from .import_storage import standardized_drive_name
from .document_models import (ImportedDocument, ImportedFile, DocumentaryCredit, DocumentDebt,
    DocumentCreditComponent, DocumentRelation, ImportBatch, DocumentReview, DocumentUtilization)
from .document_models import ManualImportIssue
from .models import PerDcomp

CNPJ = "19.818.301/0001-55"
OTHER = "23.451.982/0001-33"
P1 = "27053.67673.160426.1.1.19-3690"
P2 = "08084.82022.170426.1.3.19-1700"
P3 = "08085.82022.180426.1.3.19-1701"


def demo(protocol=P1, cnpj=CNPJ, reference=None, retifies=None, debt=False):
    text = f"""Receita Federal do Brasil
PEDIDO DE RESTITUIÇÃO, RESSARCIMENTO OU REEMBOLSO E DECLARAÇÃO DE COMPENSAÇÃO  PERDCOMP  8.33
CNPJ  {cnpj}  {protocol}
DADOS INICIAIS
Nome Empresarial  EMPRESA DE TESTE
Data de Criação  16/04/2026
Data de Transmissão  17/04/2026
Tipo de Documento  {'Declaração de Compensação' if debt else 'Pedido de Ressarcimento'}
Tipo de Crédito  Cofins Não-Cumulativa - Ressarc/Compens - PA após jan/2014
PER/DCOMP Retificador  {'Sim' if retifies else 'Não'}
Crédito Oriundo de Ação Judicial  Não
Informado em Outro PER/DCOMP  {'Sim' if reference else 'Não'}
Crédito de Sucedida  Não
Ano  2026
Trimestre  1º Trimestre
Valor Original do Crédito Inicial  1.000,00
"""
    if reference:
        text += f"Nº do PER/DCOMP Inicial  {reference}\n"
    if retifies:
        text += f"Nº do PER/DCOMP Retificado  {retifies}\n"
    if debt:
        text += """Crédito Original na Data de Entrega  1.000,00
Crédito Atualizado  1.000,00
Total dos Débitos deste Documento  100,00
Total do Crédito Original Utilizado neste Documento  100,00
Saldo do Crédito Original  900,00
Selic Acumulada  0,00%
001. Débito CP Patronal
CNPJ do Detentor do Débito  19.818.301/0001-55
Grupo de Tributo  CP Patronal
Código da Receita/Denominação  1138-04 - CP PATRONAL - CONTRIBUINTES INDIVIDUAIS
Período de Apuração  Março de 2026
Periodicidade  Mensal
Data de Vencimento do Tributo/Quota  20/04/2026
Número do Recibo de Transmissão DCTFWeb  050000469728382
Data de Transmissão DCTFWeb  16/04/2026
Categoria DCTFWeb  Geral
Periodicidade DCTFWeb  Mensal
Principal  100,00
Multa  0,00
Juros  0,00
Total  100,00
TOTAL  100,00
"""
    else:
        text += """Crédito Passível de Ressarcimento  1.000,00
Valor do Pedido de Ressarcimento  1.000,00
CONSOLIDAÇÃO DOS CRÉDITOS
0001. Código do Crédito  201 - Crédito de teste
Valor do Crédito Apurado  1.000,00
Valor das Deduções ou Descontos  0,00
Valor Utilizado em Dcomps Anteriores  0,00
Saldo do Crédito  1.000,00
Valor do Crédito Utilizado Neste Documento  1.000,00
TOTAL
VALOR DO CRÉDITO APURADO  1.000,00
CRÉDITOS APURADOS
Valor do Crédito Apurado  1.000,00
VALORES APURADOS DO CRÉDITO
0001. Crédito apurado no mês.
Janeiro  1.000,00
TOTAIS
JANEIRO  1.000,00
"""
    return text


def receipt(protocol=P1, cnpj=CNPJ):
    return f"""Documento recebido via Internet
em 17/04/2026 às 13:56:56
Versão: 8.32
RECIBO DE ENTREGA DO
PEDIDO DE RESSARCIMENTO
RECEITA FEDERAL DO BRASIL
PER/DCOMP WEB
DADOS DO SOLICITANTE
CNPJ: {cnpj}
Nome Empresarial: EMPRESA DE TESTE
DADOS DO PEDIDO DE RESSARCIMENTO
Tipo de Documento: Original
Data de Transmissão: 17/04/2026
Número de Controle: 27.05.36.76.73
Número do Documento: {protocol}
DADOS DO CRÉDITO
Tipo de Crédito: Cofins Não-Cumulativa - Ressarcimento/Compensação - PA a partir de Janeiro de 2014
Ano: 2026
Trimestre: 1º Trimestre
Valor do Pedido: 1.000,00
"""


def retifier_receipt(protocol=P2, rectified=P1, cnpj=CNPJ):
    return f"""RECEITA FEDERAL DO BRASIL
RECIBO DE ENTREGA DO
PEDIDO DE RESSARCIMENTO
PER/DCOMP WEB
DADOS DO SOLICITANTE
CNPJ: {cnpj}
Nome Empresarial: EMPRESA DE TESTE
DADOS DO PEDIDO DE RESSARCIMENTO
Tipo de Documento: Retificador
Número do PER Retificado: {rectified}
Data de Transmissão do Pedido Retificador: 25/02/2026
Número de Controle do Pedido Retificador: 05.35.46.65.17
Número do Pedido Retificador: {protocol}
DADOS DO CRÉDITO
Tipo de Crédito: Ressarcimento de IPI
Oriundo de Ação Judicial: Não
Crédito de Sucedida: Não
Valor do Pedido: 26.376,39
Documento recebido via Internet pelo Agente Receptor SERPRO
em 25/02/2026 às 13:46:44
Versão: 8.32
"""


def entry(text, name="documento.pdf", index=0):
    raw = text.encode()
    return {"index": index, "name": name, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw),
        "pages": 1, "raw": raw, "error": None, "extraction": parse_pages([text])}


def pdf(text=None, encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=1000, height=2000)
    if text:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica"), NameObject("/Encoding"): NameObject("/WinAnsiEncoding")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        lines = ["BT /F1 10 Tf 12 TL 20 1950 Td"]
        for line in text.splitlines():
            lines.append("(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*")
        stream.set_data(("\n".join(lines) + "\nET").encode("cp1252"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("test-password")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def local_ocr_package(text=None, manifest_cnpj=CNPJ, expected_sha=None, extra_member=False, text_source="ocr"):
    text = text or receipt()
    raw = pdf(text)
    actual_sha = hashlib.sha256(raw).hexdigest()
    declared_sha = expected_sha or actual_sha
    extraction_path = f"extracoes/{declared_sha}.json"
    pdf_path = f"originais/001_{declared_sha[:12]}_documento.pdf"
    extraction = {
        "schema": "miele.perdcomp.ocr-extraction",
        "schema_version": 1,
        "sha256": declared_sha,
        "pages": [text],
        "text_source": text_source,
        "ocr": {
            "engine": "rapidocr-local-test",
            "pages": 1,
            "recognized_pages": 1,
            "confidence": 0.99,
            "minimum_confidence": 0.98,
        } if text_source == "ocr" else None,
    }
    manifest = {
        "schema": "miele.perdcomp.ocr-package",
        "schema_version": 1,
        "package_id": "5e658b2a-3de5-4f6f-8a77-d3a5cd21bbd3",
        "created_at": "2026-10-06T12:00:00+00:00",
        "client_cnpj": digits(manifest_cnpj),
        "tool": {"name": "miele-ocr-local", "version": "1.0.0", "parser_version": "test"},
        "files": [{
            "original_name": "documento.pdf",
            "path": pdf_path,
            "extraction_path": extraction_path,
            "sha256": declared_sha,
            "size": len(raw),
            "pages": 1,
        }],
    }
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("miele-ocr-manifest.json", json.dumps(manifest).encode())
        archive.writestr(pdf_path, raw)
        archive.writestr(extraction_path, json.dumps(extraction).encode())
        if extra_member:
            archive.writestr("nao-declarado.txt", b"blocked")
    return content.getvalue()


class ParserTests(SimpleTestCase):
    def test_demo_and_receipt_identity(self):
        for text in (demo(), receipt()):
            result = parse_pages([text])
            self.assertEqual(result["status"], "ready", result["issues"])
            self.assertEqual(result["fields"]["protocol"], P1)
            self.assertEqual(result["fields"]["cnpj"], CNPJ)

    def test_version_82_demonstrative_and_820_receipt_are_supported(self):
        for text, expected_version in (
            (demo().replace("PERDCOMP  8.33", "PERDCOMP  8.2"), "8.2"),
            (receipt().replace("Versão: 8.32", "Versão: 8.20"), "8.20"),
        ):
            with self.subTest(version=expected_version):
                result = parse_pages([text])
                self.assertEqual(result["status"], "ready", result["issues"])
                self.assertEqual(result["fields"]["version"], expected_version)

        unknown = parse_pages([receipt().replace("Versão: 8.32", "Versão: 8.21")])
        self.assertEqual(unknown["status"], "review")
        self.assertIn("Leiaute não homologado", unknown["issues"][0])

    def test_ocr_quarter_ordinal_variants_are_normalized(self):
        for symbol in ("º", "°", "o"):
            with self.subTest(symbol=symbol):
                result = parse_pages([receipt().replace("1º Trimestre", f"1{symbol} Trimestre")])
                self.assertEqual(result["status"], "ready", result["issues"])
                self.assertEqual(result["fields"]["quarter"], "1º Trimestre")
                self.assertEqual(result["evidence"]["quarter"]["value"], "1º Trimestre")

    def test_zero_is_not_missing(self):
        result = parse_pages([demo(P2, reference=P1, debt=True)])
        self.assertEqual(result["fields"]["declared_selic"], "0.00")
        self.assertIsNone(result["fields"]["requested"])
        self.assertEqual(result["debts"][0]["fine"], "0.00")

    def test_retifier_receipt_identifies_owner_current_and_previous_protocol(self):
        result = parse_pages([retifier_receipt()])
        self.assertEqual(result["status"], "ready", result["issues"])
        self.assertEqual(result["fields"]["cnpj"], CNPJ)
        self.assertEqual(result["fields"]["protocol"], P2)
        self.assertEqual(result["fields"]["transmitted_on"], "2026-02-25")
        self.assertEqual(result["fields"]["control"], "05.35.46.65.17")
        self.assertEqual(result["fields"]["revision_kind"], "retificadora")
        self.assertEqual(result["fields"]["name"], "EMPRESA DE TESTE")
        self.assertIn({"kind": "rectifies", "protocol": P1}, result["relations"])

    def test_compensated_values_override_original_debt_principal(self):
        text = demo(P2, reference=P1, debt=True)
        text = text.replace("Total dos Débitos deste Documento  100,00", "Total dos Débitos deste Documento  749,00")
        text = text.replace("Total do Crédito Original Utilizado neste Documento  100,00", "Total do Crédito Original Utilizado neste Documento  749,00")
        text = text.replace("Saldo do Crédito Original  900,00", "Saldo do Crédito Original  251,00")
        text = text.replace(
            "Principal  100,00\nMulta  0,00\nJuros  0,00\nTotal  100,00",
            "Principal  1.497,99\nValores Compensados :\nPrincipal  749,00\nJuros  0,00\nTotal  749,00",
        )
        result = parse_pages([text])
        self.assertEqual(result["status"], "ready", result["issues"])
        debt = result["debts"][0]
        self.assertEqual(debt["original_principal"], "1497.99")
        self.assertEqual(debt["principal"], "749.00")
        self.assertEqual(debt["fine"], "0.00")
        self.assertEqual(debt["interest"], "0.00")
        self.assertEqual(debt["total"], "749.00")
        self.assertIn("Zero inferido", result["evidence"]["debts.1.fine"]["reason"])

    def test_decimal_and_cnpj(self):
        self.assertEqual(decimal("1.645.677,17"), "1645677.17")
        self.assertTrue(valid_cnpj(CNPJ))
        self.assertFalse(valid_cnpj("00000000000000"))
        with self.assertRaises(ValueError):
            decimal("1,234.56")
        with self.assertRaises(ValueError):
            decimal("999999999999999999999,99")

    def test_native_legacy_never_uses_retified_number(self):
        for text in (demo().replace("PERDCOMP  8.33", "PER/DCOMP 7.1"), "PER/DCOMP 7.1\n" + "Cabeçalho " * 20 + "Nº do PER/DCOMP Retificado " + P1):
            result = parse_pages([text])
            self.assertEqual(result["status"], "review")
            self.assertNotIn("protocol", result["fields"])

    def test_no_text(self):
        self.assertEqual(parse_pages([""])["status"], "no_text")

    def test_components_not_repeated_totals(self):
        result = parse_pages([demo()])
        self.assertEqual(len(result["components"]), 1)
        self.assertEqual(result["components"][0]["assessed"], "1000.00")
        self.assertEqual(result["components"][0]["months"], {"Janeiro": "1000.00"})

    def test_multiple_components(self):
        text = demo().replace("0001. Código", "0002. Código", 1)
        block = """0001. Código do Crédito  101 - Outro componente
Valor do Crédito Apurado  0,00
Valor das Deduções ou Descontos  0,00
Valor Utilizado em Dcomps Anteriores  0,00
Saldo do Crédito  0,00
Valor do Crédito Utilizado Neste Documento  0,00
"""
        result = parse_pages([text.replace("0002. Código", block + "0002. Código").replace("0001. Crédito apurado", "0002. Crédito apurado")])
        self.assertEqual(len(result["components"]), 2)
        self.assertEqual(result["status"], "ready", result["issues"])

    def test_monthly_blocks_bind_by_credit_code_when_subsequence_restarts(self):
        text = demo()
        text = text.replace(
            "Valor Original do Crédito Inicial  1.000,00",
            "Valor Original do Crédito Inicial  24.351,73",
        ).replace(
            "Crédito Passível de Ressarcimento  1.000,00",
            "Crédito Passível de Ressarcimento  24.351,73",
        ).replace(
            "Valor do Pedido de Ressarcimento  1.000,00",
            "Valor do Pedido de Ressarcimento  24.351,73",
        )
        original_component = """0001. Código do Crédito  201 - Crédito de teste
Valor do Crédito Apurado  1.000,00
Valor das Deduções ou Descontos  0,00
Valor Utilizado em Dcomps Anteriores  0,00
Saldo do Crédito  1.000,00
Valor do Crédito Utilizado Neste Documento  1.000,00
"""
        components = """0001. Código do Crédito  201 - Crédito interno
Valor do Crédito Apurado  1.205,64
Valor das Deduções ou Descontos  0,00
Valor Utilizado em Dcomps Anteriores  0,00
Saldo do Crédito  1.205,64
Valor do Crédito Utilizado Neste Documento  1.205,64
0002. Código do Crédito  301 - Crédito de exportação
Valor do Crédito Apurado  23.146,09
Valor das Deduções ou Descontos  0,00
Valor Utilizado em Dcomps Anteriores  0,00
Saldo do Crédito  23.146,09
Valor do Crédito Utilizado Neste Documento  23.146,09
"""
        text = text.replace(original_component, components).replace(
            "VALOR DO CRÉDITO APURADO  1.000,00",
            "VALOR DO CRÉDITO APURADO  24.351,73",
        )
        original_months = """0001. Crédito apurado no mês.
Janeiro  1.000,00
TOTAIS
JANEIRO  1.000,00
"""
        monthly_blocks = """201 - Crédito interno
0001. Crédito apurado no mês.
Janeiro  0,00
Fevereiro  0,00
Março  1.205,64
301 - Crédito de exportação
0001. Crédito apurado no mês.
Janeiro  7.660,93
Fevereiro  11.382,22
Março  4.102,94
TOTAIS
JANEIRO  7.660,93
FEVEREIRO  11.382,22
MARÇO  5.308,58
"""
        result = parse_pages([text.replace(original_months, monthly_blocks)])

        self.assertEqual(result["status"], "ready", result["issues"])
        self.assertEqual(
            result["components"][0]["months"],
            {"Janeiro": "0.00", "Fevereiro": "0.00", "Março": "1205.64"},
        )
        self.assertEqual(
            result["components"][1]["months"],
            {"Janeiro": "7660.93", "Fevereiro": "11382.22", "Março": "4102.94"},
        )

    def test_debt_across_pages_and_dctf(self):
        text = demo(P2, reference=P1, debt=True)
        result = parse_pages(text.split("Principal"))
        self.assertEqual(result["status"], "review")  # missing label is not guessed
        parts = text.split("Principal")
        result = parse_pages([parts[0], "Principal" + parts[1]])
        self.assertEqual(result["status"], "ready", result["issues"])
        self.assertEqual(len(result["debts"]), 1)
        self.assertEqual(result["evidence"]["debts.1.principal"]["page"], 2)
        self.assertEqual(result["debts"][0]["dctf_receipt"], "050000469728382")

    def test_sum_disagreement(self):
        result = parse_pages([demo(P2, debt=True).replace("Principal  100,00", "Principal  101,00")])
        self.assertEqual(result["status"], "review")
        self.assertTrue(any("principal + multa" in issue for issue in result["issues"]))

    def test_two_identities_in_one_pdf_blocked(self):
        result = parse_pages([demo(), demo(P2)])
        self.assertEqual(result["status"], "review")
        self.assertIsNone(result["fields"].get("protocol"))

    def test_embedded_wrong_holder_does_not_change_principal(self):
        result = parse_pages([demo(P2, debt=True).replace("CNPJ do Detentor do Débito  " + CNPJ, "CNPJ do Detentor do Débito  " + OTHER)])
        self.assertEqual(result["fields"]["cnpj"], CNPJ)
        self.assertEqual(result["debts"][0]["holder"], OTHER)


class FileTests(SimpleTestCase):
    def test_real_pdf_worker(self):
        extracted = extract_pdf(pdf(receipt()))
        self.assertNotIn("error", extracted)
        self.assertEqual(parse_pages(extracted["pages"])["status"], "ready")

    def test_encrypted_corrupt_and_scan(self):
        self.assertIn("protegido", extract_pdf(pdf(encrypted=True))["error"])
        self.assertIn("error", extract_pdf(b"%PDF-broken"))
        entry_ = ingest([SimpleUploadedFile("scan.pdf", pdf())])[0]
        self.assertEqual(entry_["extraction"]["status"], "no_text")

    @patch("apps.perdcomps.import_files.subprocess.run")
    def test_slow_ocr_explains_the_local_package_alternative(self, run):
        run.side_effect = subprocess.TimeoutExpired("ocr", 165)
        result = extract_pdf(b"%PDF-slow-scan")
        self.assertIn("Miele OCR Local", result["error"])
        self.assertIn(".miele.zip", result["error"])

    def test_name_never_classifies(self):
        row = ingest([SimpleUploadedFile("DCOMP INSS.pdf", pdf(receipt()))])[0]
        self.assertEqual(row["extraction"]["kind"], "receipt")
        self.assertEqual(row["extraction"]["fields"]["credit_tax"], "cofins")

    def test_zip_invalid_traversal_nested_and_nonpdf(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w") as archive:
            archive.writestr("../escape.pdf", pdf())
            archive.writestr("desktop.ini", b"nothing")
            archive.writestr("backup.DBK", b"backup")
            archive.writestr("inner.zip", b"PKxx")
            archive.writestr("safe/receipt.pdf", pdf(receipt()))
        rows = ingest([SimpleUploadedFile("batch.zip", content.getvalue())])
        self.assertEqual([r["extraction"]["status"] for r in rows], ["rejected"] * 4 + ["ready"])

    def test_fake_pdf_extension(self):
        row = ingest([SimpleUploadedFile("fake.pdf", b"<script>no</script>")])[0]
        self.assertEqual(row["extraction"]["status"], "rejected")

    def test_limits(self):
        with self.assertRaises(ImportProblem):
            ingest([SimpleUploadedFile("x.pdf", b"x" * (10 * 1024 * 1024 + 1))])
        with self.assertRaises(ImportProblem):
            ingest([SimpleUploadedFile("x.pdf", b"x")] * 101)

    @patch("apps.perdcomps.import_files.time.monotonic", side_effect=[0, 0, 171, 172])
    @patch("apps.perdcomps.import_files.extract_pdf")
    def test_global_time_budget_rejects_remaining_files_without_losing_valid_ones(
            self, extractor, monotonic):
        extractor.return_value = {"pages": [receipt()], "text_source": "native", "ocr": None}
        rows = ingest([
            SimpleUploadedFile("first.pdf", pdf(receipt())),
            SimpleUploadedFile("second.pdf", pdf(receipt(protocol=P2))),
            SimpleUploadedFile("third.pdf", pdf(receipt(protocol=P3))),
        ])

        self.assertEqual(rows[0]["extraction"]["status"], "ready")
        self.assertEqual([row["extraction"]["status"] for row in rows[1:]], ["rejected", "rejected"])
        self.assertTrue(all("tempo seguro" in row["error"] for row in rows[1:]))
        extractor.assert_called_once()

    @patch("apps.perdcomps.import_files.extract_pdf")
    def test_local_ocr_package_reuses_text_and_preserves_original(self, extractor):
        package = local_ocr_package()
        row = ingest([SimpleUploadedFile("cliente.miele.zip", package)])[0]
        extractor.assert_not_called()
        self.assertEqual(row["extraction"]["status"], "ready")
        self.assertEqual(row["extraction"]["text_source"], "ocr")
        self.assertEqual(row["extraction"]["fields"]["protocol"], P1)
        self.assertEqual(row["extraction"]["local_package"]["tool"], "miele-ocr-local")
        self.assertEqual(hashlib.sha256(row["raw"]).hexdigest(), row["sha256"])

    def test_local_ocr_package_rejects_hash_cnpj_and_undeclared_member(self):
        for package in (
            local_ocr_package(expected_sha="0" * 64),
            local_ocr_package(manifest_cnpj=OTHER),
            local_ocr_package(extra_member=True),
        ):
            with self.subTest():
                with self.assertRaises(ImportProblem):
                    ingest([SimpleUploadedFile("cliente.miele.zip", package)])


class ImportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.customer = Client.objects.create(razao_social="Test Import", cnpj=CNPJ)
        self.other = Client.objects.create(razao_social="Other", cnpj=OTHER)
        self.admin = get_user_model().objects.create_user(username="import-admin", email="import@example.test", role="admin", approval_status="approved")
        self.employee = get_user_model().objects.create_user(username="import-employee", email="employee@example.test", role="employee", approval_status="approved")

    def save(self, entries, selected=None, reason="Valores e documentos conferidos pelo usuário."):
        protocols = selected or list({digits(e["extraction"]["fields"]["protocol"]) for e in entries})
        return publish(self.customer, entries, protocols, [], self.admin, reason,
            financial_confirmed=protocols)

    def test_pair_becomes_single_document(self):
        entries = [entry(demo()), entry(receipt(), index=1)]
        result = build_preview(self.customer, entries)
        self.assertEqual(len(result["groups"]), 1)
        self.assertTrue(result["groups"][0]["importable"], result["groups"][0]["issues"])
        self.save(entries)
        self.assertEqual(ImportedDocument.objects.count(), 1)
        self.assertEqual(ImportedFile.objects.count(), 2)
        self.assertEqual(DocumentCreditComponent.objects.count(), 1)
        operational = PerDcomp.objects.get()
        self.assertEqual(operational.numero_perdcomp, P1)
        self.assertEqual(operational.valor_pedido, "1000.00")
        self.assertEqual(operational.valor_compensado, "")
        self.assertEqual(operational.valor_saldo, "1000.00")
        self.assertEqual(operational.valor_solicitado, 1000)
        self.assertEqual(operational.status, PerDcomp.Status.TRANSMITIDO)
        self.assertEqual(ImportedDocument.objects.get().legacy_document_id, operational.pk)

    def test_demo_only(self):
        self.save([entry(demo())])
        self.assertEqual(ImportedDocument.objects.get().completeness, "demonstrative_only")
        self.assertEqual(DocumentaryCredit.objects.count(), 1)

    def test_receipt_only(self):
        self.save([entry(receipt())])
        doc = ImportedDocument.objects.get()
        self.assertEqual(doc.completeness, "receipt_only")
        self.assertIsNone(doc.credit_id)
        self.assertEqual(doc.financial_effect, "nao_aplicado")

    def test_same_file_twice_and_reimport(self):
        one = entry(demo())
        self.save([one, one])
        result = self.save([one])
        self.assertTrue(result["repeated"])
        self.assertEqual(ImportedFile.objects.count(), 1)
        self.assertEqual(ImportedDocument.objects.count(), 1)
        self.assertEqual(DocumentaryCredit.objects.count(), 1)

    def test_two_different_pdfs_same_protocol(self):
        self.save([entry(demo()), entry(demo() + "\nObservação", index=1)])
        self.assertEqual(ImportedDocument.objects.count(), 1)
        self.assertEqual(ImportedFile.objects.count(), 2)

    def test_missing_origin_and_later_resolution(self):
        self.save([entry(demo(P2, reference=P1, debt=True))])
        self.assertEqual(DocumentaryCredit.objects.count(), 0)
        self.assertIsNone(DocumentRelation.objects.get().target_id)
        self.save([entry(demo())])
        self.assertEqual(DocumentaryCredit.objects.count(), 1)
        self.assertEqual(len(set(ImportedDocument.objects.values_list("credit_id", flat=True))), 1)
        self.assertIsNotNone(DocumentRelation.objects.get().target_id)

    def test_two_dcomps_one_credit_out_of_order(self):
        self.save([entry(demo(P3, reference=P1, debt=True)), entry(demo(P2, reference=P1, debt=True)), entry(demo())])
        self.assertEqual(DocumentaryCredit.objects.count(), 1)
        self.assertEqual(DocumentDebt.objects.count(), 2)
        self.assertEqual(DocumentUtilization.objects.filter(applied=False).count(), 2)

    def test_multiple_retifiers_preserve_original_without_effects(self):
        entries = [entry(demo()), entry(demo(P2, retifies=P1)), entry(demo(P3, retifies=P1))]
        with self.assertRaises(ImportProblem):
            self.save(entries, reason="")
        self.assertEqual(ImportBatch.objects.count(), 0)
        self.save(entries, reason="Preservar cadeia documental para revisão posterior.")
        self.assertEqual(ImportedDocument.objects.count(), 3)
        self.assertEqual(DocumentRelation.objects.filter(kind="rectifies").count(), 2)
        self.assertEqual(ImportedDocument.objects.exclude(financial_effect="nao_aplicado").count(), 0)

    def test_wrong_cnpj(self):
        entries = [entry(demo(cnpj=OTHER))]
        result = build_preview(self.customer, entries)
        self.assertEqual(result["files"][0]["status"], "wrong_client")
        with self.assertRaises(ImportProblem):
            self.save(entries)

    def test_receipt_conflict(self):
        entries = [entry(demo()), entry(receipt().replace("1.000,00", "2.000,00"))]
        result = build_preview(self.customer, entries)
        self.assertEqual(result["groups"][0]["status"], "conflict")
        with self.assertRaises(ImportProblem):
            self.save(entries)

    def test_cycle_and_self_reference(self):
        for entries in ([entry(demo(P1, reference=P2)), entry(demo(P2, reference=P1))], [entry(demo(P1, reference=P1))]):
            with self.assertRaises(ImportProblem):
                self.save(entries)
        self.assertEqual(ImportedDocument.objects.count(), 0)

    def test_existing_database_reference(self):
        legacy = PerDcomp.objects.create(client_id=self.customer.pk, created_by_id=self.admin.pk, cnpj=CNPJ, numero_perdcomp=P1, tributo_pedido="COFINS", valor_pedido="1000")
        self.save([entry(demo(P2, reference=P1, debt=True))])
        self.assertEqual(DocumentRelation.objects.get().legacy_target_id, legacy.pk)
        self.assertEqual(DocumentaryCredit.objects.count(), 0)
        legacy.refresh_from_db()
        self.assertEqual(legacy.valor_pedido, "1000")

    def test_existing_open_record_is_updated_after_user_confirmation(self):
        existing = PerDcomp.objects.create(client_id=self.customer.pk, created_by_id=self.admin.pk, cnpj=CNPJ,
            numero_perdcomp=P1, numero="antigo", tributo_pedido="ANTIGO", competencia="antiga",
            valor_pedido="10.00", valor_compensado="", valor_recebido="", status=PerDcomp.Status.TRANSMITIDO)
        preview = build_preview(self.customer, [entry(demo())])
        self.assertEqual(preview["groups"][0]["operational"]["action"], "update")
        self.save([entry(demo())])
        existing.refresh_from_db()
        self.assertEqual(existing.valor_pedido, "1000.00")
        self.assertEqual(existing.tributo_pedido, "COFINS")
        self.assertEqual(existing.status, PerDcomp.Status.TRANSMITIDO)
        self.assertEqual(existing.valor_compensado, "")
        self.assertEqual(existing.valor_saldo, "1000.00")
        self.assertEqual(PerDcomp.objects.count(), 1)

    def test_existing_financial_values_require_confirmation_and_keep_audit(self):
        existing = PerDcomp.objects.create(client_id=self.customer.pk, created_by_id=self.admin.pk, cnpj=CNPJ,
            numero_perdcomp=P1, numero="preservar", tributo_pedido="COFINS", competencia="preservar",
            valor_pedido="777.00", valor_compensado="100.00", valor_recebido="20.00", status=PerDcomp.Status.DEFERIDO)
        preview = build_preview(self.customer, [entry(demo())])
        self.assertEqual(preview["groups"][0]["operational"]["action"], "update")
        self.assertTrue(preview["groups"][0]["operational"]["financial_confirmation_required"])
        with self.assertRaises(ImportProblem):
            publish(self.customer, [entry(demo())], [digits(P1)], [], self.employee,
                "Conferência feita pelo usuário.", financial_confirmed=[])
        self.save([entry(demo())])
        existing.refresh_from_db()
        self.assertEqual((existing.valor_pedido, existing.valor_compensado, existing.valor_recebido,
                          existing.valor_saldo, existing.status),
            ("1000.00", "100.00", "20.00", "880.00", PerDcomp.Status.DEFERIDO))
        self.assertEqual(ImportedDocument.objects.get().legacy_document_id, existing.pk)

    def test_ocr_document_requires_explicit_confirmation(self):
        scanned = entry(demo())
        scanned["extraction"]["text_source"] = "ocr"
        scanned["extraction"]["ocr"] = {"engine": "rapidocr-test", "pages": 1,
            "recognized_pages": 1, "confidence": 0.99, "minimum_confidence": 0.91}
        preview = build_preview(self.customer, [scanned])
        self.assertTrue(preview["groups"][0]["ocr_used"])
        self.assertEqual(preview["groups"][0]["ocr_confidence"], 0.99)
        with self.assertRaises(ImportProblem):
            publish(self.customer, [scanned], [digits(P1)], [], self.employee,
                "OCR conferido diretamente no documento.", ocr_confirmed=[])
        result = publish(self.customer, [scanned], [digits(P1)], [], self.employee,
            "OCR conferido diretamente no documento.", ocr_confirmed=[digits(P1)])
        self.assertEqual(result["ocr_confirmed"], 1)
        self.assertEqual(ImportedFile.objects.get().extraction["text_source"], "ocr")

    def test_retifier_creates_new_operational_and_preserves_original(self):
        original = PerDcomp.objects.create(client_id=self.customer.pk, created_by_id=self.admin.pk, cnpj=CNPJ,
            numero_perdcomp=P1, tributo_pedido="COFINS", valor_pedido="1000.00", valor_compensado="500.00",
            status=PerDcomp.Status.DEFERIDO)
        self.save([entry(demo(P2, retifies=P1))], reason="Retificadora conferida e mantida separadamente.")
        self.assertEqual(PerDcomp.objects.count(), 2)
        original.refresh_from_db()
        self.assertEqual(original.valor_compensado, "500.00")
        retifier = PerDcomp.objects.exclude(pk=original.pk).get()
        self.assertEqual(retifier.numero_perdcomp, P2)
        self.assertEqual(retifier.status, PerDcomp.Status.TRANSMITIDO)
        original.refresh_from_db()
        self.assertEqual(original.version_status, PerDcomp.VersionStatus.SUBSTITUIDA)
        self.assertEqual(original.superseded_by_id, retifier.pk)
        self.assertEqual(retifier.version_status, PerDcomp.VersionStatus.VIGENTE)

    def test_reprocesses_already_imported_document_without_new_upload(self):
        extraction = parse_pages([demo(P2, reference=P1, debt=True)])
        document = ImportedDocument.objects.create(client=self.customer, cnpj=digits(CNPJ), protocol=digits(P2),
            protocol_original=P2, modality=extraction["fields"]["modality"], revision_kind="original",
            completeness="demonstrative_only", data=extraction["fields"])
        for debt in extraction["debts"]:
            DocumentDebt.objects.create(document=document, sequence=debt["sequence"], principal=debt["principal"],
                fine=debt["fine"], interest=debt["interest"], total=debt["total"], data=debt)
        preview = build_reprocess_preview(self.customer)
        self.assertEqual(preview["counts"], {"pending": 1, "financial_confirmation": 1})
        with self.assertRaises(ImportProblem):
            reprocess_documents(self.customer, [digits(P2)], [], self.employee, "Valores conferidos pelo usuário.")
        result = reprocess_documents(self.customer, [digits(P2)], [digits(P2)], self.employee,
            "Valores conferidos pelo usuário.")
        self.assertEqual(result["operational"]["created"], 1)
        operational = PerDcomp.objects.get(numero_perdcomp=P2)
        self.assertEqual((operational.valor_compensado, operational.valor_saldo), ("100.00", "0.00"))
        self.assertEqual(operational.valor_compensado_declarado, 100)
        self.assertEqual(operational.credito_original_utilizado, 100)
        self.assertEqual(operational.saldo_credito_original, 900)

    def test_employee_can_reprocess_existing_document_through_preview(self):
        extraction = parse_pages([demo()])
        ImportedDocument.objects.create(client=self.customer, cnpj=digits(CNPJ), protocol=digits(P1),
            protocol_original=P1, modality=extraction["fields"]["modality"], revision_kind="original",
            completeness="demonstrative_only", data=extraction["fields"])
        api = APIClient(); api.force_authenticate(self.employee)
        base = f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/reprocess/"
        preview = api.get(base + "preview/")
        self.assertEqual(preview.status_code, 200, preview.data)
        confirmed = api.post(base + "confirm/", {"token": preview.data["token"], "selected": [digits(P1)],
            "financial_confirmed": [], "reason": ""}, format="json")
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(PerDcomp.objects.get().valor_saldo, "1000.00")

    def test_balance_rule_and_standard_drive_name(self):
        self.assertEqual(operational_balance("1000.00", "100.00", "20.00"), "880.00")
        with self.assertRaises(ValueError):
            operational_balance("100.00", "80.00", "30.00")
        self.save([entry(demo())])
        name = standardized_drive_name(ImportedFile.objects.select_related("client", "document").get())
        self.assertRegex(name, r"^19818301000155_PER_270536767316042611193690_2026-04-17_DEMONSTRATIVO_[A-F0-9]{12}\.pdf$")

    def test_invalid_pdf_can_be_archived_and_resolved_manually(self):
        invalid = entry("imagem sem texto suficiente")
        invalid["raw"] = pdf()
        invalid["sha256"] = hashlib.sha256(invalid["raw"]).hexdigest()
        invalid["pages"] = 1
        result = publish(self.customer, [invalid], [], [], self.admin, "", [invalid["sha256"]])
        self.assertEqual(result["manual_pending_created"], 1)
        issue = ManualImportIssue.objects.get()
        self.assertEqual(issue.status, ManualImportIssue.Status.PENDING)
        operational = PerDcomp.objects.create(client_id=self.customer.pk, created_by_id=self.admin.pk, cnpj=CNPJ,
            numero_perdcomp="MANUAL-1", tributo_pedido="COFINS", valor_pedido="100.00")
        api = APIClient(); api.force_authenticate(self.admin)
        base = f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/manual/{issue.public_id}/"
        response = api.post(base + "resolve/", {"action": "resolved", "operational_id": str(operational.public_id),
            "note": "Cadastro manual conferido com o PDF original."}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        issue.refresh_from_db()
        self.assertEqual(issue.operational_document_id, operational.pk)
        self.assertEqual(issue.status, ManualImportIssue.Status.RESOLVED)
        repeated = api.post(base + "resolve/", {"action": "dismissed",
            "note": "Tentativa concorrente de descartar a mesma pendência."}, format="json")
        self.assertEqual(repeated.status_code, 409, repeated.data)
        issue.refresh_from_db()
        self.assertEqual(issue.operational_document_id, operational.pk)
        self.assertEqual(issue.status, ManualImportIssue.Status.RESOLVED)

    def test_atomic_failure(self):
        with patch("apps.perdcomps.import_service.resolve_references", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                self.save([entry(demo())])
        self.assertEqual(ImportBatch.objects.count(), 0)
        self.assertEqual(ImportedFile.objects.count(), 0)

    def test_manual_resolution_and_audit_are_atomic(self):
        invalid = entry("imagem sem texto suficiente")
        invalid["raw"] = pdf()
        invalid["sha256"] = hashlib.sha256(invalid["raw"]).hexdigest()
        publish(self.customer, [invalid], [], [], self.admin, "", [invalid["sha256"]])
        issue = ManualImportIssue.objects.get()
        operational = PerDcomp.objects.create(client_id=self.customer.pk, created_by_id=self.admin.pk,
            cnpj=CNPJ, numero_perdcomp="MANUAL-ATOMIC", tributo_pedido="COFINS", valor_pedido="100.00")
        api = APIClient(); api.force_authenticate(self.admin)
        url = (f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/manual/"
               f"{issue.public_id}/resolve/")

        with patch("apps.perdcomps.import_views.AuditService.log_action", side_effect=RuntimeError("audit failure")):
            response = api.post(url, {"action": "resolved", "operational_id": str(operational.public_id),
                "note": "Cadastro manual conferido com o PDF original."}, format="json")

        self.assertEqual(response.status_code, 500)
        issue.refresh_from_db()
        self.assertEqual(issue.status, ManualImportIssue.Status.PENDING)
        self.assertIsNone(issue.operational_document_id)
        self.assertIsNone(issue.resolved_by_id)

    def test_database_constraints_protect_identity_and_file(self):
        self.save([entry(demo())])
        doc = ImportedDocument.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ImportedDocument.objects.create(client=self.customer, cnpj=doc.cnpj, protocol=doc.protocol)
        file = ImportedFile.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ImportedFile.objects.create(client=self.customer, document=doc, batch=file.batch, sha256=file.sha256, pages=1)

    def test_manual_correction_has_reason_and_original(self):
        entries = [entry(demo(P2, debt=True).replace("Principal  100,00", "Principal  101,00"))]
        change = {"sha256": entries[0]["sha256"], "field": "debts.1.principal", "value": "100.00", "reason": "Conferido no documento original."}
        apply_reviews(entries, [change], self.employee)
        self.assertEqual(entries[0]["extraction"]["status"], "ready")
        self.assertEqual(entries[0]["extraction"]["evidence"]["debts.1.principal"]["original_value"], "101.00")
        change["reason"] = ""
        with self.assertRaises(ImportProblem):
            apply_reviews(entries, [change], self.employee)

    def test_no_identity_override(self):
        e = entry(demo(cnpj=OTHER))
        with self.assertRaises(ImportProblem):
            apply_reviews([e], [{"sha256": e["sha256"], "field": "cnpj", "value": CNPJ, "reason": "Tentativa de troca de titular."}], self.admin)

    def test_http_permissions_stateless_preview_and_confirm(self):
        api = APIClient()
        base = f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/"
        self.assertEqual(api.get(base + "documents/").status_code, 401)
        api.force_authenticate(self.employee)
        self.assertEqual(api.post(base + "confirm/", {}, format="multipart").status_code, 400)
        payload = pdf(receipt())
        response = api.post(base + "preview/", {"files": SimpleUploadedFile("receipt.pdf", payload)}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ImportBatch.objects.count(), 0)
        data = {"files": SimpleUploadedFile("receipt.pdf", payload), "token": response.data["token"], "selected": '["' + digits(P1) + '"]'}
        confirmed = api.post(base + "confirm/", data, format="multipart")
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        file = ImportedFile.objects.get()
        self.assertEqual(bytes(file.original_content), payload)
        response = api.get(f"/api/v1/clients/{self.other.public_id}/perdcomp-imports/files/{file.public_id}/")
        self.assertEqual(response.status_code, 404)

    def test_main_import_resolves_client_from_cnpj(self):
        api = APIClient()
        api.force_authenticate(self.employee)
        payload = pdf(receipt())
        response = api.post(
            "/api/v1/perdcomps/import/preview/",
            {"files": SimpleUploadedFile("receipt.pdf", payload)},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["client_id"], str(self.customer.public_id))
        self.assertEqual(response.data["client"]["cnpj"], CNPJ)
        self.assertEqual(response.data["client"]["razao_social"], self.customer.razao_social)
        self.assertEqual(response.data["groups"][0]["fields"]["cnpj"], CNPJ)

        confirmed = api.post(
            f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/confirm/",
            {
                "files": SimpleUploadedFile("receipt.pdf", payload),
                "token": response.data["token"],
                "selected": '["' + digits(P1) + '"]',
            },
            format="multipart",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(ImportedDocument.objects.get().client, self.customer)

    def test_main_import_accepts_local_ocr_package_with_explicit_confirmation(self):
        api = APIClient()
        api.force_authenticate(self.employee)
        payload = local_ocr_package()
        preview = api.post(
            "/api/v1/perdcomps/import/preview/",
            {"files": SimpleUploadedFile("cliente.miele.zip", payload)},
            format="multipart",
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertTrue(preview.data["groups"][0]["ocr_used"])
        self.assertEqual(preview.data["groups"][0]["ocr_confidence"], 0.99)
        protocol = digits(P1)
        confirmed = api.post(
            f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/confirm/",
            {
                "files": SimpleUploadedFile("cliente.miele.zip", payload),
                "token": preview.data["token"],
                "selected": json.dumps([protocol]),
                "ocr_confirmed": json.dumps([protocol]),
                "reason": "OCR local conferido diretamente no documento original.",
            },
            format="multipart",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        stored = ImportedFile.objects.get()
        self.assertEqual(stored.extraction["text_source"], "ocr")
        self.assertEqual(stored.extraction["local_package"]["tool"], "miele-ocr-local")
        self.assertEqual(hashlib.sha256(bytes(stored.original_content)).hexdigest(), stored.sha256)

    def test_native_local_package_still_requires_human_confirmation(self):
        row = ingest([
            SimpleUploadedFile(
                "cliente.miele.zip",
                local_ocr_package(text_source="native"),
            )
        ])[0]
        preview = build_preview(self.customer, [row])

        self.assertEqual(row["extraction"]["text_source"], "native")
        self.assertEqual(
            row["extraction"]["local_package"]["extraction_source"],
            "native",
        )
        self.assertTrue(preview["groups"][0]["ocr_used"])

    def test_main_import_partitions_multiple_clients_and_confirms_one_at_a_time(self):
        api = APIClient()
        api.force_authenticate(self.employee)

        def uploads():
            return [
                SimpleUploadedFile("customer-demo.pdf", pdf(demo())),
                SimpleUploadedFile("customer-receipt.pdf", pdf(receipt())),
                SimpleUploadedFile("other.pdf", pdf(receipt(protocol=P2, cnpj=OTHER))),
            ]

        response = api.post(
            "/api/v1/perdcomps/import/preview/",
            {"files": uploads()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["selection_required"])
        self.assertEqual(response.data["counts"], {"files": 3, "clients": 2, "unassigned": 0})

        customer_option = next(
            option for option in response.data["clients"] if option["cnpj"] == digits(CNPJ)
        )
        other_option = next(
            option for option in response.data["clients"] if option["cnpj"] == digits(OTHER)
        )
        self.assertTrue(customer_option["registered"])
        self.assertEqual(customer_option["client"]["id"], str(self.customer.public_id))
        self.assertEqual(customer_option["file_count"], 2)
        self.assertEqual(customer_option["preview"]["counts"]["documents"], 1)
        self.assertEqual(customer_option["preview"]["groups"][0]["completeness"], "complete")
        self.assertEqual(other_option["file_count"], 1)

        confirmed = api.post(
            f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/confirm/",
            {
                "files": uploads(),
                "token": customer_option["preview"]["token"],
                "selected": json.dumps([digits(P1)]),
            },
            format="multipart",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(ImportedDocument.objects.count(), 1)
        self.assertEqual(ImportedDocument.objects.get().client, self.customer)
        self.assertEqual(ImportedFile.objects.count(), 2)

        confirmed = api.post(
            f"/api/v1/clients/{self.other.public_id}/perdcomp-imports/confirm/",
            {
                "files": uploads(),
                "token": other_option["preview"]["token"],
                "selected": json.dumps([digits(P2)]),
            },
            format="multipart",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(ImportedDocument.objects.count(), 2)
        self.assertEqual(ImportedFile.objects.count(), 3)

    def test_explicit_client_preview_ignores_files_from_other_known_clients(self):
        api = APIClient()
        api.force_authenticate(self.employee)

        def uploads():
            return [
                SimpleUploadedFile("customer.pdf", pdf(receipt())),
                SimpleUploadedFile("other.pdf", pdf(receipt(protocol=P2, cnpj=OTHER))),
            ]

        response = api.post(
            f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/preview/",
            {"files": uploads()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["counts"]["files"], 1)
        self.assertEqual(response.data["batch_selection"]["other_clients_ignored"], 1)
        self.assertEqual(response.data["groups"][0]["fields"]["cnpj"], CNPJ)

        confirmed = api.post(
            f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/confirm/",
            {
                "files": uploads(),
                "token": response.data["token"],
                "selected": json.dumps([digits(P1)]),
            },
            format="multipart",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(ImportedDocument.objects.count(), 1)
        self.assertEqual(ImportedFile.objects.count(), 1)
        self.assertEqual(ImportedDocument.objects.get().client, self.customer)

    def test_main_import_lists_clients_from_multiple_local_ocr_packages(self):
        api = APIClient()
        api.force_authenticate(self.employee)
        response = api.post(
            "/api/v1/perdcomps/import/preview/",
            {"files": [
                SimpleUploadedFile("customer.miele.zip", local_ocr_package()),
                SimpleUploadedFile(
                    "other.miele.zip",
                    local_ocr_package(text=receipt(protocol=P2, cnpj=OTHER), manifest_cnpj=OTHER),
                ),
            ]},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["selection_required"])
        self.assertEqual(response.data["counts"]["clients"], 2)
        for option in response.data["clients"]:
            self.assertTrue(option["preview"]["groups"][0]["ocr_used"])

    def test_main_import_marks_unregistered_client_in_mixed_batch(self):
        Client.objects.filter(pk=self.other.pk).update(deleted_at=timezone.now())
        api = APIClient()
        api.force_authenticate(self.employee)
        response = api.post(
            "/api/v1/perdcomps/import/preview/",
            {"files": [
                SimpleUploadedFile("customer.pdf", pdf(receipt())),
                SimpleUploadedFile("new-client.pdf", pdf(receipt(protocol=P2, cnpj=OTHER))),
            ]},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)
        option = next(item for item in response.data["clients"] if item["cnpj"] == digits(OTHER))
        self.assertFalse(option["registered"])
        self.assertIsNone(option["client"])
        self.assertNotIn("preview", option)

    def test_main_import_offers_structured_client_creation(self):
        Client.objects.filter(pk=self.other.pk).update(deleted_at=timezone.now())
        api = APIClient()
        api.force_authenticate(self.employee)
        response = api.post(
            "/api/v1/perdcomps/import/preview/",
            {"files": SimpleUploadedFile("new-client.pdf", pdf(receipt(protocol=P2, cnpj=OTHER)))},
            format="multipart",
        )
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(response.data["code"], "client_not_found")
        self.assertEqual(response.data["cnpj"], digits(OTHER))
        self.assertTrue(response.data["can_create_client"])

    def test_tampered_preview(self):
        api = APIClient(); api.force_authenticate(self.admin)
        base = f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/"
        response = api.post(base + "confirm/", {"token": "forged"}, format="multipart")
        self.assertEqual(response.status_code, 400)

    @patch("apps.perdcomps.import_files.extract_pdf")
    def test_confirm_rejects_extraction_that_differs_from_preview(self, extractor):
        extractor.side_effect = [
            {"pages": [receipt()], "text_source": "native", "ocr": None},
            {"pages": [receipt().replace("1.000,00", "2.000,00")],
             "text_source": "native", "ocr": None},
        ]
        api = APIClient(); api.force_authenticate(self.employee)
        base = f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/"
        payload = pdf(receipt())
        preview = api.post(base + "preview/", {
            "files": SimpleUploadedFile("receipt.pdf", payload),
        }, format="multipart")
        self.assertEqual(preview.status_code, 200, preview.data)

        confirmed = api.post(base + "confirm/", {
            "files": SimpleUploadedFile("receipt.pdf", payload),
            "token": preview.data["token"],
            "selected": json.dumps([digits(P1)]),
        }, format="multipart")

        self.assertEqual(confirmed.status_code, 400, confirmed.data)
        self.assertIn("Arquivos ou corre", confirmed.data["detail"])
        self.assertEqual(ImportBatch.objects.count(), 0)

    @override_settings(GDRIVE_CLIENT_ID="test", GDRIVE_CLIENT_SECRET="test", GDRIVE_REFRESH_TOKEN="test", GDRIVE_PERDCOMPS_FOLDER_ID="test-folder")
    def test_drive_failure_preserves_original_and_retry_does_not_duplicate(self):
        from .import_storage import sync_originals
        self.save([entry(demo())])
        queryset = ImportedFile.objects.filter(client=self.customer)
        with patch("apps.perdcomps.import_storage.GoogleDriveService") as mocked:
            mocked.return_value._get_service.side_effect = RuntimeError("OAuth unavailable")
            result = sync_originals(queryset)
        self.assertEqual(result["status"], "pending")
        self.assertTrue(ImportedFile.objects.get().original_content)
        stored = ImportedFile.objects.select_related("client", "document").get()
        raw = bytes(stored.original_content)
        properties = {"miele_client": str(self.customer.public_id), "miele_sha256": stored.sha256,
            "miele_protocol": stored.document.protocol, "miele_kind": stored.kind}
        metadata = {"id": "already-archived", "name": standardized_drive_name(stored),
            "size": str(len(raw)), "md5Checksum": hashlib.md5(raw).hexdigest(),
            "appProperties": properties, "parents": ["test-folder"], "trashed": False}
        with patch("apps.perdcomps.import_storage.GoogleDriveService") as mocked:
            mocked.return_value._get_service.return_value.files.return_value.list.return_value.execute.return_value = {"files": [metadata]}
            mocked.return_value.get_file_metadata.return_value = metadata
            result = sync_originals(queryset)
            mocked.return_value.upload_stream_metadata.assert_not_called()
        self.assertEqual(result["status"], "synced")
        stored.refresh_from_db()
        self.assertEqual(stored.drive_file_id, "already-archived")
        self.assertIsNone(stored.original_content)
        self.assertEqual(stored.drive_size, len(raw))
        self.assertIsNotNone(stored.database_released_at)
        self.assertEqual(ImportedFile.objects.count(), 1)

    @override_settings(GDRIVE_CLIENT_ID="test", GDRIVE_CLIENT_SECRET="test", GDRIVE_REFRESH_TOKEN="test", GDRIVE_PERDCOMPS_FOLDER_ID="test-folder")
    def test_verified_upload_releases_database_copy_and_drive_download_checks_hash(self):
        from .import_storage import sync_originals
        self.save([entry(demo())])
        stored = ImportedFile.objects.select_related("client", "document").get()
        raw = bytes(stored.original_content)
        properties = {"miele_client": str(self.customer.public_id), "miele_sha256": stored.sha256,
            "miele_protocol": stored.document.protocol, "miele_kind": stored.kind}
        metadata = {"id": "uploaded-file", "name": standardized_drive_name(stored),
            "size": str(len(raw)), "md5Checksum": hashlib.md5(raw).hexdigest(),
            "appProperties": properties, "parents": ["test-folder"], "trashed": False}
        with patch("apps.perdcomps.import_storage.GoogleDriveService") as mocked:
            mocked.return_value._get_service.return_value.files.return_value.list.return_value.execute.return_value = {"files": []}
            mocked.return_value.upload_stream_metadata.return_value = metadata
            mocked.return_value.get_file_metadata.return_value = metadata
            result = sync_originals(ImportedFile.objects.all())
        self.assertEqual(result["released"], 1)
        stored.refresh_from_db()
        self.assertIsNone(stored.original_content)

        api = APIClient(); api.force_authenticate(self.employee)
        url = f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/files/{stored.public_id}/"
        with patch("apps.perdcomps.import_storage.GoogleDriveService") as mocked:
            mocked.return_value.download_stream.return_value = io.BytesIO(raw)
            response = api.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), raw)

        with patch("apps.perdcomps.import_storage.GoogleDriveService") as mocked:
            mocked.return_value.download_stream.return_value = io.BytesIO(b"altered")
            response = api.get(url)
        self.assertEqual(response.status_code, 409)

    @override_settings(GDRIVE_CLIENT_ID="", GDRIVE_CLIENT_SECRET="", GDRIVE_REFRESH_TOKEN="", GDRIVE_PERDCOMPS_FOLDER_ID="")
    def test_storage_queue_status_is_visible_but_only_admin_can_run_it(self):
        self.save([entry(demo())])
        api = APIClient(); api.force_authenticate(self.employee)
        url = "/api/v1/perdcomps/import/storage/"
        response = api.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pending"], 1)
        self.assertEqual(api.post(url, {}).status_code, 403)
        api.force_authenticate(self.admin)
        response = api.post(url, {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "database")

    @override_settings(GDRIVE_CLIENT_ID="test", GDRIVE_CLIENT_SECRET="test", GDRIVE_REFRESH_TOKEN="test", GDRIVE_PERDCOMPS_FOLDER_ID="")
    def test_drive_never_falls_back_to_root_folder(self):
        from .import_storage import sync_originals
        self.save([entry(demo())])
        with patch("apps.perdcomps.import_storage.GoogleDriveService") as mocked:
            result = sync_originals(ImportedFile.objects.all())
            mocked.assert_not_called()
        self.assertEqual(result["status"], "pending")

    def test_guest_and_unapproved_user_are_blocked(self):
        api = APIClient()
        url = f"/api/v1/clients/{self.customer.public_id}/perdcomp-imports/documents/"
        self.employee.role = "guest"; self.employee.save()
        api.force_authenticate(self.employee)
        self.assertEqual(api.get(url).status_code, 403)
        self.employee.role = "employee"; self.employee.approval_status = "pending"; self.employee.save()
        self.assertEqual(api.get(url).status_code, 403)


class LocalCorpusTests(SimpleTestCase):
    def test_supplied_corpus(self):
        root = os.environ.get("PERDCOMP_CORPUS_DIR")
        if not root:
            self.skipTest("Conjunto privado não incluído no Git; informe PERDCOMP_CORPUS_DIR para validar.")
        from pypdf import PdfReader
        counts = {"ready": 0, "no_text": 0, "review": 0}
        for path in Path(root).glob("*.pdf"):
            with self.subTest(file=path.name):
                pages = [p.extract_text(extraction_mode="layout") or "" for p in PdfReader(path).pages]
                result = parse_pages(pages)
                counts[result["status"]] += 1
                if result.get("layout") == "web83":
                    self.assertEqual(result["status"], "ready", result["issues"])
                if not any(p.strip() for p in pages):
                    self.assertEqual(result["status"], "no_text")
        self.assertEqual(counts, {"ready": 36, "no_text": 44, "review": 2})


class LocalCorpusGroupingTests(TestCase):
    def test_real_pairs_match_and_debt_fields_have_evidence(self):
        root = os.environ.get("PERDCOMP_CORPUS_DIR")
        if not root:
            self.skipTest("Conjunto privado não incluído no Git.")
        from pypdf import PdfReader
        all_entries = []
        for path in Path(root).glob("*.pdf"):
            if path.stat().st_size > 200000:
                continue
            pages = [p.extract_text(extraction_mode="layout") or "" for p in PdfReader(path).pages]
            extraction = parse_pages(pages)
            if extraction.get("layout") != "web83":
                continue
            raw = path.read_bytes()
            all_entries.append({"index": len(all_entries), "name": path.name, "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw), "pages": len(pages), "raw": raw, "error": None, "extraction": extraction})
            for debt in extraction["debts"]:
                self.assertIsNotNone(debt["holder"], path.name)
                self.assertIsNotNone(debt["revenue"], path.name)
                for key, value in debt.items():
                    if value is not None:
                        self.assertIn(f"debts.{debt['sequence']}.{key}", extraction["evidence"])
        counts = []
        for cnpj in sorted({e["extraction"]["fields"]["cnpj"] for e in all_entries}):
            client = Client.objects.create(razao_social="Corpus test", cnpj=cnpj)
            matching = [e for e in all_entries if e["extraction"]["fields"].get("cnpj") == cnpj]
            preview = build_preview(client, matching)
            for group in preview["groups"]:
                self.assertTrue(group["importable"], group["issues"])
            counts.append((len(matching), len(preview["groups"])))
        self.assertEqual(sum(n for n, _ in counts), 36)
        self.assertEqual(sum(n for _, n in counts), 19)


class ConcurrentImportTests(TransactionTestCase):
    def test_concurrent_confirmation_and_retry_are_idempotent(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections, OperationalError
        client = Client.objects.create(razao_social="Concurrent", cnpj=CNPJ)
        user = get_user_model().objects.create_user(username="concurrent", email="concurrent@example.test", role="admin", approval_status="approved")
        barrier = Barrier(2)
        def attempt():
            close_old_connections()
            try:
                local_client = Client.objects.get(pk=client.pk)
                local_user = get_user_model().objects.get(pk=user.pk)
                barrier.wait(timeout=10)
                return publish(local_client, [entry(demo())], [digits(P1)], [], local_user, "")
            except (OperationalError, IntegrityError):
                # SQLite contention follows the API's 409/re-preview path.
                return "retry"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(attempt), pool.submit(attempt)
            outcomes = [first.result(timeout=20), second.result(timeout=20)]
        self.assertEqual(len(outcomes), 2)
        publish(client, [entry(demo())], [digits(P1)], [], user, "")
        self.assertEqual(ImportBatch.objects.count(), 1)
        self.assertEqual(ImportedDocument.objects.count(), 1)
        self.assertEqual(ImportedFile.objects.count(), 1)
        self.assertEqual(DocumentaryCredit.objects.count(), 1)
