# Melhorias: seleção múltipla e giro fino

## 1) Seleção múltipla na aba "Falha na Restauração"

Antes só dava para forçar uma foto por vez, ou todas de uma vez sem escolha.

Agora cada cartão tem **caixa de seleção**, e a barra de botões tem:

- **Marcar todas** / **Desmarcar todas** (o rótulo alterna conforme o estado);
- **Forçar selecionadas (N)** — o número aparece no botão, então dá para conferir
  o que foi marcado antes de gastar;
- **Forçar só esta** em cada cartão, que continua existindo para o caso pontual.

Detalhes que evitam erro:

- cartão marcado ganha **borda e fundo de destaque** — seleção visível de longe;
- foto **sem positivo** tem a caixa desabilitada (não há o que restaurar);
- **Marcar todas** marca só as que têm positivo;
- ao recarregar a lista, marcações de fotos que saíram são **descartadas**;
- a confirmação mostra o **custo estimado** (US$ 0,04 por foto) e repete o aviso
  de que máscara fraca tende a gerar detalhe inventado.

## 2) Giro fino, de 1 em 1 grau

Para negativo fotografado meio torto, o giro de 90 não resolve — e agora não
precisa mais de programa externo.

No visor, ao lado do **Rotacionar 90°**, há um grupo:

```
[ −1° ]  +3,0°  [ +1° ]  [ Zerar ]
```

- os dois controles **somam no mesmo ângulo**: 90° + 2° = 92°;
- o ângulo atual aparece em graus, com sinal;
- **Salvar rotação (3,0°)** grava no arquivo.

### O que muda no servidor

`girar_restaurado(cfg, nome, angulo)` aceita **qualquer ângulo** em graus,
sentido horário. O antigo `rotacionar_restaurado(giros)` virou um atalho que
chama a nova função com `90 * giros`, então o botão de 90° e os testes existentes
continuam funcionando.

### Ângulo que não é múltiplo de 90

`expand=True` faz a imagem **crescer** para caber a rotação, e os cantos vazios
ficam **pretos** (`fillcolor=(0,0,0)`). Isso é de propósito:

- preto não se confunde com conteúdo da foto;
- o usuário vê exatamente onde a imagem original acaba;
- depois de endireitar, é só usar **Recortar** para tirar os cantos.

Medido: 895x625 girada 1,5° vira 649x913.

### O que é recusado

| caso | resposta |
|---|---|
| ângulo 0 | recusado ("não é rotação") |
| acima de 360° | recusado |
| foto sem restaurada | 404 |

E sempre **guarda cópia** antes de gravar, em `_antes_da_rotacao/`.

## Verificação

```
giro 90°      895x625 -> 625x895        (dimensões trocadas)
giro 1,5°     625x895 -> 649x913        (cresce para caber)
ângulo 0      recusado
acima de 360  recusado
atalho de 90° continua funcionando
arquivo real do usuário não foi tocado
19 verificações passando
```
