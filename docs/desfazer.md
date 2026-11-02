# Botão Desfazer

## O que faz

Volta a imagem restaurada ao estado **anterior ao último ajuste**. Serve para
quando a correção de olhos vermelhos pega demais, o recorte sai errado ou o giro
não era aquele.

Um botão **Desfazer** no visor, ao lado de "Olhos vermelhos".

## Como funciona

Toda operação que altera o arquivo já guarda uma cópia antes de gravar, em
`saida/restaurada/_antes_da_rotacao/`:

| operação | nome da cópia |
|---|---|
| giro | `<foto>_restaurado_<data>.png` |
| recorte | `<foto>_restaurado_recorte_<data>.png` |
| olhos | `<foto>_restaurado_olhos_<data>.png` |

O desfazer **usa a cópia da operação que acabou de ser feita**, não "a mais
recente da pasta". A diferença importa: se você girou e depois corrigiu os olhos,
"a mais recente" seria a do giro — e desfazer levaria a dois estados atrás.

A tela guarda o nome devolvido por cada operação (`ultimoBackup`) e o envia de
volta. Se a página for recarregada e o nome se perder, o desfazer cai na cópia
mais recente daquela foto.

## Segurança, porque aqui se copia arquivo

`backup` vem do navegador, então não dá para confiar:

| tentativa | resultado |
|---|---|
| caminho com `..` apontando para fora | **recusado** |
| cópia de outra foto | **recusado** ("a cópia não pertence a esta foto") |
| arquivo inexistente | recusado (404) |

O nome enviado é reduzido a `Path(nome).name` — descarta qualquer diretório — e
precisa **começar pelo nome desta foto**. Sem essas duas checagens, o campo
viraria um "leia qualquer arquivo do disco e grave como imagem".

## O que NÃO é guardado

Desfazer **não** guarda cópia do estado que está sendo descartado. Fazer isso
permitiria alternar sem parar entre dois estados e encheria a pasta de cópias.
Desfazer significa: aquele resultado não serve.

## Verificação

```
giro 1472x704 -> 704x1472
desfazer com a cópia específica -> 1472x704   igual ao original
desfazer sem informar a cópia   -> 1472x704   igual ao original
caminho com '..'                -> recusado
cópia de outra foto             -> recusada
arquivos reais                  -> intactos
```

O teste `_teste_undo_seg.py` usa **arquivos que existem** de outra foto: um
arquivo inexistente já falharia por não existir, e isso não provaria a checagem.

## Limitação

O desfazer volta **um** passo. Não há histórico múltiplo: cada desfazer usa uma
cópia e a consome (a cópia continua no disco, mas a próxima vez pegaria a mesma,
caso seja a mais recente). Para voltar vários passos, abra a pasta
`_antes_da_rotacao/` e copie a versão desejada — os nomes têm data e hora, e o
tipo de operação.
