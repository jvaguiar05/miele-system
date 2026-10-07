#!/usr/bin/env python
"""Cria um cliente em uma API local usando credenciais fornecidas pelo operador."""

import os
import sys

import requests


BASE_URL = os.getenv("MIELE_LOCAL_API_URL", "http://127.0.0.1:8000/api/v1")
USERNAME = os.getenv("MIELE_LOCAL_USERNAME")
PASSWORD = os.getenv("MIELE_LOCAL_PASSWORD")


def main() -> int:
    if not USERNAME or not PASSWORD:
        print(
            "Defina MIELE_LOCAL_USERNAME e MIELE_LOCAL_PASSWORD antes de executar."
        )
        return 2

    login = requests.post(
        f"{BASE_URL}/auth/login/",
        json={"username": USERNAME, "password": PASSWORD},
        timeout=30,
    )
    if login.status_code != 200:
        print("LOGIN_FAILED", login.status_code, login.text)
        return 1

    response = requests.post(
        f"{BASE_URL}/clients/clients/",
        headers={"Authorization": f"Bearer {login.json()['access']}"},
        json={"razao_social": "Teste Auto", "cnpj": "01.166.372/0001-55"},
        timeout=30,
    )
    print("STATUS", response.status_code)
    print(response.text)
    return 0 if response.ok else 1


if __name__ == "__main__":
    sys.exit(main())
