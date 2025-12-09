# DEPLOYMENT – Miele System

> Guia completo de deploy do Miele System no Render.com com PostgreSQL e integração Google Drive.

---

## 🌐 Visão Geral

O Miele System está configurado para deploy automático no **Render.com**, oferecendo:

- **Web Service** Django/DRF com Gunicorn + Uvicorn workers
- **PostgreSQL** gerenciado pelo Render
- **Armazenamento** via Google Drive API (OAuth 2.0)
- **Deploy automático** via Git (branch `develop`)
- **Health checks** para monitoramento
- **Logs estruturados** em JSON

---

## 📋 Pré-requisitos

### 1. Conta no Render.com
- Acesse [render.com](https://render.com) e crie uma conta
- Conecte sua conta GitHub/GitLab

### 2. Configuração Google Drive
- Console do Google Cloud com projeto criado
- Google Drive API habilitada
- Credenciais OAuth 2.0 configuradas
- Refresh Token gerado (veja seção específica)

---

## 🔧 Configuração no Render.com

### 1. Criar Web Service

1. **Dashboard do Render** → "New" → "Web Service"
2. **Connect Repository**: conecte o repositório `miele-system`
3. **Configurações básicas**:
   - **Name**: `miele-system` (ou nome preferido)
   - **Runtime**: `Docker`
   - **Branch**: `develop` (deploy automático)
   - **Root Directory**: deixar vazio
   - **Docker Command**: deixar vazio (usa Dockerfile)

### 2. Configurar Environment Variables

No dashboard do Render, vá em **Environment** e configure:

#### Aplicação
```env
# Obrigatório
SECRET_KEY=sua-chave-secreta-super-segura-aqui
DEBUG=false
ALLOWED_HOSTS=seu-app.onrender.com

# Opcional (configurado automaticamente pelo Render)
PORT=10000
```

#### Banco de Dados
```env
# Será configurado automaticamente quando conectar PostgreSQL
DATABASE_URL=postgresql://user:pass@host:port/db
```

#### CORS e Segurança
```env
CORS_ALLOWED_ORIGINS=https://seu-frontend.com,https://outro-dominio.com
CORS_ALLOW_ALL_ORIGINS=false
SECURE_SSL_REDIRECT=true
SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO,https
```

#### Google Drive
```env
GDRIVE_CLIENT_ID=123456789.apps.googleusercontent.com
GDRIVE_CLIENT_SECRET=seu-client-secret
GDRIVE_REFRESH_TOKEN=seu-refresh-token-aqui
GDRIVE_CLIENTS_FOLDER_ID=id-da-pasta-clientes
GDRIVE_PERDCOMPS_FOLDER_ID=id-da-pasta-perdcomps
```

### 3. Adicionar PostgreSQL

1. **Dashboard** → "New" → "PostgreSQL"
2. **Name**: `miele-system-db`
3. **PostgreSQL Version**: 15 ou superior
4. **Após criação**: conecte ao Web Service
   - Web Service → **Environment** 
   - A variável `DATABASE_URL` será adicionada automaticamente

---

## 🔑 Configuração Google Drive OAuth

### 1. Google Cloud Console

1. **Acesse**: [console.cloud.google.com](https://console.cloud.google.com)
2. **Crie ou selecione** um projeto
3. **APIs & Services** → **Library**
4. **Habilite** a Google Drive API

### 2. Credenciais OAuth 2.0

1. **APIs & Services** → **Credentials**
2. **Create Credentials** → **OAuth 2.0 Client ID**
3. **Application type**: Web application
4. **Authorized redirect URIs**: `https://developers.google.com/oauthplayground`
5. **Salve** Client ID e Client Secret

### 3. Gerar Refresh Token

1. **Acesse**: [OAuth 2.0 Playground](https://developers.google.com/oauthplayground)
2. **Configurações** (engrenagem):
   - ☑️ Use your own OAuth credentials
   - **OAuth Client ID**: seu client ID
   - **OAuth Client Secret**: seu client secret
3. **Step 1**: 
   - **Select & authorize APIs**: `https://www.googleapis.com/auth/drive`
   - **Authorize APIs**
4. **Step 2**: 
   - **Exchange authorization code for tokens**
   - **Copie** o Refresh Token

### 4. Criar Pastas no Google Drive

1. **Acesse** [drive.google.com](https://drive.google.com)
2. **Crie** uma estrutura de pastas:
   ```
   Miele System/
   ├── Clientes/
   └── PERDCOMPs/
   ```
3. **Copie os IDs** das pastas da URL:
   - `https://drive.google.com/drive/folders/ID_DA_PASTA`

---

## 🚀 Processo de Deploy

### 1. Deploy Automático

O deploy acontece automaticamente quando:
- **Push** para branch `develop`
- **Merge** de Pull Request para `develop`

### 2. Deploy Manual

No dashboard do Render:
1. **Web Service** → **Manual Deploy**
2. **Deploy Latest Commit**

### 3. Logs de Deploy

Monitor em tempo real:
- **Dashboard** → **Logs** (tab superior)
- Logs mostram build do Docker, migrações, e startup

---

## 🔍 Monitoramento e Health Checks

### Health Check Endpoints

O Render monitora automaticamente:
- **Health Check Path**: `/health/ready`
- **Timeout**: 30 segundos
- **Intervalo**: 30 segundos

### Endpoints Disponíveis

```bash
# Liveness (app está rodando)
curl https://seu-app.onrender.com/health/live

# Readiness (app + db + dependências)
curl https://seu-app.onrender.com/health/ready
```

### Logs Estruturados

Logs em formato JSON:
```bash
# Via Render Dashboard
Logs → Stream logs

# Exemplo de log
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "logger": "django",
  "message": "Request completed",
  "request_id": "req-123",
  "user_id": "user-456",
  "method": "POST",
  "path": "/api/v1/clients/",
  "status": 201,
  "latency_ms": 45
}
```

---

## 🛠️ Configurações Específicas

### render.yaml

O arquivo `render.yaml` configura automaticamente:

```yaml
services:
  - type: web
    name: miele-system
    runtime: docker
    plan: starter
    branch: develop
    healthCheckPath: /health/ready
    envVars:
      - key: PORT
        value: 10000
      - key: PYTHON_VERSION
        value: 3.11
```

### Dockerfile

Otimizado para produção:
- **Multi-stage build** para reduzir tamanho
- **Python 3.11** Alpine para performance
- **Gunicorn + Uvicorn workers** para ASGI/WSGI
- **WhiteNoise** para arquivos estáticos

### Configurações Django

`core/settings/prod.py`:
```python
# SSL e segurança
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Headers de segurança
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# Sessões e cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

---

## 🔄 Comandos de Gerenciamento

### Executar Comandos no Render

Via **Shell** no dashboard:

```bash
# Aplicar migrações
python manage.py migrate

# Criar superusuário
python manage.py create_superuser_with_role

# Configurar roles
python manage.py setup_roles

# Coletar arquivos estáticos (se necessário)
python manage.py collectstatic --noinput
```

---

## 🐛 Troubleshooting

### Problemas Comuns

#### 1. Falha no Build
```bash
# Verificar logs no Render Dashboard
# Comum: dependências não instaladas
Error: Could not find a version that satisfies the requirement...

# Solução: verificar requirements/base.in
```

#### 2. Database Connection Error
```bash
# Verificar se PostgreSQL foi conectado corretamente
# Verificar se DATABASE_URL existe nas environment variables
```

#### 3. Google Drive API Errors
```bash
# Verificar se todas as variáveis GDRIVE_* estão configuradas
# Verificar se o refresh token ainda é válido
# Verificar se a API está habilitada no Google Cloud Console
```

#### 4. Health Check Failing
```bash
# Verificar se /health/ready responde
curl https://seu-app.onrender.com/health/ready

# Verificar logs para erros de dependências
```

### Debug de Logs

```bash
# Logs em tempo real no dashboard
# Filtrar por ERROR ou WARNING
# Procurar por stack traces completas

# Exemplo de log de erro
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "ERROR", 
  "logger": "django.request",
  "message": "Internal Server Error",
  "request_id": "req-123",
  "exception": "ValueError: ...",
  "traceback": ["File ...", "Line ..."]
}
```

---

## 📊 Performance e Escalabilidade

### Planos do Render

- **Starter**: $7/mês - 512MB RAM, adequado para desenvolvimento
- **Standard**: $25/mês - 2GB RAM, produção básica
- **Pro**: $85/mês - 4GB RAM, produção com mais carga

### Otimizações

```python
# settings/prod.py

# Connection pooling
DATABASES['default']['CONN_MAX_AGE'] = 60
DATABASES['default']['OPTIONS'] = {
    'MAX_CONNS': 20,
    'MIN_CONNS': 5,
}

# Cache (opcional - Redis addon)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env('REDIS_URL'),
    }
}
```

### Monitoring Adicional (Opcional)

```python
# Sentry para error tracking
SENTRY_DSN = env('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment='production',
        traces_sample_rate=0.1,
    )
```

---

## 🔐 Segurança em Produção

### Checklist de Segurança

- ✅ **SECRET_KEY** única e segura
- ✅ **DEBUG=false** 
- ✅ **ALLOWED_HOSTS** específico
- ✅ **CORS** restrito
- ✅ **SSL** forçado
- ✅ **Headers** de segurança
- ✅ **Environment variables** para credenciais
- ✅ **Database** com acesso restrito

### Backup e Recuperação

```bash
# Render PostgreSQL tem backup automático
# Para backup manual via pg_dump:
pg_dump $DATABASE_URL > backup.sql

# Restauração:
psql $DATABASE_URL < backup.sql
```

---

## 📝 Manutenção

### Updates Regulares

1. **Dependências**: `pip-compile` e commit
2. **Migrações**: aplicadas automaticamente no deploy
3. **Rollback**: via dashboard ou revert do commit
4. **Monitoring**: verificar logs e health checks diariamente

### Rotina de Deploy

1. **Desenvolvimento**: branch `feature/*`
2. **Testing**: merge para `develop` 
3. **Deploy automático**: Render monitora `develop`
4. **Validação**: verificar health checks e logs
5. **Produção estável**: merge para `main` quando necessário

---

## 📞 Suporte

### Recursos Render.com

- **Documentação**: [docs.render.com](https://docs.render.com)
- **Status**: [status.render.com](https://status.render.com)
- **Support**: tickets via dashboard

### Logs e Debugging

- **Application logs**: Dashboard → Logs
- **Build logs**: Deploy → View details
- **PostgreSQL logs**: Database → Logs
- **Health checks**: Service → Health

---