# Onde está o código

Duas pastas, com papéis diferentes:

- **`neg35/`** — o programa em si (a biblioteca). Não roda sozinho.
- **`tools/`** — o ponto de entrada (`app.py`) e utilitários.

## `neg35/` — o programa (5.100 linhas)

| arquivo | linhas | o que faz |
|---|---|---|
| `servidor.py` | 2040 | **o cérebro da interface**: converte, restaura, recorta, gira, renomeia, lista falhas |
| `post.py` | 606 | análise da imagem: casar exposição, clarear, achar o quadro |
| `config.py` | 524 | lê e grava o `.env`; testa se as pastas gravam |
| `pipeline.py` | 427 | a conversão do negativo passo a passo |
| `cli.py` | 380 | uso pelo terminal, sem tela |
| `api.py` | 325 | chamada da IA (OpenRouter/Gemini) |
| `core.py` | 260 | a inversão do negativo (sRGB ↔ linear) |
| `olhos.py` | 170 | filtro de olhos vermelhos |
| `adobe.py` | 146 | conversão de cor pelo Adobe |
| `render.py` | 134 | montagem das imagens de comparação |
| `synthetic.py` | 112 | dados de teste |
| `curva.py` | 109 | curva de exibição |
| `__init__.py` | 12 | versão do pacote |

## `tools/` — entrada e ferramentas (3.000 linhas)

**O que a aplicação usa de fato:**

| arquivo | linhas | papel |
|---|---|---|
| `app.py` | 729 | **ponto de entrada**: sobe o servidor HTTP na porta 8765 |
| `preparar_ambiente.py` | 184 | cria o ambiente Python |
| `instalar_wheels.py` | 74 | instala as bibliotecas |
| `consertar_tls.py` | 191 | conserta o certificado do Kaspersky |
| `conferir_servidor.py` | 70 | confere se a janela aberta está atualizada |
| `regravar_env.py` | 68 | regrava o `.env` com as chaves novas |

**Utilitários avulsos** (rodam por conta própria, fora da tela): `lote.py`,
`reconverter_positivos.py`, `restaurar_ia.py`, `inspecionar_dng.py`,
`diag_dng_falha.py`, `calibrar_curva.py`, `comparar_*.py`, `verificar_*.py`,
`testar_adobe.py`, `baixar_wheels.py`.

**27 arquivos de teste** (`_teste_*.py`, `_conf_*.py`) — não fazem parte da
aplicação; servem para verificar cada recurso.

## `web/` — a tela (3.371 linhas)

| arquivo | linhas | o que é |
|---|---|---|
| `app.js` | 2360 | toda a lógica da tela (abas, zoom, recorte, renomear) |
| `estilo.css` | 614 | aparência |
| `index.html` | 397 | estrutura das abas |

## Como as peças se ligam

```
run.cmd
  -> tools\app.py                  sobe o servidor HTTP na porta 8765
       -> neg35\servidor.py        regras de cada ação
            -> neg35\pipeline.py   orquestra a conversão
                 -> adobe.py  core.py  curva.py  post.py
            -> neg35\api.py        chama a IA
            -> neg35\olhos.py      olhos vermelhos
            -> neg35\config.py     lê o .env
       -> web\index.html + app.js + estilo.css   a tela no navegador
```

## Configuração e atalhos, na raiz

| arquivo | papel |
|---|---|
| `.env` | pastas, modelo de IA, prompt, opções |
| `run.cmd` | abre a interface |
| `reiniciar.cmd` | fecha a antiga e abre uma nova (depois de atualização) |
| `verificar.cmd` | diz qual interpretador está em uso e se está tudo atualizado |
| `requirements.txt` | bibliotecas |
| `README.md` | visão geral |

## Se for mexer no código

- **regra de negócio** (converter, restaurar, recortar) → `neg35/servidor.py`
- **inversão de cor / gamma** → `neg35/core.py` e `neg35/curva.py`
- **tela** → `web/app.js`
- **nova rota HTTP** → `tools/app.py` (GET em `do_GET`, ação em `do_POST`)

Depois de mexer em Python, **reinicie**: o Python carrega o código uma vez.
Depois de mexer em `web/`, basta recarregar a página com Ctrl+F5.
