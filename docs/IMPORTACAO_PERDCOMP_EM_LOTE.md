# Importação operacional de PER/DCOMPs por cliente

## Onde usar

**PER/DCOMP → Importar** para identificação automática pelo CNPJ, ou **Clientes → abrir cliente → PER/DCOMPs → Importação em lote** para trabalhar dentro de um cliente já conhecido.

É possível enviar um único PDF, vários PDFs, um ZIP comum ou um ou mais pacotes `.miele.zip` preparados pela ferramenta local. Na aba geral, o sistema separa o lote pelo CNPJ principal extraído e permite escolher um cliente por vez. Dentro do cadastro de um cliente, somente os PDFs do CNPJ aberto são apresentados; arquivos reconhecidos como pertencentes a outros clientes são ignorados com segurança. A prévia não grava dados; um administrador ou funcionário aprovado pode confirmar depois de conferir as diferenças.

Para grandes lotes que exigem OCR, consulte [Miele OCR Local](MIELE_OCR_LOCAL.md). O computador executa o trabalho pesado e o backend continua responsável por integridade, validação, confirmação e auditoria.

## Regras de segurança

| Situação encontrada | Ação na confirmação |
| --- | --- |
| Protocolo novo e documento válido | Cria PER/DCOMP com status **Transmitido** |
| Protocolo existente | Mostra valor atual e proposto; valores financeiros exigem autorização individual |
| Valor manual divergente | Só é substituído após checkbox e justificativa do usuário |
| Retificadora válida | Cria novo registro vigente e marca o original como substituído |
| Documento anterior importado depois | Arquiva como **Versão anterior — nenhum dado alterado** |
| PDF inválido, digitalizado ou legado não reconhecido | Só entra na fila manual se o usuário marcar essa opção |
| Mesmo protocolo em mais de um registro operacional | Bloqueia a automação e exige tratamento manual |

Identidade: protocolo normalizado + CNPJ + cliente selecionado. O nome do arquivo não é usado para identificar ou substituir uma PER/DCOMP.

Campos preenchidos pelo PDF: número/protocolo, processo, datas, tributo, valor solicitado, compensação declarada, crédito utilizado e saldo documental. Recebimento bancário, homologação e deferimento não são presumidos. O saldo operacional é sempre `Pedido − (Compensado + Recebido)`; saldo negativo é rejeitado.

## Operação

1. Abra o cliente correto. Use **Registrar arquivos já importados** para os PDFs que já estão no sistema, sem reenviá-los; ou **Importar novos arquivos**.
2. Selecione PDFs ou um ZIP. Envie demonstrativo e recibo juntos, quando disponíveis.
3. Clique **Gerar prévia**. Confira a ação operacional e as diferenças de campos.
4. Marque somente documentos conferidos. Retificadoras e alterações exigem justificativa.
5. Para um arquivo inválido que precisa ser preservado, marque **Enviar para tratamento manual**. Não marque arquivos de outro cliente.
6. Um usuário interno aprovado confirma. Toda substituição financeira exige autorização individual e justificativa.
7. Confira a lista operacional. A sincronização posterior com o Drive é opcional e guarda apenas uma cópia dos originais.

## Fila de tratamento manual

Na mesma tela, o usuário pode baixar o PDF, abrir o cadastro manual, selecionar uma PER/DCOMP operacional do mesmo cliente e vinculá-la com justificativa, ou descartar a pendência com justificativa.

Somente administradores concluem ou descartam pendências. Os arquivos ficam no banco e não são enviados ao Drive. O vínculo manual não altera campos nem valores da PER/DCOMP escolhida.

## Arquivos analisados

O conjunto privado `miele-frontend/PerDComp` tem 85 arquivos e não é versionado no Git:

| Classificação | Quantidade | Tratamento |
| --- | ---: | --- |
| Demonstrativos Web com texto | 19 | Automático após conferência |
| Recibos Web com texto | 17 | Agrupados por titular e protocolo |
| PDFs sem texto nativo | 44 | OCR local com conferência obrigatória; fila manual quando o reconhecimento não for seguro |
| PDFs antigos PER/DCOMP 7.1 | 2 | Fila manual |
| Backups DBK | 2 | Não suportados |
| `desktop.ini` | 1 | Ignorado |

Os 36 PDFs Web representam 19 documentos de três titulares. Nunca importe toda a pasta para um único cliente. Para inspecionar sem gravar:

```powershell
cd C:\Projetos\miele-system
py -3.11 backend/manage.py inspect_perdcomp_pdfs C:\Projetos\miele-frontend\PerDComp --summary-only --settings=core.settings.dashboard_test
```

## Armazenamento e auditoria

