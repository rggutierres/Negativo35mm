# O zoom mostrava a imagem velha

## O sintoma

Depois da correção do cache, a aba **Comparar** passou a mostrar a foto nova.
Mas ao clicar na imagem para ampliar, o zoom mostrava a versão **antiga,
recortada**.

## A causa: URL do zoom não mudava

O cartão da comparação usa uma URL com versão:

```
/midia/comparar/<nome>?w=2200&s=<compVersao>     ← mudou, atualizou
```

O zoom usava uma URL **fixa**:

```
/imagem/restaurado/<nome>?w=2600                 ← não mudou, ficou no cache
```

Mesmo com o servidor passando a enviar `no-store`, isso **não apaga o que o
navegador já guardou** antes da regra existir. Aquele endereço exato tinha uma
cópia válida por 1 hora, e o navegador a entregava sem consultar o servidor.

Por isso os dois se comportaram diferente: um tinha versão na URL, o outro não.

## A correção

Toda URL de imagem grande passou a ser montada por uma função única:

```js
function urlImagemGrande(tipo, nome) {
  return `/imagem/${tipo}/${encodeURIComponent(nome)}?w=2600&s=${Date.now()}`;
}
```

O `Date.now()` garante endereço diferente a cada abertura — não depende de
nenhuma política de cache, nem do estado da tela.

Usada em **cinco** lugares: clique no cartão, botão de modo do cartão, recarga
depois de recortar, recarga depois de girar e o visor de comparação.

O visor de comparação (`w=1500`) também ganhou token.

## Verificado no servidor em execução

```
usos de urlImagemGrande : 5
monta com Date.now()    : sim
clique usa restaurado   : sim
comparador com token    : sim
no-store nas rotas      : no-store
```

## Dois testes que precisaram de ajuste

A refatoração mudou o texto do código e quebrou duas verificações que procuravam
string literal:

- `"/imagem/restaurado/" in js` — o texto não existe mais, agora é
  `urlImagemGrande('restaurado', ...)`;
- a janela de busca do botão **Refazer** começava no primeiro `comp-slider`
  (que agora aparece antes, na montagem do cartão) e não alcançava o
  `irParaOProgresso()`.

Ambas passaram a conferir a **intenção**, não o texto exato.

## Lição

`no-store` no servidor corrige o futuro, não o passado. Enquanto existir uma URL
fixa apontando para um arquivo que muda, o navegador pode continuar entregando a
versão antiga que já guardou. A URL precisa mudar junto com o conteúdo.
