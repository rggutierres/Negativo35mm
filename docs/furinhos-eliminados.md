# Furinhos do negativo nas fotos restauradas

## O sintoma

As fotos restauradas vinham com os furinhos do negativo e, às vezes, um pedaço do
quadro vizinho.

## A primeira pergunta: prompt ou código?

Promptar a IA para "recortar a borda" é arriscado: o modelo **chuta** onde a
foto termina, e um chute errado corta pedaço da foto — perda irreversível.

A solução foi cortar **antes** de enviar, com verificação. O quadro do filme
35mm é **36×24 mm = 3:2 exato**; isso é geometria do filme, não suposição sobre
a foto. Então a detecção usa a proporção como trava: se o retângulo encontrado
não tiver 3:2 (dentro de 6%), **não corta**.

## O erro que fez o problema persistir

A detecção do quadro funcionava, mas **parava cedo**. Medido na imagem enviada
à IA:

| | luminância | faixa p95−p05 | claro |
|---|---|---|---|
| coluna 0 a 85 | 0,913 | 0,0028 | 100% |
| coluna 150 | 0,370 | 0,901 | 10% |

A faixa de borda ia até a coluna **85**, mas a detecção parou na **50** — e a IA
recebia 35–70 px de faixa lavanda, que ela reproduzia no resultado. Era isso que
o usuário via como "furinhos".

## O que foi implementado

Duas etapas:

1. **`achar_quadro`** — acha o retângulo do quadro, com a trava da proporção 3:2.
   A borda do filme invertida é **lisa** (gradiente 0,00000) e **clara**
   (luminância 0,91), contra 0,005 de gradiente e 0,5 de luminância do quadro.

2. **`_apara_resíduo`** — recua **3% fixos** de cada lado, para o resíduo.

## Por que recuo fixo, depois de quatro tentativas

Tentei achar "onde a borda acaba" com quatro heurísticas. **Todas erraram**:

| critério | resultado medido |
|---|---|
| gradiente < 0,004 | tirou 120–158 px; proporção caiu a 1,45 |
| uniformidade p95−p05 < 0,06 | ainda tirava demais |
| fração de pixels claros > 60% | 132/145/15/110; proporção 1,46 |
| faixa clara > 0,85 e uniforme | parou em luminância 0,88–0,94 (ainda clara) |

O problema de fundo: a transição da borda para a foto é **gradual**, não um
degrau. Não existe um ponto onde "a borda acaba" que uma heurística simples
acerte em todas as fotos — cada tentativa otimizava uma foto e estragava outra.

Um recuo fixo **dispensa acertar**: erra sempre para o mesmo lado e na mesma
medida, e a medida é escolhida para ser pequena.

**Por que 3%:** a faixa residual vai de 45 a 152 px num quadro de 2600 a 2850 px
(1,6% a 5,4%). Um recuo de 3% tira a maior parte. Medido: a proporção final fica
entre 1,473 e 1,529 (alvo 1,500, mediana **1,487**) — o quadro continua sendo o
do filme.

O custo é conhecido: perde-se 3% de cada lado da foto. É imperceptível.

## Teste real

Restaurada a `20261012_133756` de verdade:

```
positivo     : 4000x1868  proporção 2.141
enviado      : 1536x1039  proporção 1.478   (recorte 610,0 → 3245,1784)
resultado    : 1248x832   proporção 1.500
```

As quatro extremidades do resultado:

| lado | luminância | faixa lisa e clara |
|---|---|---|
| esquerda | 0,016 | **0 px** |
| direita | 0,016 | **0 px** |
| topo | 0,008 | **0 px** |
| base | 0,010 | **0 px** |

Luminância 0,008–0,016 é **foto escura**; a borda do filme mede 0,91. As quinas
foram inspecionadas visualmente: conteúdo da foto, sem faixa lavanda.

## O que ficou para trás

Sobra uma franja de **0 a 35 px** (de 50–150 px antes) em algumas fotos. Não
valeu continuar: cada heurística nova tirava de uma foto e comia outra.

Se ainda aparecer faixa em alguma foto específica, o controle **"Folga de borda"**
não resolve (ele *acrescenta* margem). O ajuste seria aumentar o recuo fixo em
`post._apara_resíduo`. Me diga qual foto e eu meço.

## Detalhe de execução

O teste real precisa das variáveis de CA do `run.cmd`, senão falha com erro de
certificado (o proxy corporativo reassina TLS):

```powershell
$env:REQUESTS_CA_BUNDLE = "C:\Temp\Deepseek\negativo35\ca-empresa.pem"
$env:SSL_CERT_FILE = "C:\Temp\Deepseek\negativo35\ca-empresa.pem"
```

E a IA às vezes devolve **só texto, sem imagem** ("Here is the restored
photograph..."). É transitório: repetir resolve.
