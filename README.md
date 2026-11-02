# neg35 — negativo 35mm → positivo restaurado

Fotografa um negativo de filme, transforma em positivo com matemática de cor
correta e restaura com IA.

```bash
# Preparar o ambiente (uma vez) -- cria .venv com numpy, Pillow, rawpy e requests
python tools/preparar_ambiente.py
python tools/instalar_wheels.py

# Interface gráfica (recomendado)
.venv\Scripts\python.exe tools\app.py

# Ou a linha de comando
.venv\Scripts\python.exe tools\lote.py
```

---

## Interface web (`tools/app.py`)

Abre em **http://127.0.0.1:8765/**. Faz o fluxo inteiro numa tela:

1. **Ao abrir, compara** a pasta de origem com a de positivos e a de restaurados
2. **Converte automaticamente** tudo que ainda não tem positivo, com barra de
   progresso: `N de M`, etapa atual e nome do arquivo
3. Mostra **só os que ainda não foram restaurados**, em grade com miniatura
4. **Clicar na miniatura abre a imagem grande**, com zoom
5. **Caixa de seleção** por foto (`Marcar todos` / `Desmarcar`)
6. Mostra o **custo estimado** antes de gastar
7. Botão **Restaurar selecionadas** chama a IA só nas marcadas
8. Engrenagem abre as **configurações** (pastas, saturação, curva, Adobe), que
   vão para o `.env`

Sem dependências novas: servidor com `http.server` da biblioteca padrão e front
em HTML/CSS/JS puro, sem framework e sem CDN. Motivo: neste ambiente o `pip`
trava (proxy + `%TEMP%` bloqueado), então evitar instalação foi decisão de
projeto, não preferência.

Detalhes em [docs/interface-web.md](docs/interface-web.md).

---

## Linha de comando (`tools/lote.py`)

O mesmo fluxo, em texto — útil para lote grande ou para depurar.

```
Pastas de trabalho (Enter mantém, ou digite um caminho novo):
  1/3 origem (os .dng/.jpg):
    atual: E:\Bkp\GoogleDrive\Negativo35mm\RAW
  ...
  6 a processar

Quais processar?  1,3-5 | todos | a

  fotos selecionadas : 6
  custo por imagem   : US$ 0.0387  (consulta ao OpenRouter)
  CUSTO ESTIMADO     : US$ 0.232

  Confirma? (s/n):
```

```bash
--tudo                  processa tudo que falta, sem perguntar
--selecao 1,3-5         escolhe sem interação
--so-local              só gera os positivos, sem IA (grátis)
--env CAMINHO           usa outro arquivo de configuração
--sem-perguntar-pastas  usa as pastas do .env direto
```

### O arquivo `.env`

Criado automaticamente na primeira execução. Fica no `.gitignore`.

```ini
pasta_origem=E:\Bkp\GoogleDrive\Negativo35mm\RAW
pasta_positivo=E:\Bkp\GoogleDrive\Negativo35mm\Positivo
pasta_restaurada=E:\Bkp\GoogleDrive\Negativo35mm\Restaurada

provedor=openrouter
modelo=google/gemini-2.5-flash-image
openrouter_api_key=...

filme=generico
saturacao=1.15
nitidez=0.4
balanco=0.9

max_lado_envio=1536
pular_restauradas=true

prompt=Restore this photograph. It is already a correct positive scan...
```

**Precedência:** variável de ambiente > `.env` > padrão do código. Isso permite
testar com `set OPENROUTER_API_KEY=...` sem tocar no arquivo salvo.

**Para trocar de modelo**, edite só a linha `modelo=`. Veja as opções com
`.venv\Scripts\python.exe -m neg35.cli modelos`.

⚠️ A chave fica em texto puro no `.env`. Ele está no `.gitignore`. Se vazar,
revogue no provedor.

---

## Por que DNG, e não é por resolução

A ideia de "converter tudo em JPG (mais leve) e usar DNG só nas escolhidas"
tem duas premissas erradas, e as duas foram medidas:

