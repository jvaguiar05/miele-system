# Miele OCR Local

Ferramenta para preparar grandes volumes de PDFs no computador do usuário, sem consumir CPU do backend Render e sem gravar diretamente no banco de dados.

## Fluxo

1. A ferramenta lê os PDFs da pasta informada sem mover ou alterar os originais.
2. Páginas sem camada de texto passam por RapidOCR/ONNX localmente.
3. CNPJ, protocolo e leiaute são avaliados pelo mesmo parser usado pelo Miele.
4. Os arquivos são separados por CNPJ e divididos automaticamente em pacotes seguros.
5. O usuário envia cada `.miele.zip` no botão **Importar** do Miele.
6. O backend confere SHA-256, CNPJ, estrutura e texto, gera a prévia e exige confirmação humana para documentos OCR.

A ferramenta nunca acessa o PostgreSQL, não contém credenciais do Google Drive e não envia documentos pela internet.

## Pré-requisitos

- Windows PowerShell;
- ambiente `C:\Projetos\miele-system\.venv` instalado;
- dependências de `requirements\requirements.txt` instaladas;
- espaço local suficiente para os pacotes gerados.

Para conferir o ambiente:

```powershell
cd C:\Projetos\miele-system
.\.venv\Scripts\python.exe -c "import pypdf, pypdfium2, rapidocr, onnxruntime; print('OCR OK')"
```

## Preparar uma pasta

```powershell
cd C:\Projetos\miele-system
.\scripts\Build-MieleOcrPackage.ps1 `
  -InputPath "C:\Caminho\Dos\PDFs" `
  -OutputDirectory "C:\MieleOCR\Saida" `
  -Workers 1
```

Também é possível informar um único PDF:

```powershell
.\scripts\Build-MieleOcrPackage.ps1 `
  -InputPath "C:\Caminho\documento.pdf" `
  -OutputDirectory "C:\MieleOCR\Saida"
```

Use `-Workers 1` inicialmente. Em computador com pelo menos 16 GB de RAM, `-Workers 2` pode ser testado. O limite aceito é quatro, mas paralelismo excessivo pode deixar o computador lento.

## Resultado

A ferramenta cria uma pasta datada:

```text
miele_ocr_20261006_120000/
├── pacotes/
│   ├── 23451982000133_parte_001.miele.zip
│   └── 23451982000133_parte_002.miele.zip
├── relatorio.csv
└── resumo.json
```

- Cada pacote possui somente um CNPJ.
- Cada pacote contém até 49 PDFs, até 45 MB e no máximo 500 páginas.
- Arquivos repetidos são eliminados pelo SHA-256.
- `relatorio.csv` mostra CNPJ, protocolo, páginas, confiança e pendências.
- `READY` significa que o parser reconheceu os campos mínimos.
- `REVIEW` significa que o pacote pode ser aberto no Miele, mas o documento exigirá correção ou tratamento manual.
- Arquivos sem CNPJ seguro aparecem no relatório e não entram em pacote algum.

## Importar no Miele

1. Abra **PER/DCOMP → Importar**.
2. Selecione um arquivo `.miele.zip` da pasta `pacotes`.
3. Clique em **Gerar prévia**.
4. Confira CNPJ, protocolo, valores, relações e confiança do OCR no PDF original.
5. Corrija somente os campos permitidos quando necessário.
6. Marque a confirmação de OCR e informe uma justificativa.
7. Confirme o registro.
8. Sincronize os originais com o Google Drive pelo fluxo normal do Miele.

Não extraia nem altere manualmente o conteúdo do `.miele.zip`. Qualquer mudança no PDF, no manifesto ou no texto quebra as validações de integridade.

## Google Drive

O Drive pode ser usado como pasta sincronizada de entrada e como arquivo dos originais. A ferramenta local não precisa do token OAuth do Miele: o aplicativo Google Drive para computador realiza a sincronização.

O OCR embutido do Google Drive não é usado. O processamento permanece local, preservando confidencialidade e mantendo o Miele responsável por validação, confirmação e auditoria.

## Segurança e limites

- PDF original: até 10 MB e 100 páginas.
- Pacote: até 49 PDFs e 50 MB de originais.
- Texto extraído: até 2 MB por PDF e 10 MB por pacote.
- ZIP traversal, links simbólicos, criptografia, itens extras e hashes divergentes são bloqueados.
- O servidor recalcula os campos; não aceita valores financeiros prontos do computador local.
- PDFs OCR sempre exigem autorização explícita e justificativa no Miele.
- Retificadoras, versões anteriores e saldos continuam sendo decididos pelo backend.

## Solução de problemas

**Nenhum ambiente Python com dependências OCR foi encontrado**

Instale as dependências na `.venv` correta e repita. Não use uma `.venv-local` sem `pypdf`, `pypdfium2`, `rapidocr` e `onnxruntime`.

**REVIEW: CNPJ titular não identificado**

Confira se o PDF mostra o CNPJ principal e não apenas o CNPJ de um débito. Preserve o original e trate o documento manualmente quando necessário.

**REVIEW com confiança alta**

Confiança de OCR mede reconhecimento visual, não validade fiscal. O parser pode exigir revisão por período, valores conflitantes ou leiaute ainda não homologado.

**O computador ficou lento**

Interrompa após o arquivo atual e execute novamente com `-Workers 1`. Os originais não são modificados.
