# Checklist de publicação do Miele

## 1. Antes do deploy

- Confirmar no Render:
  - `CORS_ALLOW_ALL_ORIGINS=false`
  - `CORS_ALLOWED_ORIGINS=https://miele-frontend-staging.vercel.app`
  - `ALLOWED_HOSTS=miele-backend-staging-r8hx.onrender.com`
  - `GDRIVE_MAX_FILE_SIZE=10485760`
  - credenciais e IDs das pastas do Google Drive preenchidos;
  - `SECRET_KEY` longa, aleatória e diferente do ambiente local.
- Confirmar na Vercel:
  - `VITE_API_BASE_URL=https://miele-backend-staging-r8hx.onrender.com/api/v1`
- Não alterar `DATABASE_URL` nem os IDs das pastas existentes.

## 2. Ordem de publicação

1. Publicar o backend na branch `develop`.
2. Aguardar `Deploy succeeded` no Render.
3. Conferir no Shell do Render:

   ```bash
   cd backend
   python manage.py showmigrations perdcomps
   ```

   A migração `0012_ocrdailyusage` deve aparecer com `[X]`.
4. Abrir `/health/live` e `/health/ready`; ambos devem responder sem erro.
5. Publicar o frontend na branch `main`.
6. Aguardar o deploy da Vercel e abrir o site em uma janela anônima.

## 3. Teste rápido após o deploy

- Entrar com um administrador e um funcionário.
- Confirmar que um visitante aprovado consegue consultar, mas não editar.
- Abrir Dashboard, Clientes, Contratos, PER/DCOMP e Relatórios.
- Importar primeiro um PDF textual pequeno e conferir a prévia antes de registrar.
- Confirmar que o PDF foi arquivado no Google Drive e pode ser aberto pelo Miele.
- Verificar que a fila de armazenamento não mantém cópias no banco.
- Evitar OCR em lote no primeiro teste; para volume alto, usar o Miele OCR Local.

## 4. Se ocorrer erro grave

- Pausar novas importações.
- Guardar horário, usuário, arquivo e mensagem do erro.
- Fazer rollback do deploy no Render ou na Vercel para a versão anterior.
- Não restaurar nem apagar o banco sem um backup confirmado.
