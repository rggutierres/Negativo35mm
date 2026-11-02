# Aba Renomear — documentar as tiras de negativo

## Para que serve

Você escreve uma etiqueta física na tira (ex.: `filme1-tira1`) e repete no
programa. Todas as fotos daquela tira passam a ter o prefixo no nome:

```
20261012_133746.dng                 ->  filme1-tira1_20261012_133746.dng
20261012_133746_positivo.png        ->  filme1-tira1_20261012_133746_positivo.png
20261012_133746_restaurado.png      ->  filme1-tira1_20261012_133746_restaurado.png
```

## Renomeia TUDO da mesma foto

Ordem que importa: o programa liga negativo, positivo e restaurada pelo
**nome-base**. Se renomeasse só a origem, o positivo já convertido "perderia" a
ligação com a foto — e a restaurada também.

Por isso cada foto renomeia **todos** os arquivos dela:

| pasta | arquivos |
|---|---|
| origem | `.dng` **e** `.jpg` (todos com o mesmo nome-base) |
| positivo | `<nome>_positivo.png` |
| restaurada | `<nome>_restaurado.png` |

A tela avisa em cada cartão quais acompanham
(`também renomeia: positivo + restaurada`).

## Como a lista decide o que falta

Pelo **registro** (`saida/_renomeados.json`), não pelo formato do nome.

Isso é necessário porque o nome original já tem underscores
(`20261012_133746`), então tentar adivinhar "tem prefixo ou não" pelo padrão
daria erro. O registro guarda de onde para onde cada foto foi.

Foto renomeada sai da lista; foto nova na pasta de origem aparece.

## Segurança

**Nunca sobrescreve.** Antes de mover qualquer arquivo, o programa confere
**todos** os destinos. Se algum já existir, aquela foto é pulada com o motivo, e
as outras continuam. Perder arquivo por colisão de nome seria irreversível.

Também confere tudo antes de mover o primeiro: se houver colisão no meio, a foto
não fica metade renomeada.

## Limpeza do prefixo

O que você digita é ajustado para nome de arquivo válido:

| você digita | vira |
|---|---|
| `filme1-tira1` | `filme1-tira1` |
| `  Filme 1 - Tira 2  ` | `Filme-1---Tira-2` |
| `a/b:c*d` | `abcd` |
| `___x___` | `x` |

Espaço vira hífen, caractere proibido pelo Windows sai, underscore repetido
junta. Prefixo vazio (ou só com caracteres proibidos) é **recusado**.

A mesma limpeza roda no servidor, então o que a tela mostra na prévia é o que
será gravado.

## A tela

- campo do prefixo, com **prévia do nome novo** em cada cartão;
- caixa de seleção por foto e **Marcar todas / Desmarcar todas**;
- botão com a contagem: **Renomear N selecionada(s)** — desabilitado sem prefixo
  ou sem seleção;
- confirmação antes de aplicar, explicando que origem, positivo e restaurada
  serão renomeados e que nada é sobrescrito.

## Verificação (pasta isolada, sem tocar nos seus arquivos)

```
2 fotos sem prefixo na lista inicial
origem com DNG + JPG detectados
renomeou 4 arquivos (DNG, JPG, positivo, restaurada)
nome antigo não ficou em nenhuma pasta
foto renomeada saiu da lista
colisão de nome recusada e arquivo existente preservado
prefixo vazio / só proibidos / lista vazia recusados
```

## Limitação

Não há desfazer para renomear. Para voltar atrás, renomeie de novo com o prefixo
que estava — ou use o registro `_renomeados.json`, que tem `de`, `para` e a data
de cada operação.