**O custo em tokens é o mesmo.** Tokens de imagem dependem da **dimensão em
pixels**. JPG e DNG da mesma foto têm a mesma resolução, e ambos são
redimensionados para o mesmo tamanho antes de ir ao modelo. O DNG só pesa mais
no upload.

**O JPG destruiu o dado que a inversão precisa.** O balanço de branco
automático do celular neutraliza a máscara laranja:

| Fonte | Máscara (R/B) | Veredito |
|---|---|---|
| DNG | **4,32** | máscara intacta |
| JPG | 1,25 – 1,68 | neutralizada |

Com máscara ~1,2 o dado é indistinguível de cinza. **5 dos 6 JPGs** estavam
assim.

### A estratégia que faz sentido

| Passo | Custo | Qualidade |
|---|---|---|
| Inversão (Python, local) | **zero** por foto | idêntica do JPG ou DNG |
| Restauração por IA | ~US$ 0,01–0,16 por foto | é aqui que o dinheiro vai |

Como a inversão é grátis, **converta sempre do DNG** e gaste a API só nas
fotos escolhidas. É exatamente o que o `lote.py` faz.

---

## As três regras que fazem o resultado sair certo

### 1. Gama se aplica UMA única vez

O pipeline trabalha inteiro em **luz linear**; a codificação sRGB acontece só
na borda. A saída do `rawpy` com `gamma=(1,1)` **já é linear** — aplicar
`srgb_para_linear` em cima encolhe tudo ~3,3×:

| | Base detectada | R/B |
|---|---|---|
| Tratando DNG como linear (correto) | `[0.692, 0.357, 0.160]` | 4,32 |
| Tratando DNG como sRGB (errado) | `[0.477, 0.115, 0.023]` | 20,7 |

O erro deixava o positivo lavado com 17,6% de pixels estourados. Corrigido:
5,4%. Tem teste de regressão para os dois sentidos.

### 2. Nunca inverta em sRGB

Negativo responde de forma linear. Inverter valores gama-encodados dá
contraste esmagado e dominante ciano.

### 3. Máscara laranja se remove por DIVISÃO, não subtração

```python
lin  = normalizar(foto, linear=True)    # já em luz linear
base = detectar_base_do_filme(lin)      # ~ (0.69, 0.36, 0.16)
t    = lin / base                       # remove a máscara
t    = t / t.max()
pos  = 1.0 - t                          # densidade -> luz
```

---

## Pipeline

```
1. carregar            DNG via rawpy/LibRaw; JPEG via Pillow (+ EXIF)
2. normalizar UMA vez para luz linear
3. detectar a base do filme   <-- parâmetro mais sensível
4. inverter (divisão pela base)
5. balanço de branco          <-- antes do contraste
6. contraste (percentis)
7. saturação (preserva luma)
8. nitidez (com limiar)       <-- depois de tudo
9. IA: denoise + cor (opcional)
10. codificar para sRGB e salvar
```

## Uso como biblioteca

```python
from neg35 import pipeline, config

cfg = config.carregar()                  # lê o .env

res = pipeline.desenvolver(
    "negativo.dng",
    pipeline.Parametros(filme="gold200", saturacao=1.15, restaurar="openrouter"),
)
# res.final está em LUZ LINEAR
pipeline.salvar(res.final, "saida.png", linear=True)

print(res.meta["base_filme"])
print(res.meta.get("aviso"))
```

Se você tem um array em vez de arquivo, diga o espaço em que ele está:

```python
pipeline.desenvolver(arr, entrada_linear=True)   # saída de rawpy
pipeline.desenvolver(arr)                        # JPEG/PNG em sRGB
```

---

## Etapa 2 — qual modelo de IA usar

