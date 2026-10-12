# Enquadramento: os furos da perfuração atrapalham?

**Resposta curta: não precisa se preocupar com os furos. Enquadre frouxo, com
a borda laranja aparecendo. Só não enquadre tão justo que a borda suma.**

Testado na sua foto `20261012_110646.dng` (1868×4000).

---

## O que foi medido

| Enquadramento | Resolução | Base R/B | p05 (contraste) |
|---|---|---|---|
| **Com furos + borda** (como está) | 1868×4000 (7.472.000 px) | **4,32** | **0,544** |
| Sem furos, mantendo a borda | 1868×3560 (6.669.000 px) | 4,35 | 0,530 |
| Sem furos e sem a borda | 1868×3240 (6.050.000 px) | 4,12 | 0,409 |
| Só os rostos (bem fechado) | 1027×2000 (2.054.000 px) | 3,76 | 0,493 |

### Leitura

- **Tirar os furos custa 10,8% dos pixels e não melhora nada.** Base e
  contraste ficam iguais ou levemente piores.
- **O que realmente machuca é cortar a borda laranja**: o contraste cai de
  0,544 para 0,409 (-25%) e a base piora. A borda é a **âncora de cor**.
- Enquadrar muito fechado (só os rostos) perde 73% dos pixels e ainda
  degrada a base para 3,76.

### Por que os furos não atrapalham

A detecção da base usa o percentil alto seguido de **média robusta** (descarta
10% de cada extremo). Os furos são laranja como o filme virgem, então mesmo
quando entram na conta apontam para a cor certa. Eles não são um veneno — são
o mesmo material, só mais iluminado.

O problema que apareceu na **primeira** foto não era a perfuração: era um bug
meu de recorte e outro de gama. Corrigidos.

---

## Recomendação prática

### Faça

- **Enquadre frouxo**: o quadro do negativo **+ a borda laranja**. Se sobrar
  furo, tudo bem.
- **Deixe uma folga nas laterais.** Serve para dois fins: mantém a âncora de
  cor e te dá margem para corrigir perspectiva depois, sem perder conteúdo.
- **Fotografe reto**, celular paralelo ao filme, 15–25 cm.
- **Foco manual** na granulação, ambiente escuro (evita reflexo).
- **Não estoure a borda laranja.** Ela tem que ficar clara mas não no branco
  puro. O pipeline avisa (`meta["aviso"]`) se estourou.

### Não faça

- **Não use zoom digital** para "limpar" os furos. Zoom digital é recorte
  seguido de ampliação: você perde pixels sem ganhar nada, porque tirar os
  furos não melhora o resultado. (Zoom **óptico** é outra história — este é
  lossless.)
- **Não enquadre justo no quadro.** É o único erro de enquadramento que
  estraga o resultado de verdade: sem filme virgem visível, a detecção passa
  a adivinhar pelos pixels mais claros da **cena** — que num negativo podem
  ser mais claros que a própria máscara — e a cor sai errada.
- Não se preocupe em alinhar perfeitamente o quadro na hora. O programa
  recorta depois, e sem perda, porque você tem os pixels sobrando.

---

## Resumindo em uma frase

**Sobra de filme é bom, falta de filme é ruim.** Melhor pecar por enquadrar
demais do que de menos.
