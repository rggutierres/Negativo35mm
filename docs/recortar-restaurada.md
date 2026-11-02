# Recortar a restaurada no visor

## Como usar

Na aba **Comparar**, clique na foto restaurada. No visor:

1. **Recortar** — entra no modo de recorte. Aparece uma caixa sobre a imagem,
   com o resto escurecido.
2. **Arraste as alças** das quatro bordas (topo, base, esquerda, direita) até o
   enquadramento desejado. Há uma grade de terços dentro da caixa.
3. **Cortar** — grava no arquivo. **Cancelar** sai sem mexer em nada.

## Decisões que importam

### A coordenada é em FRAÇÃO, não em pixel

O recorte é guardado como 0..1 da imagem. Isso permite a mesma caixa servir para
a tela (em qualquer zoom, qualquer tamanho de janela) e para o servidor, que
corta o arquivo.

Se fosse em pixel da tela, o recorte dependeria do zoom em que o usuário estava —
e a foto seria cortada no lugar errado.

### Por que existe o wrapper `#visor-fig`

A imagem sozinha não tem uma caixa que acompanhe seu tamanho exato: ela é
dimensionada por `width`/`height` em estilo. Por isso ela vive num
`div` com `display: inline-block`, que passa a ter **exatamente** o tamanho da
imagem exibida. A caixa de recorte é posicionada em porcentagem desse wrapper,
então se alinha com a imagem em qualquer tamanho.

### O giro é descartado ao entrar no recorte

Se a imagem estiver girada só na tela, a caixa de recorte não corresponderia aos
pixels do arquivo. Ao entar no modo de recorte, o giro visual é zerado e um aviso
explica. Como girar tem botão próprio para salvar, nada se perde.

### Cópia de segurança antes de gravar

Recortar errado é fácil e a restauração custou dinheiro. O arquivo é copiado para
`<restaurada>/_antes_da_rotacao/` antes de ser sobrescrito. Essa subpasta não
aparece na tela (a listagem usa `glob("*_restaurado.png")`, que não entra em
subpasta).

### Validações no servidor

| caso | resposta |
|---|---|
| coordenada fora de 0..1 | recusado |
| retângulo invertido (x1 < x0) | recusado |
| lado menor que 5% | recusado |
| retângulo é a imagem inteira | recusado ("nada a recortar") |
| foto sem restaurada | 404 |

A última é importante: cortar "a imagem inteira" seria gravar uma cópia idêntica
e encher a pasta de backups sem motivo.

## Verificação

```
antes : 1472x704
recorte 0.1,0.2 -> 0.9,0.8
depois: 1178x422   (esperado ~1177x422)
backup: existe
listagem da tela: 0 backups
fora de 0..1 / invertido / <5% / imagem inteira / foto inexistente: todos recusados
arquivo restaurado ao original no fim do teste
```

Arrasto com **Pointer Events**, que cobre mouse e toque com o mesmo código.
As alças têm 14 px de área de pega e 3 px de desenho, para serem fáceis de pegar
sem poluir a imagem.
