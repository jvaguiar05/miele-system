# Documentação da Atualização: Lookup de CNPJ e Preenchimento Automático

## Objetivo
Documentar a implementação final da funcionalidade de busca de CNPJ no backend, exposição do endpoint e consumo pelo frontend, além de definir o fluxo correto de Git para deploy.

## Alterações realizadas

### Backend
- `backend/apps/clients/services.py`
  - Implementada a função `lookup_cnpj_data()` para consultar a BrasilAPI e normalizar os dados.
  - Mapeamento de campos atualizado para `razao_social`, `nome_fantasia`, `tipo_empresa`, `atividades` e `qsa`.

- `backend/apps/clients/views.py`
  - Adicionada a action `lookup_cnpj()` ao `ClientViewSet`.
  - Endpoint exposto para GET em `/api/v1/clients/lookup-cnpj/`.

- `backend/apps/clients/urls.py`
  - Adicionada rota direta `lookup-cnpj/` junto com o roteador DRF.

- `backend/core/settings/base.py`
  - Adicionadas variáveis de configuração para `BRASILAPI_CNPJ_BASE_URL` e `BRASILAPI_TIMEOUT`.

### Frontend
- `miele-frontend/src/components/clients/ClientForm.tsx`
  - Removida a chamada direta à API externa via proxy.
  - Agora o frontend usa `api.get('clients/lookup-cnpj/')` para buscar dados do backend.
  - Ajustado o mapeamento de resposta para preencher os campos do formulário.

## Endpoint final
- `GET /api/v1/clients/lookup-cnpj/?cnpj={cnpj}`
- Exemplo:
  - `https://miele-backend-staging-r8hx.onrender.com/api/v1/clients/lookup-cnpj/?cnpj=01.166.372/0001-55`

## Resultado esperado
- Retorno HTTP `200 OK` com dados normalizados.
- Preenchimento automático das informações no formulário de cliente.
- Sem uso de CORS proxy externo no frontend.

## Fluxo de Git recomendado

### 1. Trabalhar em branch dedicada
Sempre crie uma branch para cada alteração importante:
```powershell
git checkout -b feature/cnpj-lookup-backend
```

### 2. Revisar antes de adicionar
Verifique as alterações:
```powershell
git status
git diff
```

### 3. Adicionar apenas os arquivos corretos
Evite `git add .` quando houver arquivos não relacionados.
```powershell
git add backend/apps/clients/services.py backend/apps/clients/views.py backend/apps/clients/urls.py backend/core/settings/base.py miele-frontend/src/components/clients/ClientForm.tsx
```

### 4. Commit com mensagem clara
```powershell
git commit -m "feat: adicionar lookup de CNPJ no backend e preenchimento automático no frontend"
```

### 5. Push da branch para o remoto
```powershell
git push origin feature/cnpj-lookup-backend
```

### 6. Merge para o branch de deploy
No seu caso, o staging do Render está configurado para `develop`.
- Abra PR da feature para `develop`.
- Após aprovar, faça merge para `develop`.

Se precisar testar no staging imediatamente e o serviço do Render usa `develop`, garanta que `develop` está atualizado com o código correto.

### 7. Verificar deploy no Render
- Aguarde a build completar.
- Teste o endpoint no staging.
- Se houver 404 ou erro, valide os logs do Render.

## Nota importante sobre branches
- `main` contém o histórico de produção/local.
- `develop` é o branch de staging no Render.
- Se fizer alterações em `main`, será preciso sincronizar com `develop` para que o staging receba o código.

### Comando rápido para sincronizar `main` com `develop`
```powershell
git checkout develop
git merge main
git push origin develop
```

## Dica final
- Nunca faça push direto antes de testar localmente.
- Sempre mantenha o branch de deploy (`develop`) alinhado com o branch de trabalho que você aprovou.
- Use `git status` e `git diff` como controle de qualidade antes de commitar.
