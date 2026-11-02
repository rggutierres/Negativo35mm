# Abas de falha: conversão e restauração

## O que mudou

1. A aba **"Falhas na conversão"** passou a se chamar
   **"Falha na Conversão para Positivo"**.
2. Aba nova: **"Falha na Restauração"**, com botão **Forçar restauração** em cada
   foto.

## Por que duas abas

São problemas de naturezas diferentes:

- **Conversão**: o negativo não virou positivo. Quase sempre arquivo corrompido
  ou em formato não suportado. O que resolve é reexportar o arquivo.
- **Restauração**: o positivo existe, mas a IA não foi chamada. O caso medido é
  **máscara fraca**.

Juntar as duas faria o usuário procurar um problema no lugar errado.

## O caso relatado: máscara fraca

```
20261012_214914   R/B 2.10
20261012_214922   R/B 1.85
20261012_214938   R/B 2.31
```

O limite é `LIMITE_MASCARA = 2.5`: um negativo bom tem R/B entre 2,6 e 4,5,
porque a máscara laranja do filme faz o vermelho ficar bem acima do azul. Abaixo
de 2,5 o negativo perdeu essa correção, e a IA **não recupera** — ela **inventa
detalhes**, e o resultado engana.

Por isso esses casos **não** são restaurados automaticamente. A tela explica
isso e oferece forçar, deixando claro que é pago.

## Como funciona

**Registro persistido** (`saida/_falhas_restauracao.json`), separado do de
conversão. Grava nome, motivo, detalhe, `mascara_fraca`, `r_b` e data.

Diferença importante em relação à aba de conversão: aqui **não** se varre
"positivo sem restaurada". Isso listaria toda foto ainda não restaurada, que é o
estado normal. Só aparece o que o programa anotou como falha.

Uma foto que já tem restaurada **sai da lista** (a falha foi superada), e
restaurar com sucesso remove do registro.

**Botão Forçar** reusa `/api/restaurar` com `forcar: true` — o mesmo caminho da
caixa "Forçar mesmo com máscara fraca" da tela principal. Não há lógica nova
duplicada.

"Forçar todas" pede confirmação com o custo estimado (US$ 0,04 por foto), porque
é gasto real e o resultado tende a não ser fiel.

## Um bug que encontrei no caminho

`sRGB = preparar_envio(...)` estava sendo chamado **duas vezes** em `restaurar`
— resíduo de uma edição anterior. O efeito era recortar e reduzir a imagem duas
vezes, com o segundo recorte agindo sobre uma imagem já reduzida. Removi a
duplicata.

## Verificação

```
GET /api/falhas-restauro → total: 3, limite: 2.5
20261012_214914  R/B=2.1   fraca=True  positivo=True
20261012_214922  R/B=1.85  fraca=True  positivo=True
20261012_214938  R/B=2.31  fraca=True  positivo=True
GET /api/falhas (conversão) → total: 1  (não quebrou)
nome antigo 'Falhas na conversão' removido
17 verificações, todas passando
```
