import requests, json

login = requests.post('http://127.0.0.1:8000/api/v1/auth/login/', json={'username':'admin','password':'AdminPass123!'})
if login.status_code != 200:
    print('LOGIN_FAILED', login.status_code, login.text)
    raise SystemExit(1)
access = login.json().get('access')
headers = {'Authorization': f'Bearer {access}', 'Content-Type': 'application/json'}
cnpj = '01.166.372/0001-55'
data = {'razao_social':'Teste Auto','cnpj': cnpj}
r = requests.post('http://127.0.0.1:8000/api/v1/clients/clients/', headers=headers, json=data)
print('STATUS', r.status_code)
try:
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))
except Exception:
    print(r.text)
