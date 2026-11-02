# A imagem escura: três bugs com a mesma causa

## O sintoma

A restauração saía escura — 0,038 de mediana, contra 0,465 da versão que o
usuário fez à mão no Gemini. Depois da primeira correção, "melhorou um pouco,
mas continua muito longe".

## A causa comum aos três

`core.normalizar(img, linear=False)` **decodifica o gama sRGB**. O nome do
parâmetro descreve a *entrada* ("o dado que você está me dando é sRGB?"), mas é
fácil ler como "não mexa no gama".

Em três pontos do código eu passei dado **que já estava em sRGB** para essa
função, e cada passagem escureceu a imagem para cerca de 1/3 do brilho:

| # | Onde | O que acontecia |
|---|---|---|
| 1 | `servidor.preparar_envio` (via `pipeline.carregar`) | a imagem ia para a IA com p50 0,039 em vez de 0,610 |
| 2 | `servidor.restaurar` ao gravar | a IA recebia 0,5216 e o arquivo saía 0,2627 |
| 3 | `pipeline.py`, `lote.py`, `restaurar_ia.py` | mesmo erro em três outros pontos |

Como cada um encolhia o brilho por conta própria, os efeitos se somavam. Foi por
isso que a primeira correção "melhorou só um pouco": ela consertou o envio, e a
gravação continuou escurecendo.

## A correção

Função nova, `core.para_float01`, que **só cuida de escala e canais** — não toca
em gama:

```python
def para_float01(img):
    """Converte para float [0,1] SEM mexer em gama."""
```

Ela convive com `normalizar`, que continua sendo a ferramenta certa quando o
objetivo é **converter** para luz linear (é o que o pipeline de inversão espera).

Use:

- `para_float01(img)` → o dado já está no espaço de cor certo, quero em float;
- `normalizar(img, linear=...)` → quero converter para luz linear;
- `pipeline.carregar_srgb(caminho)` → quero os pixels como estão no arquivo.

## Resultado medido, ponta a ponta

```
positivo no disco                p50 = 0,5216
o que a IA RECEBE                p50 = 0,5216     (idêntico)
o que é GRAVADO                  p50 = 0,5490     (a IA devolveu claro)
```

Antes: a IA recebia 0,039 e o arquivo saía 0,2627.

## O segundo problema: 12 processos acumulados

Os testes de reinício falhavam porque **12 processos do neg35** estavam abertos
ao mesmo tempo. Quando um novo subia, encontrava a porta 8765 ocupada, escolhia
outra, e a janela antiga continuava atendendo na 8765 — a que o navegador abre.

Ou seja: o `reiniciar.cmd` "não funcionava" porque o servidor velho nunca saía.

**Ferramenta nova:** `verificar.cmd` pergunta ao programa em execução quais
recursos ele tem e compara com o código em disco:

```
recursos no código em disco : 8
recursos na janela aberta   : 6

RESULTADO: a janela está DESATUALIZADA.
Faltam: cor_no_envio [a tela precisa deste]
```

## Terceiro problema: o Explorer não abria

O endpoint `/api/abrir-pasta` estava no `do_POST`, e a tela chamava com GET.
Movido para o `do_GET`. Testado: responde 200 e abre as três pastas; recusa
qualquer valor que não seja `origem`, `positivo` ou `restaurada` (não aceita
caminho arbitrário, para não virar um "abra qualquer coisa").

## Como conferir depois de mexer

```bash
verificar.cmd
```

Ele diz se a janela aberta está atualizada. Se estiver, os recursos batem com o
código em disco.

## Nota para quem for manter o código

O nome `linear` em `core.normalizar` é a fonte de todos esses bugs. Ele descreve
a **entrada**, não a saída — e a saída é **sempre** luz linear.

Se o dado já está em sRGB e você não quer convertê-lo, **não use `normalizar`**.
Use `para_float01`.
