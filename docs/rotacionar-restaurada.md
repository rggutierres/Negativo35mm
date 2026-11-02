# Rotacionar a restaurada no visor

## O que foi adicionado

Ao clicar na imagem restaurada (aba Comparar), o visor de zoom agora tem:

- **Rotacionar 90°** — gira na tela, no sentido horário
- **Salvar rotação** — grava o giro no arquivo

O botão de salvar **só aparece depois de girar**, porque girar sem salvar não
deixa rastro nenhum: mostrar o botão desde o início sugeriria que há algo a
salvar quando não há.

## Por que dois botões

Girar com CSS não muda o arquivo. Se só houvesse o giro visual, a foto
continuaria deitada em qualquer outro programa — o que seria uma correção falsa.

## Cópia de segurança antes de gravar

Girar por engano é fácil, e a restauração custou dinheiro. Antes de sobrescrever,
o arquivo é copiado para:

```
saida/restaurada/_antes_da_rotacao/<nome>_restaurado_<data>.png
```

Essa subpasta **não aparece na tela**, porque a listagem usa
`glob("*_restaurado.png")`, que não entra em subpasta. Nada se perde e o usuário
não vê arquivos extras na lista.

## Detalhes de implementação

- Rotação em 90° horário: `PIL.Image.rotate(-90 * giros, expand=True)`. O
  `expand=True` é obrigatório — sem ele a imagem em pé vira uma faixa cortada.
- Grava em `.tmp.png` e renomeia, para não deixar arquivo truncado.
- `giros` é recusado se não for 1, 2 ou 3 (0 não é rotação).
- Só aparece em **imagem única**. Numa comparação lado a lado, girar as duas
  metades juntas não é o que o usuário quer.
- Depois de salvar, a imagem grande é recarregada com `?s=<timestamp>` — sem
  isso o navegador serve a versão do cache e parece que nada mudou.
- Os cartões da aba Comparar são redesenhados no mesmo momento.

## Verificação

```
antes : 1472x704
giros : 1 -> 704x1472        (eixos trocados, correto)
backup: existe=True
voltou: 1472x704             (igual ao original, com 3 giros)
listagem da tela: 0 backups (correto)
giros=0 recusado
foto inexistente recusada
```

## Sobre as três fotos de máscara fraca

`/api/falhas-restauro` agora responde **total=0**, e isso está correto: as três
(`214914`, `214922`, `214938`) **já têm restaurada**, criada às 21:39–21:41 —
ou seja, foram restauradas à força pela tela principal.

A aba mostra **falhas pendentes**. Foto que já tem restaurada sai da lista,
porque o problema foi superado — mantê-la ali faria o usuário tentar de novo algo
que já foi feito, e cada tentativa é paga.

Se preferir ver as falhas mesmo depois de resolvidas, é uma mudança pequena:
bastaria não filtrar por "já tem restaurada". Me diga.