- A prévia fica em memória e expira em uma hora; a confirmação reextrai e revalida os arquivos.
- Originais, hashes, evidências, correções, justificativas e usuário são preservados.
- A publicação usa transação, bloqueio do cliente e restrições únicas contra duplicidade.
- A cópia no Drive usa `GDRIVE_PERDCOMPS_FOLDER_ID` e não é requisito para o cadastro.
- Falha no Drive não desfaz o cadastro e não apaga o PDF armazenado no banco.
- A importação registra compensação declarada quando a fórmula operacional é coerente e o usuário confirma. Não presume recebimento, homologação, honorários, Selic ou decisões da Receita.
- Se o total declarado superar o valor hoje mapeado como Pedido, os dados documentais são preservados e a aplicação financeira fica pendente de regra, sem saldo negativo.
- No Drive, os nomes seguem `CNPJ_TIPO_PROTOCOLO_DATA_PAPEL_HASH12.pdf`. O hash evita colisões e o nome original permanece no banco.

Modelos principais: `ImportBatch`, `ImportedFile`, `ImportedDocument`, `DocumentReview` e `ManualImportIssue`. O documento importado pode apontar para o `Perdcomp` operacional.

## API e limites

Prefixo: `/api/v1/clients/{client_uuid}/perdcomp-imports/`.

- `POST preview/` e `POST confirm/` (`selected`, `manual_selected`, `financial_confirmed`, `token`, arquivos e justificativa);
- `GET reprocess/preview/` e `POST reprocess/confirm/`: registra documentos já armazenados;
- `POST preview-file/`, `GET documents/` e `GET files/{file_uuid}/`;
- `GET manual/{issue_uuid}/file/` e `POST manual/{issue_uuid}/resolve/`;
- `POST sync-drive/`, somente por administrador.

Limites: 100 arquivos, 10 MB por PDF, 50 MB por lote/ZIP, 100 páginas por PDF, 500 por lote e 20 páginas que necessitem OCR direto no servidor. Pacotes OCR locais contêm até 49 PDFs, 45 MB e 500 páginas; o servidor confere hashes e não repete o OCR. ZIP aninhado, traversal, symlink, item criptografado, arquivo não declarado e compressão excessiva são rejeitados. DBK continua fora do escopo.

## PDFs em imagem e OCR

- O backend tenta primeiro a camada de texto nativa. Somente páginas sem texto suficiente passam pelo OCR.
- O processamento usa RapidOCR/ONNX e PDFium localmente; nenhum PDF é enviado a serviços externos.
- A prévia identifica documentos OCR e apresenta a confiança média informativa.
- Protocolo, CNPJ, datas e valores devem ser conferidos no PDF original pelo usuário.
- O backend exige uma autorização OCR explícita e uma justificativa de pelo menos 10 caracteres.
- O original, o texto interpretado, as evidências, o usuário e a justificativa permanecem auditáveis.
- Se o OCR não produzir um leiaute válido, o documento não é publicado automaticamente e pode seguir para tratamento manual.
- Recibos retificadores reconhecem separadamente o protocolo vigente em **Número do Pedido Retificador** e a versão anterior em **Número do PER Retificado**.
- Em débitos com a seção **Valores Compensados**, os valores dessa seção prevalecem sobre o principal original. Multa ou juros omitidos só são inferidos como zero quando a aritmética exibida no próprio documento fecha exatamente; o principal original permanece na auditoria.

O botão **Importar** da aba geral de PER/DCOMPs usa o mesmo fluxo e aceita um PDF, múltiplos PDFs, ZIP ou vários pacotes `.miele.zip`. Quando houver mais de um CNPJ, a tela lista os clientes e a quantidade de PDFs de cada um. O usuário escolhe um cliente, confere e registra somente os documentos dele; depois pode continuar com os demais sem reenviar o lote. Arquivos sem CNPJ somente são associados por protocolo quando existe um único titular possível. Arquivos ambíguos nunca são atribuídos por suposição e devem ser importados dentro do cadastro correto para conferência.

## Migrações e validação

- `0008_documentarycredit_importbatch_importeddocument_and_more`: documentos e auditoria.
- `0009_manualimportissue`: fila de tratamento manual.
- `0010_importeddocument_superseded_by_and_more`: versões, situações separadas e valores documentais normalizados.

As migrações não convertem nem alteram valores de PER/DCOMPs antigas. Somente uma confirmação explícita pode criar, atualizar ou vincular registros operacionais.

```powershell
cd C:\Projetos\miele-system
$env:PERDCOMP_CORPUS_DIR = 'C:\Projetos\miele-frontend\PerDComp'
py -3.11 backend/manage.py test apps.clients.test_contracts apps.clients.test_dashboard_operations apps.clients.test_quarters apps.clients.test_selic apps.perdcomps.test_deadlines apps.perdcomps.test_reports apps.perdcomps.test_status_retirement apps.perdcomps.test_documentary_import --settings=core.settings.dashboard_test
```

Antes de produção: aplicar `migrate`, homologar em staging com cópia anonimizada e conferir criação, atualização segura, vínculo sem alteração, retificadora e fila manual. Nenhum PDF privado deve ir ao Git.

O conjunto privado nunca deve ser versionado no Git. Antes de cada publicação, repita os testes, o `check`, a conferência de migrações e o build do frontend.
