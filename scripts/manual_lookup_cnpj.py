#!/usr/bin/env python
"""Consulta o endpoint local de CNPJ com um token fornecido pelo operador."""

import os
import sys

import requests


BASE_URL = os.getenv("MIELE_LOCAL_API_URL", "http://127.0.0.1:8000/api/v1")
ACCESS_TOKEN = os.getenv("MIELE_LOCAL_ACCESS_TOKEN")
CNPJ = os.getenv("MIELE_TEST_CNPJ", "01.166.372/0001-55")


def main() -> int:
    if not ACCESS_TOKEN:
        print("Defina MIELE_LOCAL_ACCESS_TOKEN antes de executar.")
        return 2

    response = requests.get(
        f"{BASE_URL}/clients/clients/lookup-cnpj/",
        params={"cnpj": CNPJ},
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        timeout=30,
    )
    print("STATUS", response.status_code)
    print(response.text)
    return 0 if response.ok else 1


if __name__ == "__main__":
    sys.exit(main())
