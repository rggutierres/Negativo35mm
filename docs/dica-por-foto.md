# Dica por foto (opção A) e refazer com brilho

## Opção A: enviar os números medidos junto com a imagem

### A ideia, e por que ela venceu a alternativa

Foi cogitado mandar a foto para um modelo de visão (DeepSeek) e ele devolver os
parâmetros para o nano-banana. **Medi antes de decidir**, e a medição foi
conclusiva:

| foto | erro de exposição da IA | brilho de entrada sugerido |
|---|---|---|
| 133734 | −0,168 | **1,47x** |
| 133746 | −0,183 | **1,47x** |
| 133756 | −0,139 | **1,47x** |
| 133814 | −0,170 | **1,47x** |

**Todas pedem exatamente o mesmo.** Os ajustes necessários são sistemáticos
(assinatura do modelo), não específicos de cada foto. Duas chamadas de modelo
para chegar a uma constante que se calcula localmente em milissegundos seria
complexidade sem ganho.

### O que foi implementado

`servidor.analisar_foto` mede, localmente e de graça:

- luminância mediana, p05, p95
- fração de pixels quase pretos e quase brancos
- cast de cor (G/R e R/B nos tons médios)

`servidor.dica_para_a_ia` transforma isso em texto acrescentado ao prompt.

### A dica é mandatória, não sugestiva

Primeira versão dizia *"não escureça"* — passivo demais. Como sei que o modelo
devolve com mediana em ~68% do que recebe, a dica agora dá **o número que quero
na saída**:

```
MEASURED DATA for this specific image (use it, it is not a guess): median
luminance is 0.64 right now. Exposure requirement: the restored result MUST
have its median luminance between 0.50 and 0.62. The input is already correctly
exposed, so do NOT darken it -- a darker result is a defect, not a style.
Color cast: green measures 1.41x red in the midtones, a cast from the aged
film. Neutralise it toward realistic skin tones.
```

Tamanho: 126 a 427 caracteres, sobre um prompt de 1300. Custo adicional: zero
(é texto).

Também eliminei uma **contradição** da primeira versão, que dizia "neutralize o
verde" e "aqueça" ao mesmo tempo. Agora a instrução de cor é uma só.

## Refazer com brilho, na aba de comparação

Cada cartão de comparação tem agora:

- **controle deslizante** de brilho (0,6 a 2,0, padrão 1,2)
- **botão "Refazer com este ajuste"**
- um aviso de que a foto atual **será apagada**

Ao clicar, o programa apaga a restauração atual, clareia a imagem enviada
conforme o controle e manda de novo à IA. Sem apagar, ficariam duas versões no
disco e você não saberia qual está vendo.

### O brilho usa curva de tom, não multiplicação

Medido: um ganho de 1,2x levava os pixels de branco puro de 0% para **40%**, e a
foto não ficava mais clara — ficava com a metade de cima chapada. O motivo é que
estes positivos já têm ~42% dos pixels na faixa clara (a borda do filme), então
multiplicar joga essa população inteira para o teto.

A curva de Reinhard comprime o topo em vez de truncá-lo. Resultado medido, com
zero branco estourado em todos os níveis:

| brilho | p50 enviado | branco |
|---|---|---|
| 1,0 | 0,638 | 0,0% |
| 1,2 | 0,770 | 0,0% |
| 1,4 | 0,786 | 0,0% |
| 1,6 | 0,804 | 0,0% |

## Comparação: lado a lado e sem borda

Três mudanças, todas pedidas:

1. **Sempre lado a lado.** Antes o programa decidia sozinho e empilhava fotos em
   pé. Agora é sempre horizontal.
2. **Sem faixa de legenda.** Saiu a tarja escura com texto sobre cada metade. As
   imagens ficam encostadas, com 8 px de separação.
3. **Sem borda desperdiçada.** A caixa de cada metade tinha a largura da imagem
   mais alta, deixando faixas escuras enormes. Agora cada metade recebe a largura
   da sua própria imagem, escalada pela mesma altura.

A altura-alvo tem um **mínimo de 620 px**: sem ele, duas fotos de paisagem lado
a lado saíam com 320 px de altura, finas demais para julgar.

As fotos do usuário são 4000×1868 (deitadas), então o conjunto fica em ~4,3:1 —
é geometria, não defeito. Cada metade fica com cerca de 700×1400, boa resolução
para julgar.

## Um erro de teste que vale registrar

O teste de comparação usava um JPEG com **marcador EXIF de rotação**. O pipeline
corrige a orientação, então o fixture virava uma foto em pé enquanto as fotos
reais do usuário são deitadas — e o teste passou a medir outra geometria,
acusando falhas onde não havia.

Corrigido lendo os pixels crus, sem correção de orientação, para o fixture
refletir o que o usuário realmente tem.

## Quando usar a opção B

A **crítica por um modelo de visão** (mandar positivo + restaurado e pedir "o
que a IA errou?") continua valendo para o que não tem métrica: julgamento de
qualidade, defeitos que eu não sei procurar, triagem de quais fotos merecem o
gasto. Está deixado para depois.