**DeepSeek não faz isto.** Confirmado na
[documentação oficial](https://api-docs.deepseek.com/guides/vision/): o
`deepseek-flash` aceita imagem na **entrada**, mas devolve apenas **texto**.
Não existe endpoint de geração ou edição de imagem. Igual para Claude e GPT
de texto.

| Modelo | US$/imagem | Serve? |
|---|---|---|
| `google/gemini-2.5-flash-image` | $0,039 | ✅ **recomendado** |
| `google/gemini-nano-banana-2.1` | $0,039 | ✅ (deu 429 no pool compartilhado) |
| `google/gemini-3-pro-image` | $0,155 | não testado |
| `openai/gpt-5-image-mini` | $0,010 | ❌ **alucina** |

### O desastre do gpt-5-image-mini

Testado na sua foto: **não restaurou, gerou outra foto.** Inventou uma segunda
criança no colo do homem, mudou o ângulo da cabeça, trocou o fundo e esmagou o
formato de retrato (717×1536) para quadrado (1024×1024). No recorte 1:1, ampliou
a boca do homem em vez de mostrar a região pedida.

Era o mais barato e foi o pior. **Para restauração, use o Gemini.**

### O que o Gemini acertou

- Corrigiu a cor cruzada do filme (o problema central do seu material)
- Contraste: mediana de 0,787 → 0,459, removendo o véu de baixa densidade
- No recorte 1:1: removeu pó, riscos e ruído, **preservando a trama do tecido**
- Manteve enquadramento, pose e identidade

### Limitações medidas

- **Enviar em resolução cheia não melhora.** Mandei 1868×4000 (7,5 MP) e recebi
  **704×1472** — idêntico ao envio reduzido. O `max_lado_envio=1536` do `.env`
  já evita upload inútil.
- **A saída é ~1 MP, não 4K.** Para resolução alta são duas etapas: Gemini para
  cor e limpeza, depois um upscale dedicado (Real-ESRGAN).

### O prompt

O prompt do `.env` é deliberadamente restritivo. *"Vibrant, deeply saturated,
4K, modern camera technology"* autoriza o modelo a **reinventar** a foto — foi
esse tipo de prompt que produziu a alucinação do GPT.

O prompt atual diz o que fazer, o que **não** fazer, e o que fazer na dúvida
("deixe suave em vez de inventar"). Também trata cor cruzada, que é o problema
real de negativo antigo. **Mantenha as proibições**: são elas que impedem o
modelo de inventar rostos e fundos.

---

## Captura

Nada depois salva uma captura ruim. Em ordem de importância:

1. **Ative o DNG** no Expert RAW ou use o modo Pro. Em dobro (JPG+DNG) é boa
   ideia como backup, mas a conversão sai do DNG.
2. **Luz difusa e uniforme** por trás: tablet com tela branca no máximo, ou
   mesa de luz.
3. **Não estoure a borda laranja.** Tem que ficar clara, não no branco puro.
   O pipeline avisa (`meta["aviso"]`), mas não ressuscita.
4. **Enquadre frouxo, com a borda laranja aparecendo.** Os furos da perfuração
   **não atrapalham** — medi: tirá-los custa 10,8% dos pixels e não melhora
   nada. O que estraga é enquadrar justo e cortar a borda: o contraste cai 25%.
   Não use zoom digital para "limpar" os furos.
5. **Paralelo e fixo**: tripé ou pilha de livros, 15–25 cm.
6. **Foco manual** na granulação, ambiente escuro (evita reflexo).

Detalhes: [docs/digitalizar-com-s22-ultra.md](docs/digitalizar-com-s22-ultra.md)
e [docs/enquadramento.md](docs/enquadramento.md)

---

## Problemas conhecidos do seu material

### DNGs que o LibRaw não decodifica

**Este é o problema mais sério.** Dos 6 DNGs novos, **nenhum** decodifica pelo
caminho bom:

| Arquivo | LibRaw | ImageMagick |
|---|---|---|
| `110646` | ✅ OK | OK |
| `104147`, `104222`, `104253`, `104309` | ❌ Data error | tolera |
| `100136`, `100151`, `101813` | ❌ Unsupported | ❌ recusa |
| os 6 novos (`133515`…) | ❌ Data error | tolera |

Os novos têm metadados **idênticos** ao único que funciona (`comp=7`,
`phot=34892`, 12 bits) e ainda assim falham. Testei 11 variações de parâmetros
do rawpy (`half_size`, `output_bps`, `output_color`, `demosaic`, sem correção
de lente…): **nenhuma funciona**. É limitação do LibRaw 0.22.1, que é o mais
novo disponível para Python.

### O fallback pelo ImageMagick não resolve

Ele aplica o balanço de branco da câmera, o que **neutraliza a máscara
laranja** — o mesmo estrago que o JPEG do celular faz:

| Fonte | Máscara (R/B) | Positivo (p05 / saturação) |
|---|---|---|
| DNG bom (`110646`) | **4,32** | 0,544 / 0,082 |
| DNG novo via ImageMagick | 1,55 | **0,698 / 0,056** |

Positivo lavado, e **a IA não recupera**: mandei esse positivo para o Gemini e
voltou borrado e esverdeado. Por isso o `lote.py` **pula a restauração** quando
a máscara chega fraca (R/B < 2,5) — para você não pagar por isso. Desligue com
`pular_mascara_fraca=false` no `.env`.

### O que fazer

1. **Investigue o modo de captura.** Existe um DNG que funciona
   (`20261012_110646`, 4000×1868) e vários que não. Compare as configurações do
   Expert RAW entre aquela foto e as novas — algum ajuste mudou. Re-fotografe
   algumas de teste e confirme com `tools/diag_dng_falha.py`.
2. **Adobe DNG Converter** (gratuito) converte para DNG padrão que o LibRaw lê.
   Não pude testar (não está instalado), mas é a solução conhecida para DNG
   proprietário.
3. **Use o modo Pro** em vez do Expert RAW, se ele gerar arquivos que o LibRaw
   aceita. O `110646` provavelmente veio de um modo diferente.
4. **Sempre tire JPG junto** — não para conversão (a máscara está perdida nele
   também), mas como seguro: abre em qualquer lugar.

Enquanto isso não for resolvido, o programa entrega o positivo local (útil, mas
lavado) e não gasta IA nesses arquivos.

### Detalhes técnicos

| | Grupo A | Grupo B | Grupo C (novos) |
|---|---|---|---|
| Compression | `52546` | `7` | `7` |
| DNGVersion | 1.7 | 1.6 | 1.6 |
| Bits | 16 | 12 | 12 |
| Resolução | 4000×3000 | 4000×1868 | 4000×1868 |
| LibRaw | Unsupported | Data error | Data error |
| Exemplo | `100136` | `104309` | `133515` |

Verificado por CRC32 contra os ZIPs do Drive: **os arquivos estão íntegros** —
é formato não suportado, não corrupção de transferência. Copiei um arquivo
problemático para disco local e ele falha igual: **não é o Google Drive**.

### Aviso "Data corrupted"

Os DNGs dos Grupos B e C emitem aviso de bloco corrompido em offsets
diferentes. O decodificador preenche a falha; impacto visual desprezível.

### Erro de certificado TLS — é o Kaspersky

Se a chamada de API falhar com `self-signed certificate in certificate chain`,
a causa é a **varredura de conexões criptografadas do Kaspersky** (não proxy
corporativo, como eu supus antes). Ele se põe no meio da conexão e reassina o
certificado com a CA raiz dele. O navegador aceita porque a CA está no
repositório do Windows; o Python não, porque usa o pacote `certifi`, que só tem
as CAs públicas.

Três caminhos:

**1. Exclusões no Kaspersky** — nas configurações da varredura de conexões
criptografadas existe uma lista de exclusões por domínio. Adicione:

```
api.openrouter.ai
openrouter.ai
generativelanguage.googleapis.com
api.openai.com
```

Resolve sem tocar no Python. Custo: essas URLs deixam de ser inspecionadas.
(Os nomes exatos do menu variam entre versões — não consegui confirmar a sua
porque o site da Kaspersky não respondeu.)

**2. O script deste projeto** (usado até agora, e o que recomendo por padrão):

```bash
python tools/consertar_tls.py
set REQUESTS_CA_BUNDLE=%CD%\ca-empresa.pem
```

Ele une as CAs públicas do `certifi` com as CAs confiáveis do Windows —
incluindo a que o Kaspersky instalou. Você **mantém a proteção** E o Python
conecta. Custo: um arquivo e uma variável de ambiente.

**3. Desativar a varredura de conexões criptografadas** no antivírus.
Funciona, mas reduz a proteção em toda a navegação. Não recomendo só por causa
deste programa.

---

## Ambiente

O `pip` trava neste Windows: `%TEMP%` é bloqueado por política (o pip não
consegue desempacotar) e o proxy corporativo derruba o resolutor. O rawpy
também não tem wheel para Python 3.14.

```bash
python tools/preparar_ambiente.py   # baixa as wheels do PyPI (Python 3.13)
python tools/instalar_wheels.py     # extrai com zipfile, sem pip
```

Resultado: `.venv\Scripts\python.exe` com numpy, Pillow, rawpy 0.27.1
(LibRaw 0.22.1) e requests.

**Use sempre `.venv\Scripts\python.exe`**, não o `python` do sistema — o 3.14
não tem rawpy e não lê DNG.

---

## Arquivos

```
neg35/
  config.py      leitura e gravação do .env (pastas, chave, modelo, prompt)
  core.py        álgebra de cor: normalização, base do filme, inversão
  post.py        balanço, contraste, saturação, nitidez (tudo em linear)
  pipeline.py    orquestração, carregamento RAW/JPEG+EXIF, salvar
  api.py         Etapa 2: Gemini / OpenAI / OpenRouter
  synthetic.py   negativo sintético para validar a matemática
  render.py      imagens de diagnóstico antes/depois
  cli.py         linha de comando (desenvolver, pasta, amostrar, comparar)
tests/
  test_pipeline.py   19 testes (round-trip, regressões de gama, robustez)
tools/
  lote.py                FLUXO COMPLETO: lista, escolhe, estima, converte
  preparar_ambiente.py   baixa wheels do PyPI (contorna pip travado)
  instalar_wheels.py     extrai wheels sem pip
  consertar_tls.py       resolve erro de certificado corporativo
  restaurar_ia.py        restaura UMA imagem, com comparação lado a lado
  inspecionar_dng.py     diz se um DNG é Bayer cru ou já demosaico
  comparar_dngs.py       separa DNGs suportados dos problemáticos
  verificar_integridade.py  CRC32 contra o ZIP
  dng_teste.py           cria DNG sintético válido (para testes)
  gerar_teste.py         cria amostras sintéticas
  _teste_lote.py         testa o fluxo do lote sem gastar API
docs/
  digitalizar-com-s22-ultra.md   guia de captura
  enquadramento.md               furos da perfuração e enquadramento
  restauracao-ia.md              qual modelo funciona e qual alucina
```

### Testes

```bash
.venv\Scripts\python.exe tests\test_pipeline.py    # núcleo de cor
.venv\Scripts\python.exe tools\_teste_lote.py      # fluxo do lote (grátis)
```

Os testes provam o round-trip e cobrem por regressão os bugs reais que
apareceram:

- normalização dupla de `uint8` (branqueava as imagens de diagnóstico)
- **gama aplicado sobre dados já lineares** (lavava o positivo do DNG)
- `\N` de um caminho do Windows tratado como quebra de linha no `.env`
- `--env` ignorado: `ler_env(None)` caía sempre no `.env` padrão
- fallback do ImageMagick dependia de `%TEMP%`, que pode estar bloqueado
- divisão por zero no balanço com imagem uniforme

O caso do gama merece destaque: o sintoma parecia ser "DNG é pior que JPG", e a
causa era tratar as duas fontes como se estivessem no mesmo espaço de cor.
Nenhum teste antigo pegava isso porque todos usavam entrada sRGB.

