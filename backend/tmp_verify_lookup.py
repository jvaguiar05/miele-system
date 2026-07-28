import requests

url = 'http://127.0.0.1:8000/api/v1/clients/lookup-cnpj/?cnpj=01.166.372/0001-55'
headers = {
    'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzg1MjU4ODEwLCJpYXQiOjE3ODUyNTc5MTAsImp0aSI6IjJlOTMwZTM3NGJkNjQ2MGJhNmYzYjNkYWI4OWRmNzk4IiwidXNlcl9pZCI6IjEifQ.XBbtRQe5ZgnvaMfCWgL4X8kyndT5dR44YHJbUaRoQmQ',
    'Accept': 'application/json',
}

resp = requests.get(url, headers=headers)
print(resp.status_code)
print(resp.text)
