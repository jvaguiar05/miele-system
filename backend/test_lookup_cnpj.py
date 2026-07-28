#!/usr/bin/env python
"""Test script for CNPJ lookup endpoint."""

import os
import django
import json
import requests

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.dev")
django.setup()

# Get JWT token from superuser
from apps.identity.models import User

admin_user = User.objects.filter(is_staff=True).first()
if not admin_user:
    print("❌ No admin user found")
    exit(1)

# Create JWT token manually
from rest_framework_simplejwt.tokens import RefreshToken

refresh = RefreshToken.for_user(admin_user)
access_token = str(refresh.access_token)

print(f"✅ Got access token for user: {admin_user.username}")

# Test the lookup endpoint
BASE_URL = "http://127.0.0.1:8000/api/v1/clients/clients"
CNPJ = "01.166.372/0001-55"

headers = {
    "Authorization": f"Bearer {access_token}",
    "Accept": "application/json",
}

url = f"{BASE_URL}/lookup-cnpj/?cnpj={CNPJ}"

print(f"\n🔍 Testing CNPJ lookup endpoint...")
print(f"URL: GET {url}\n")

response = requests.get(url, headers=headers)
print(f"Status: {response.status_code}\n")
print(f"Response:\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
