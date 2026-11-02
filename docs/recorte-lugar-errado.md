# Recorte salvou o lugar errado (caixa e arquivo em referências diferentes)

## O sintoma

Girou 90°, salvou, depois fez o recorte. Na tela o quadro parecia certo, mas o
arquivo foi cortado **no meio** — outro lugar.

## A causa: duas referências diferentes

A caixa de recorte era **desenhada** em porcentagem do wrapper `#visor-fig`:

```js
cx.style.left = `${corte.x0 * 100}%`;   // % do WRAPPER
```

Mas as frações eram **calculadas** sobre o retângulo da **imagem**:

```js
const r = $('visor-img').getBoundingClientRect();   // retângulo da IMAGEM
```

Quando os dois têm exatamente o mesmo tamanho, dá certo. Quando não, o que
aparece na tela é uma coisa e o recorte enviado é outra.

E eles divergem justamente no caso reclamado — **depois de girar**:

1. salvar a rotação **recarrega** a imagem (`src` novo);
2. a imagem fica com `height: 100%` dentro de um pai de altura automática, então
   seu tamanho depende de a carga ter terminado;
3. `entrarModoRecorte` media tudo naquele instante e **fixava o wrapper** no
   tamanho de antes.

Resultado: a caixa era desenhada sobre um wrapper desatualizado, enquanto as
frações se referiam à imagem nova. O recorte saía deslocado.

## As correções

**1. Uma referência só.** `desenharCorte()` agora posiciona a caixa em **pixels**,
medindo o retângulo da imagem, e converte para a origem do wrapper. Desenho e
cálculo passam a usar exatamente o mesmo retângulo.

**2. Redesenho quando algo muda.** A caixa é redesenhada em:

- `load` da imagem (o caso da recarga depois de girar);
- `resize` da janela;
- `scroll` do corpo do visualizador.

**3. Espera a imagem carregar.** Se a imagem não estiver completa ao entrar no
recorte, a caixa é medida de novo quando ela terminar — em vez de usar o tamanho
antigo.

**4. Sair do recorte devolve o zoom.** `sairModoRecorte()` chama `aplicarZoom()`,
senão o wrapper ficava preso no tamanho usado durante a seleção.

## A foto afetada foi recuperada

A `20261012_214922` estava com o corte rejeitado (614x880). Reconstruí a
sequência pelos backups:

```
18:47:40  corte  1472x704 -> 880x614   <- o corte rejeitado
18:55:41  giro   880x614  -> 614x880
18:55:45  giro   614x880  -> 880x614
18:57:01  giro   880x614  -> 614x880   <- estado atual
```

Devolvi o backup sem corte (`..._recorte_20261023_184740.png`, 1472x704), e o
estado rejeitado ficou guardado como
`20261012_214922_restaurado_corte_rejeitado_<data>.png`. **Nada foi perdido.**

Conferido visualmente: a foto voltou inteira, com a moldura do filme.

## Lição

Misturar duas referências de coordenada (porcentagem de um elemento, pixel de
outro) funciona até os dois divergirem — e eles divergem exatamente quando a
imagem muda de tamanho, que é o caso da recarga depois da rotação. Quando o
assunto é coordenada, a origem tem de ser uma só.
