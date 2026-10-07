import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools import miele_ocr_local as tool


CNPJ = "19818301000155"
PROTOCOL = "270536767316042611193690"
RECEIPT_TEXT = f"""RECEITA FEDERAL DO BRASIL
RECIBO DE ENTREGA DO PEDIDO DE RESSARCIMENTO
PER/DCOMP WEB
DADOS DO SOLICITANTE
CNPJ: 19.818.301/0001-55
Nome Empresarial: EMPRESA DE TESTE
DADOS DO PEDIDO DE RESSARCIMENTO
Tipo de Documento: Original
Data de Transmissão: 17/04/2026
Número do Documento: 27053.67673.160426.1.1.19-3690
Versão: 8.32
Valor do Pedido: 1.000,00
"""


class PackageChunkTests(unittest.TestCase):
    def make_item(self, root, index, *, size=1, pages=1, extraction_size=2):
        extraction = root / f"extraction-{index}.json"
        extraction.write_bytes(b"x" * extraction_size)
        return {
            "protocol": f"{index:024d}",
            "name": f"doc-{index}.pdf",
            "sha256": f"{index:064x}",
            "size": size,
            "pages": pages,
            "extraction_file": extraction,
        }

    def assert_split(self, items):
        self.assertEqual([len(chunk) for chunk in tool.chunks_for(items)], [1, 1])

    def test_chunks_respect_file_byte_page_and_extraction_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            count_items = [self.make_item(root, index) for index in range(50)]
            self.assertEqual([len(chunk) for chunk in tool.chunks_for(count_items)], [49, 1])

            self.assert_split([
                self.make_item(root, 100, size=23 * 1024 * 1024),
                self.make_item(root, 101, size=23 * 1024 * 1024),
            ])
            self.assert_split([
                self.make_item(root, 102, pages=300),
                self.make_item(root, 103, pages=300),
            ])
            extraction_unit = 1536 * 1024  # 1,5 MB; abaixo do limite individual de 2 MB.
            extraction_items = [
                self.make_item(root, 104 + index, extraction_size=extraction_unit)
                for index in range(7)
            ]
            self.assertEqual(
                [len(chunk) for chunk in tool.chunks_for(extraction_items)],
                [6, 1],
            )

            exactly_ten_mb = [
                self.make_item(root, 120 + index, extraction_size=2 * 1024 * 1024)
                for index in range(5)
            ]
            self.assertEqual(
                [len(chunk) for chunk in tool.chunks_for(exactly_ten_mb)],
                [5],
            )

    def test_compact_argument_validation(self):
        parser = tool.bounded_int(1, 4)
        self.assertEqual(parser("2"), 2)
        with self.assertRaises(tool.argparse.ArgumentTypeError):
            parser("5")


class GeneratedPackageTests(unittest.TestCase):
    def test_written_package_is_accepted_by_the_production_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "packages"
            destination.mkdir()
            source = root / "receipt.pdf"
            raw = b"%PDF-1.4\nlocal-test-original"
            source.write_bytes(raw)
            sha256 = hashlib.sha256(raw).hexdigest()
            extraction = root / "extraction.json"
            extraction.write_text(json.dumps({
                "schema": tool.EXTRACTION_SCHEMA,
                "schema_version": tool.SCHEMA_VERSION,
                "sha256": sha256,
                "pages": [RECEIPT_TEXT],
                "text_source": "native",
                "ocr": None,
            }), encoding="utf-8")
            item = {
                "source": source,
                "name": source.name,
                "sha256": sha256,
                "size": len(raw),
                "pages": 1,
                "protocol": PROTOCOL,
                "extraction_file": extraction,
            }

            package, package_id = tool.write_package(
                destination, CNPJ, 1, [item], datetime.now(timezone.utc).isoformat()
            )

            self.assertTrue(package.is_file())
            self.assertTrue(package_id)
            with zipfile.ZipFile(package) as archive:
                loaded = tool.load_ocr_package(archive)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["sha256"], sha256)

    @patch.object(tool, "file_sha256", return_value="a" * 64)
    @patch.object(tool, "collect_pdfs")
    @patch.object(tool, "process_pdf")
    def test_main_returns_nonzero_when_no_package_is_created(self, process, collect, _hash):
        source = Path("unidentified.pdf")
        collect.return_value = [source]
        process.return_value = {
            "source": source,
            "name": source.name,
            "status": "review",
            "issues": ["CNPJ titular não identificado com segurança."],
        }
        with tempfile.TemporaryDirectory() as directory:
            result = tool.main([str(source), "--output", directory])
        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
