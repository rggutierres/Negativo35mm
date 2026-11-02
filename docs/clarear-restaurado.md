# Clarear o resultado da IA

## O sintoma

Na comparação lado a lado, o restaurado saía visivelmente mais escuro que o
positivo.

## Quanto, medido

Três fotos, comparando a mediana da luminância (p50) do positivo com a do
restaurado:

| foto | p50 positivo | p50 restaurado | diferença |
|---|---|---|---|
| 20261012_133734 | 0,653 | 0,438 | **−0,215** |
| 20261012_133756 | 0,638 | 0,433 | **−0,205** |
| 20261012_133814 | 0,598 | 0,316 | **−0,282** |

Média: **0,234 a menos**. Consistente nas três, então não é acaso de uma foto —
é comportamento do modelo.

## O que foi implementado

`post.casar_exposicao`: depois que a IA devolve, o programa clareia o resultado
para casar com o positivo.

### Como faz, e as duas tentativas que não deram certo

**Ganho multiplicativo** (`v * k`, nos três canais igualmente). É o que melhor
preserva a cor, e por construção: multiplicar os três canais pelo mesmo número
mantém a razão entre eles, que é o que define a cor.

Testado com uma imagem de cor conhecida:

| método | mudança de cor |
|---|---|
| **ganho** | **0,015** |
| gama único | 0,062 |
| somar a diferença aos canais | 0,079 |

O gama único parecia mais natural (clareia os meios-tons e preserva o topo), mas
trata cada canal de forma diferente: no teste, o vermelho foi de 0,571 para
0,452.

**O problema do ganho era o corte no branco.** Com o ganho que estas fotos
pedem, o que já estava claro passa de 1,0 e vira branco puro — medido, **38% da
imagem**, e o positivo **não tem um único pixel** em branco puro.

**Solução: limitar o ganho pelo topo da imagem.** O ganho é reduzido até que o
pixel mais claro (P99,9) não chegue a 1,0. Nada é cortado e a cor fica
exatamente preservada.

Tentei antes, sem sucesso: comprimir a imagem toda com `x/(1+x)` (satura cedo
demais, o branco continuou em 25–39%) e ancorar uma curva em vários pontos
(preservava o realce, mas mudava a cor).

## Resultado

| foto | p50 antes | p50 depois | p50 positivo | branco | erro de cor |
|---|---|---|---|---|---|
| 133734 | 0,438 | **0,507** | 0,653 | 0,0% | 0,005 |
| 133756 | 0,433 | **0,539** | 0,638 | 0,0% | 0,006 |
| 133814 | 0,316 | **0,393** | 0,598 | 0,0% | 0,026 |

Cor preservada (erro 0,005–0,026) e **zero** branco estourado.

## A limitação, dita com clareza

**O ganho é limitado pelo pixel mais claro da imagem.** Sempre que o resultado
da IA já tem um ponto quase branco, o limite impede alcançar o alvo.

Medido nas três fotos: o ganho aplicado foi 1,37x / 1,61x / 1,24x, quando o alvo
exigiria ~1,6x a 2,0x. Por isso a mediana chega a 0,51–0,54 em vez de 0,60–0,65.

Para clarear **mais**, sem estourar, seria preciso comprimir o realce — e isso
muda a cor. É uma escolha, não um defeito:

- **como está**: cor fiel, sem branco estourado, clareia até onde dá;
- **com realce comprimido**: clareia mais, com alguma perda de cor nos tons
  claros.

O controle **"Clarear: força"** na engrenagem ajusta quanto da correção é
buscada — mas nas fotos medidas o limite de segurança é que manda, então subir
para 1,0 não muda o resultado. O que muda é desligar a proteção, e isso eu não
recomendo.

## Se quiser mais claro de verdade

O caminho mais eficaz é **mudar o que enviamos**, não o que fazemos com a
resposta: o modelo escurece, então mandar um positivo mais claro faz ele
devolver mais claro. Como o ganho de entrada não tem problema de corte (é o
positivo, que já está em 0,61), dá para clarear a entrada com o mesmo ganho
seguro.

Não implementei porque é mais uma variável em jogo, e a atual já resolve parte
do problema. Se ainda incomodar, é o próximo passo — me diga.

## Testes

`tools/regravar_env.py` regrava o `.env` acrescentando chaves novas ao `Config`
sem perder valores. Existe porque isso aconteceu duas vezes: campo criado no
código, esquecido no arquivo, e o usuário não encontrava no `.env`.

O `_teste_env_completo.py` compara **todos** os campos do `Config` com as chaves
escritas no arquivo, então a falta é detectada.
