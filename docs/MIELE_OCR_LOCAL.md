# Miele OCR Local

Ferramenta para preparar grandes volumes de PDFs no computador do usuário, sem consumir CPU do backend Render e sem gravar diretamente no banco de dados.

## Fluxo

1. A ferramenta lê os PDFs sem mover ou alterar os originais.
2. Páginas sem camada de texto passam por RapidOCR/ONNX localmente.
3. CNPJ, protocolo e leiaute são avaliados pelo mesmo parser usado pelo Miele.
4. Os arquivos são separados por CNPJ e divididos em pacotes seguros.
5. O usuário envia um ou vários `.miele.zip` pelo botão **Importar**.
6. O backend confere estrutura, hashes, CNPJ e texto, recalcula os campos e exige conferência humana de todo documento preparado localmente.

A ferramenta nunca acessa PostgreSQL, `.env` ou Google Drive e não envia documentos pela internet. O hash garante a consistência entre os itens do pacote, mas não prova sozinho que o OCR leu corretamente cada imagem. Confira sempre o PDF original antes de registrar.

## Instalação recomendada no Windows

Use o ZIP versionado **Miele OCR Local para Windows** publicado pela equipe:

1. baixe o ZIP de uma pasta oficial e confirme a versão esperada;
2. extraia todo o conteúdo para uma pasta local;
3. execute `Install-MieleOcrLocal.cmd`;
4. autorize o download das dependências OCR quando solicitado;
5. abra **Miele OCR Local** pelo Menu Iniciar.

A instalação fica em `%LOCALAPPDATA%\Miele\OCR Local`, apenas para o usuário atual, e não exige administrador. O instalador exige Python 3.11 e nunca instala Python silenciosamente. Se ele estiver ausente, mostra instruções para instalação manual e a opção explícita por `winget`.

No aplicativo, escolha uma pasta ou PDFs específicos. O processamento usa um worker, mostra o avanço arquivo por arquivo e abre a pasta `pacotes` ao terminar. A saída padrão fica em **Documentos\Miele OCR**.

## Instalação para desenvolvimento

Pré-requisitos: Windows PowerShell, Python 3.11 e espaço local suficiente.

```powershell
cd C:\Projetos\miele-system
py -3.11 -m venv .venv-local
.\.venv-local\Scripts\python.exe -m pip install -r requirements\ocr-local.txt
.\.venv-local\Scripts\python.exe -c "import pypdf, pypdfium2, rapidocr, onnxruntime; print('OCR OK')"
```

Ambientes virtuais copiados ou movidos entre computadores não são portáteis. Recrie a `.venv-local` se o Python original não existir mais.

## Preparar arquivos pelo repositório

```powershell
cd C:\Projetos\miele-system
.\scripts\Build-MieleOcrPackage.ps1 `
  -InputPath "C:\Caminho\Dos\PDFs" `
  -OutputDirectory "$HOME\Documents\Miele OCR" `
  -Workers 1
```

Também é possível informar um único PDF. Use um worker inicialmente. Em computador com pelo menos 16 GB de RAM, dois podem ser testados; o limite é quatro.

## Quando usar OCR online ou local

Use o OCR online para arquivos pequenos e ocasionais: até 5 páginas que precisem de OCR por operação, 10 páginas executadas por usuário ao dia e 40 páginas executadas pelo sistema ao dia. A prévia e a confirmação contam separadamente porque o servidor executa o OCR nas duas etapas. PDFs que já possuem texto e pacotes `.miele.zip` não consomem essa cota.

Para volumes acima desses limites, prepare os arquivos com o Miele OCR Local. Os números são configuráveis pela equipe e podem ser ajustados conforme a capacidade do ambiente; a mensagem exibida pelo sistema é a referência para a configuração vigente.

## Resultado

Cada execução cria uma pasta datada:

```text
miele_ocr_20261007_120000/
|-- pacotes/
|   |-- 23451982000133_parte_001.miele.zip
|   `-- 23451982000133_parte_002.miele.zip
|-- relatorio.csv
`-- resumo.json
```

- Cada pacote possui somente um CNPJ.
- Cada pacote contém até 49 PDFs, até 45 MB de PDFs + extrações, no máximo 500 páginas e até 10 MB de texto extraído.
- Cada PDF tem no máximo 10 MB, 100 páginas e 2 MB de texto extraído.
- Arquivos repetidos são eliminados pelo SHA-256.
- `relatorio.csv` mostra CNPJ, protocolo, páginas, confiança e pendências.
- `READY` indica que o parser reconheceu os campos mínimos.
- `REVIEW` indica que o documento exigirá correção ou tratamento manual no Miele.
- Arquivos sem CNPJ seguro aparecem no relatório e não entram em pacote.

## Importar no Miele

1. Abra **PER/DCOMP → Importar**.
2. Selecione os `.miele.zip` da pasta `pacotes`.
3. Gere a prévia e, em lote multi-CNPJ, escolha um cliente por vez.
4. Confira CNPJ, protocolo, valores, relações, confiança e PDF original.
5. Corrija somente os campos permitidos.
6. Marque a confirmação da preparação local e informe uma justificativa. Isso também é obrigatório quando o pacote encontrou texto nativo, pois a extração ocorreu fora do servidor.
7. Confirme o registro e continue com os outros clientes do lote.
8. Sincronize os originais com o Google Drive pelo fluxo normal do Miele.

Não extraia nem altere o conteúdo do `.miele.zip`. Qualquer mudança quebra as validações de integridade.

## Segurança e retenção local

O `.miele.zip` contém o PDF original e o texto fiscal extraído, sem criptografia própria:

- gere a saída somente em pasta corporativa com acesso restrito;
- não envie pacotes por e-mail pessoal ou mensageiros não autorizados;
- ao usar pasta sincronizada, confirme permissões e política da organização;
- mantenha os pacotes somente pelo período necessário para importar e conferir;
- após confirmação e arquivamento pelo Miele, elimine cópias locais conforme a política de retenção da empresa.

O OCR embutido do Google Drive não é usado. Uma pasta sincronizada pode servir como entrada ou saída, mas a sincronização é responsabilidade do aplicativo Google Drive do usuário.

## Solução de problemas

**Python 3.11 não foi encontrado**

O instalador não baixa Python sem autorização. Instale-o pelo site oficial ou execute o instalador PowerShell com `-InstallPythonWithWinget` se desejar usar `winget` explicitamente.

**Dependências OCR não foram encontradas**

Usuários operacionais devem executar novamente o instalador da distribuição oficial. Desenvolvedores devem recriar a `.venv-local` e instalar `requirements\ocr-local.txt`.

**Nenhum pacote foi criado**

Abra o `relatorio.csv`. PDFs corrompidos, acima dos limites ou sem CNPJ titular seguro não entram em pacote. Preserve o original e envie-o separadamente ao Miele para tratamento manual quando aplicável.

**REVIEW com confiança alta**

Confiança mede reconhecimento visual, não validade fiscal. O parser ainda pode exigir revisão por período, valores conflitantes ou leiaute não homologado.

**O computador ficou lento**

Use um worker. O launcher instalado já usa essa configuração conservadora. Interromper uma execução não apaga nem modifica os PDFs originais, mas a versão atual não retoma automaticamente um lote interrompido.

**O envio direto expira**

Prepare o PDF em imagem pelo Miele OCR Local e envie o `.miele.zip` pelo mesmo botão **Importar**. O backend continua responsável por validação, confirmação e auditoria.
