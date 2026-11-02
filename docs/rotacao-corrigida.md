# Rotação dos positivos — corrigida

## O sintoma

Nas fotos restauradas, as pessoas apareciam **deitadas**, e os furinhos do
filme ficavam nas **laterais** em vez de no topo e na base.

## A causa, medida

Comparei, para o mesmo negativo:

| etapa | dimensões | situação |
|---|---|---|
| DNG (`raw.sizes`) | 4000 × 1868 | correto |
| `desenvolver()` hoje | 4000 × 1868 | **correto** |
| positivo no disco | 1868 × 4000 | **TRANSPOSTO** |

**O código atual estava certo.** Os 26 positivos em disco tinham sido gravados
por uma versão antiga que transpunha o array ao salvar (`salvar` hoje não
transpõe: `Image.fromarray` de um array `(H, W, 3)` dá uma imagem `W × H`).

Como o positivo é a base de tudo — comparação, restauração, recorte — o erro
contaminou o resto. E explica por que o recorte resistiu tanto: a proporção do
quadro ficava invertida (0,69 em vez de 1,45), então a trava reprovava.

## A correção

Ferramenta nova: `tools/reconverter_positivos.py`.

```
python tools/reconverter_positivos.py --conferir   # só lista
python tools/reconverter_positivos.py              # reconverte
```

Ela pergunta ao próprio DNG qual deveria ser a orientação e reconverte só os que
estão trocados. Não apaga nada antes de gravar (o `salvar` grava em `.tmp` e
renomeia), e positivo é regenerável a partir do negativo.

**Resultado: 26 de 26 reconvertidos, 0 falhas, 477 s.**

Depois: `--conferir` → "para corrigir: 0 de 26".

## Um erro que cometi no caminho

A primeira versão da conferência assumiu que `flip` em (5, 6) exigia trocar os
eixos. Não exige: `raw.sizes` **já vem** no espaço de saída. Com a troca
indevida, o "esperado" ficava igual ao arquivo trocado e a ferramenta dizia
"ok" para 26 arquivos errados.

## Efeito no resto

- **Comparação**: o positivo agora aparece em pé (verificado).
- **Restauração**: passa a receber a foto na orientação certa.
- **Recorte**: com a orientação certa, 26 de 26 são detectados e a proporção fica
  1,43 (alvo 1,455). Mas **o recorte continua desligado** — 4 fotos ficam fora da
  tolerância (1,318 a 1,577), então o recurso ainda não é confiável.

## O que ficou pendente

**A imagem restaurada existente está velha**: ela foi gerada a partir do positivo
rotacionado. Na aba Comparar, o lado direito aparece deitado.

Refaça essa foto (aba Comparar → **Refazer**) depois de conferir o resultado.

**Sobre os furinhos:** a orientação corrigida removeu o obstáculo principal, e a
detecção agora acerta a proporção. O que falta é lidar com os furos pretos no
meio da faixa clara — eles derrubam a fração de "claro" por linha de 98% para
52% em 50 px, então a detecção por linha não vê a faixa inteira. Medi também que
**não existe vão escuro** separando a borda do quadro nesta foto (a luminância
cai de 0,98 para 0,50 de forma gradual), então a ideia de usar o vão como
marcador também não serve aqui.

Próxima tentativa sugerida: detectar os **furos** (retângulos pretos regulares) e
usar o último deles como referência para o fim da borda.
