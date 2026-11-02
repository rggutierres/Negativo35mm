# `urlImagemGrande is not defined` ao cortar

## O sintoma

Ao clicar em **Cortar**, o recorte era gravado no arquivo, mas aparecia o erro
`urlImagemGrande is not defined`. A imagem não recarregava, então a tela
continuava mostrando a versão anterior.

## A causa: função no lugar errado

Ao criar os construtores de URL eu os inseridi **dentro** de `renderComparar`:

```js
function renderComparar() {
  ...
  caixa.innerHTML = html;

  function urlImagemGrande(tipo, nome) { ... }   // ← aninhada!
  function urlComparacao(nome, largura) { ... }

  caixa.querySelectorAll('.comp-imagem').forEach(...);
}
```

Em JavaScript, `function` declarada dentro de outra função existe **apenas
durante aquela função**. Quem roda fora dela não a enxerga.

Isso explica o comportamento estranho de "cortou mas deu erro":

- o clique no cartão funcionava, porque acontece **dentro** de `renderComparar`;
- o `cortarVisor`, que é do nível do módulo, chamava `urlImagemGrande()` e
  recebia `undefined`.

E a ordem no código escondeu o problema: o recorte é gravado **antes** de
recarregar a imagem:

```js
await post('/api/recortar-restaurado', {...});   // grava no arquivo ✔
toast('Recorte salvo: ...');
$('visor-img').src = urlImagemGrande(...);       // ← estourava aqui
```

Por isso o arquivo foi cortado e a tela não atualizou.

## A correção

As duas funções passaram para o **nível do módulo**, antes de `renderComparar`,
com um comentário explicando por que não podem morar dentro dela.

Também corrigi `salvarRotacaoVisor`, cuja primeira linha tinha ficado colada na
assinatura (`async function salvarRotacaoVisor() {  if (...) return;`).

## Verificado no servidor em execução

```
urlImagemGrande    no modulo: sim
urlComparacao      no modulo: sim
definicoes aninhadas   : nenhuma
usos de urlImagemGrande: 5
salvarRotacaoVisor ok  : sim
```

## Teste que impede a volta

`_teste_web.py` agora verifica, para cada construtor de URL:

1. que existe uma definição **sem indentação** (`^function nome(`);
2. que **não** existe definição indentada (`^\s+function nome(`).

O item 2 é o que pega a aninhada — foi exatamente o estado que causou o erro.

## Lição

Um erro que aparece **depois** de a gravação ter dado certo engana: parece que a
operação falhou quando o dado já foi salvo. Neste caso o toast de sucesso nem
chegou a ser o problema — o arquivo estava cortado, e a única coisa quebrada era
recarregar a imagem. Mas quem vê a mensagem vermelha assume que perdeu o
trabalho.
