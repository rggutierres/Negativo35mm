# Aba de comparação

Uma aba dedicada para ver o positivo e o restaurado lado a lado, com busca e
seleção.

## Como usar

1. Clique na aba **Comparar**, no topo.
2. **Busque** pelo nome (ex.: `133746`, `Expert`, `Pro`) ou marque na lista.
3. Clique em **Comparar selecionadas**.

Aparecem cartões, um por foto, com o positivo e o restaurado na **mesma
escala**. Clicar na imagem abre grande, com zoom.

Há duas formas de marcar em massa: **Marcar todas** (marca o que estiver
filtrado) e **Desmarcar**.

### Filtro "só as que já têm restaurada"

Ligado por padrão, porque comparar exige os dois lados. Desmarque para ver
também as que só têm positivo — útil para conferir a inversão local antes de
gastar com a IA.

### Atalho da outra aba

Na lista de trabalho, o ícone **⇄** de cada foto já restaurada leva direto para
esta aba com aquela foto marcada.

## Duas decisões de implementação

### 1. A comparação é montada no servidor

Não são duas tags `<img>` lado a lado. O servidor monta **uma** imagem com as
duas metades e o navegador baixa um arquivo reduzido.

Medido: a comparação sai com **14% do tamanho** das duas imagens somadas.

### 2. Lado a lado ou empilhado? Depende da foto

Para foto em pé (que é o caso: 4000x1868 é paisagem, mas 1868x4000 é retrato),
colocar lado a lado dá uma faixa altíssima e estreita — que só cabe na tela
muito reduzida, e aí nada é visível.

O servidor calcula qual arranjo **aproveita mais a tela** e escolhe:

```python
_eh_vertical(largura_a, altura_a, largura_b, altura_b, max_largura)
```

Compara a área útil nos dois arranjos, respeitando os limites de tela. Se
empilhar mostra mais pixels, empilha.

### A legenda é proporcional, não fixa

A faixa de legenda tem 4,5% da altura da imagem (mínimo 48 px), e a fonte escala
junto. Uma faixa fixa de 34 px virava um risco ilegível em imagem grande — foi
medido e corrigido.

## As duas metades ficam na MESMA escala

Ponto que parece detalhe e não é. A IA devolve ~704x1472 enquanto o positivo é
1868x4000: mesma proporção, resoluções diferentes.

Se as duas metades fossem escaladas para a mesma **largura**, o rosto pareceria
maior de um lado e daria impressão falsa de mais detalhe. Por isso as duas são
escaladas pela mesma **altura** e centradas numa caixa com a proporção do
positivo (letterbox). O que se compara é conteúdo, não zoom.

## Limite de cartões

A aba desenha **12 cartões por vez**. Cada cartão é uma imagem montada no
servidor, então desenhar 40 de uma vez deixaria a página pesada. Se houver mais,
aparece o botão **Mostrar mais**, com a contagem (`12 de 27`).

## Testes

O `_teste_web.py` verifica:

- as duas abas existem no HTML e os dois painéis;
- o painel de comparação **nasce escondido** e o de trabalho visível;
- existe a regra `.painel[hidden]` no CSS — sem ela, o `display` do painel
  venceria o atributo `hidden` e os dois apareceriam juntos (o mesmo bug que fez
  a tela de configuração abrir sozinha);
- busca, lista, área de resultado, marcar/desmarcar e filtro existem no HTML
  **e** têm evento ligado no JS;
- o atalho ⇄ da grade leva para a aba.

O `_teste_comparador.py` cobre a montagem: PNG válido, limite de largura,
letterbox com folga central, economia de bytes e os erros de arquivo faltando.
