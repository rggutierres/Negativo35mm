# Teste: JPEG do celular vs DNG, com restauração por IA

Arquivo: `C:\Temp\teste\20261012_143104` (os dois formatos do mesmo disparo).

## Resultado: os dois caminhos saem lavados

Medido em resolução cheia, com o mesmo pipeline:

| Etapa | Dimensão | p05 | p50 | p95 | saturação | Veredito |
|---|---|---|---|---|---|---|
| Negativo JPG | 1868×4000 | 0,004 | 0,316 | 0,726 | 0,100 | — |
| **Positivo do JPG** | 1868×4000 | **0,749** | **0,953** | 0,990 | 0,046 | ❌ **lavado** |
| **Positivo do DNG** (fallback) | 4000×1868 | **0,832** | **0,963** | 0,994 | 0,033 | ❌ **lavado** |
| Máscara (R/B) — JPG | | | | | | 1,67 |
| Máscara (R/B) — DNG | | | | | | 1,86 |

Um positivo saudável tem p05 em torno de 0,5 e p50 em torno de 0,79 (é o que o
DNG bom `110646` entrega). Aqui o p05 está em **0,75-0,83**: os pretos não
existem, a imagem inteira está jogada nos tons claros.

**Nenhum dos dois é utilizável, e o DNG do fallback é o pior dos dois** —
coerente com a máscara mais fraca dele.

## Por que o JPEG não ajuda

A expectativa era que o JPEG do celular (já revelado, com curva aplicada) fosse
uma fonte razoável. Não é, por dois motivos que se somam:

1. **A máscara laranja está neutralizada** (R/B 1,67) — o balanço de branco
   automático da câmera fez isso. Sem a máscara, a inversão não tem âncora de
   cor e o resultado fica chapado.
2. **O preto vem esmagado** (p05 = 0,004 no negativo) — o celular aplicou o
   ponto preto dele *antes* da inversão. Num negativo isso é destrutivo: o que
   era densidade vira zero absoluto, e o preto da cena se perde.

## A armadilha: a IA "consertou" o que não dava

Ao mandar o positivo lavado do JPEG para o Gemini, ele devolveu uma imagem que
**parece** um positivo plausível — rostos visíveis, pele com tom, detalhe
recuperado (p05 subiu de 0,749 para 0,139, saturação de 0,046 para 0,228).

Parece um resgate. **Não é.** O resultado tem dominante sépia forte, pele
amorenada e vermelho saturado demais. A IA não recuperou a cor: ela **inventou**
uma, porque a fonte não tinha informação de cor para ancorar. Mesmo padrão de
alucinação que o `gpt-5-image-mini` mostrou — menos óbvio, mas igualmente falso.

Moral: **fonte com máscara fraca não se conserta com IA.** Ela produz algo
bonito e incorreto.

## Correção aplicada

Encontrei uma inconsistência: o `tools/restaurar_ia.py` mandava para a IA
arquivos que o `tools/lote.py` já pulava. Corrigido — agora ele mede a máscara
antes e recusa por padrão:

```
máscara  : R/B=1.67  base=[0.616 0.514 0.37]

  !! MÁSCARA FRACA (R/B < 2,5)
     ...Gastar API aqui é provável desperdício.
     Use --forcar para enviar mesmo assim.
```

Os dois programas agora concordam. `--forcar` existe para quando você quiser
insistir conscientemente.

## Rotação: testada e descartada

Você notou que o Expert RAW entrega a foto girada e o Pro não. Testei girando
os arquivos 90° / 180° nos dois sentidos:

| Arquivo | como está | 90 CW | 90 CCW | 180 |
|---|---|---|---|---|
| `143104.dng` | 1,86 | 1,86 | 1,86 | 1,86 |
| `143104.jpg` | 1,67 | 1,67 | 1,67 | 1,67 |
| `110646.dng` (bom) | 4,32 | 4,32 | 4,32 | 4,32 |

**A rotação não influencia a detecção.** O detector usa estatística global, que
é invariante à orientação. A rotação continua importando para *exibição*, mas
não é a causa da máscara fraca.

## Conclusão prática

Este `143104` tem máscara fraca nos dois formatos — **é problema do disparo ou
do arquivo, não do formato escolhido**. Isso é independente do defeito de bloco
corrompido já diagnosticado.

O caminho continua sendo:

1. **Adobe DNG Converter** — para consertar o bloco corrompido e permitir o
   caminho LibRaw (a máscara tende a vir boa, como no `110646`).
2. **Investigar a captura** — se o DNG sai com máscara fraca, vale conferir a
   exposição: a borda laranja precisa ficar clara mas **não estourada**. Máscara
   fraca costuma significar negativo subexposto ou borda mal iluminada.

Para conferir a máscara de qualquer arquivo antes de processar:

```bash
.venv\Scripts\python.exe tools\comparar_modos.py "pasta"
```
