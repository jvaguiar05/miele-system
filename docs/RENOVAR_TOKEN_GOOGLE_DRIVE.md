# Miele — renovar a autorização do Google Drive

Tutorial para substituir `GDRIVE_REFRESH_TOKEN` no backend do Render. Não requer commit, push ou alteração de banco.

## 1. Preparar as credenciais

1. Abra o [painel do Render](https://dashboard.render.com/).
2. Selecione o **backend do Miele** (atualmente `miele-backend-staging`).
3. Entre em **Environment** e localize `GDRIVE_CLIENT_ID` e `GDRIVE_CLIENT_SECRET`.
4. Tenha os dois valores disponíveis para preencher o site oficial do Google no passo 3.

Não cole credenciais neste tutorial, no GitHub, em mensagens ou capturas de tela. Use a mesma conta Google que já tem acesso às pastas de clientes, PER/DCOMPs e Selic.

## 2. Conferir o cliente Google

1. Abra o [Google Cloud Console](https://console.cloud.google.com/) e selecione o projeto usado pelo Miele.
2. Em **Google Auth Platform → Clients** (ou **APIs e serviços → Credenciais**), abra o cliente cujo ID corresponde ao Render.
3. Confira se a Google Drive API está habilitada no projeto.
4. No cliente web, confira se **URIs de redirecionamento autorizados** inclui exatamente:

```text
https://developers.google.com/oauthplayground
```

Adicione esse endereço se estiver ausente, preservando os demais. Não crie outro cliente apenas para renovar o token. A correspondência entre cliente, segredo e autorização é necessária. [Referência Google](https://developers.google.com/identity/protocols/oauth2/web-server).

## 3. Gerar o novo refresh token

1. Abra o [OAuth Playground oficial](https://developers.google.com/oauthplayground/).
2. Na engrenagem, configure:

| Opção | Valor |
| --- | --- |
| OAuth flow | Server-side |
| OAuth endpoints | Google |
| Access type | Offline |
| Force prompt | Consent Screen |
| Use your own OAuth credentials | Marcado |
| OAuth Client ID | Valor de `GDRIVE_CLIENT_ID` |
| OAuth Client secret | Valor de `GDRIVE_CLIENT_SECRET` |

3. Feche as configurações.
4. Em **Step 1**, preencha o campo de escopos com:

```text
https://www.googleapis.com/auth/drive
```

5. Clique em **Authorize APIs**.
6. Entre na conta Google usada pelo Miele e confira o aplicativo e as permissões antes de autorizar.
7. Em **Step 2**, clique em **Exchange authorization code for tokens**.
8. Copie o campo **Refresh token**, não o **Access token**.

**Marcar as próprias credenciais é essencial:** tokens emitidos com as credenciais padrão do Playground são revogados após 24 horas. [Referência do Playground](https://developers.google.com/oauthplayground/).

## 4. Atualizar o Render

1. Volte ao backend → **Environment** → **Edit**.
2. Substitua somente o valor de `GDRIVE_REFRESH_TOKEN` pelo token completo, sem aspas ou espaços extras.
3. Preserve `GDRIVE_CLIENT_ID`, `GDRIVE_CLIENT_SECRET` e os IDs das pastas.
4. Escolha **Save, rebuild, and deploy** ou **Save and deploy**, conforme as opções disponíveis. Se salvar sem deploy, execute um deploy manual depois.
5. Aguarde o novo deploy ficar **Live**. O processo precisa reiniciar para carregar a variável.

Não é necessário publicar o frontend. [Variáveis de ambiente no Render](https://render.com/docs/configure-environment-variables).

## 5. Testar no Miele

1. No sistema publicado, abra um relatório Selic que tenha **PDF original** e tente baixá-lo. Isso verifica acesso ao Drive, desde que o original tenha sido armazenado nele.
2. Para verificar escrita, importe um PDF oficial novo: gere a prévia, confira os valores e confirme.
3. Verifique o arquivo na pasta Selic e o download pelo Miele.

A prévia sozinha não testa o Google Drive: o envio ocorre na confirmação. Um PDF já importado é bloqueado por duplicidade antes do envio; essa mensagem também não comprova a conexão com o Drive. Não altere um PDF apenas para contornar essa verificação.

## 6. Evitar renovações frequentes

No Google Cloud, confira **Google Auth Platform → Audience → Publishing status**. O Miele foi configurado como **Em produção / Externo**; confirme que está no projeto correspondente ao Client ID do Render.

Aplicativos externos em Testing podem emitir tokens com validade de sete dias para esse escopo. Se mudar para produção, gere uma nova autorização depois da mudança. Em produção não há essa expiração semanal, mas o token pode ser revogado, ficar sem uso por seis meses, atingir limites de emissão ou ser afetado por políticas da organização. Nenhum refresh token deve ser tratado como permanente. [Regras de validade do Google](https://developers.google.com/identity/protocols/oauth2).

O backend usa o refresh token para obter automaticamente novos access tokens. O botão **Refresh access token** do Playground não substitui um refresh token inválido no Render.

## 7. Se ainda não funcionar

| Sintoma | O que conferir |
| --- | --- |
| `redirect_uri_mismatch` | O endereço do passo 2 deve estar no mesmo cliente usado no Playground, em URIs de redirecionamento. |
| `invalid_client` | Client ID e Client Secret devem corresponder e estar ativos. |
| Refresh token não apareceu | Confira Offline, Consent Screen e credenciais próprias; refaça a autorização e a troca do código. |
| Pasta inexistente ou sem acesso | Confira o ID da pasta e a conta que autorizou o token. |
| Autorização expirada mesmo após trocar | Confira o serviço alterado, a conclusão do deploy e se copiou o refresh token completo. |
| Falha volta em cerca de 24 horas | Confira se usou as próprias credenciais no Playground. |
| Falha volta em sete dias | Confira o status de publicação do projeto do Client ID utilizado. |

A mensagem atual do Miele sobre autorização expirada também pode representar outras falhas na renovação OAuth. Se persistir, consulte os logs do backend e compartilhe apenas a descrição do erro, sem tokens ou segredos.

### Último recurso: revogar o acesso anterior

Não revogue se já conseguiu gerar e usar o novo token. A revogação pode interromper outras integrações que compartilham essa autorização; os arquivos permanecem no Drive.

Se a emissão continuar sem refresh token, acesse as [conexões da Conta Google](https://myaccount.google.com/connections), identifique com cuidado o aplicativo do Miele, remova a autorização e repita os passos 3 a 5. A nova autorização deve usar acesso offline e consentimento explícito. [Fluxo OAuth e revogação](https://developers.google.com/identity/protocols/oauth2/web-server).

## Registro da manutenção

Preencha apenas informações administrativas; nunca registre valores de tokens aqui.

- Data da renovação:
- Responsável:
- Serviço do Render atualizado:
- Projeto Google Cloud:
- Deploy concluído:
- Download pelo Drive testado:
- Upload testado, quando houver documento novo:
