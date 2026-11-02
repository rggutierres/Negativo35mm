# Preview lavado — a causa era o arquivo, não a miniatura

## O sintoma

Depois de converter para positivo, os previews na tela inicial pareciam
"lavados, mais claros" do que o arquivo na pasta.

## A investigação

Comparei a mediana de luminância da miniatura com a do arquivo. Se a miniatura
fosse gerada com gama dupla (o erro recorrente deste projeto), ela viria mais
clara que o arquivo.

Primeiro medição — pareciam **iguais** (0,519 contra 0,523). Então a miniatura
era fiel, e o problema estava no arquivo.

## A causa: fui eu

Ao corrigir a rotação, reconverti os 26 positivos com:

```python
pipeline.salvar(res.positivo, destino, linear=True, curva=None)   # ERRADO
```

mas `servidor.converter` usa:

```python
pipeline.salvar(res.positivo, destino, linear=True, curva=cur)    # CERTO
```

Com `curva=None`, a luz linear é codificada em sRGB puro. O positivo de filme
tem densidade baixa, então o resultado fica **lavado**. Medido:

| | mediana de luminância |
|---|---|
| positivo correto (antes) | 0,523 |
| positivo que eu gerei | **0,894** |

E como a miniatura é fiel, ela também passou a mostrar 0,89 — o usuário viu
exatamente isso.

## A correção

`tools/reconverter_positivos.py` agora usa `servidor._curva_fn(cfg)`, a mesma
curva de exibição do conversor. E ganhou `--todos`, porque ele só reconvertia os
que estavam com a orientação trocada — com a rotação já corrigida, não regravava
nada e a curva errada continuava.

Resultado: **26 reconvertidos**, mediana do conjunto **0,605** (era 0,894).

## Um teste novo para isso não voltar

`tools/_teste_miniatura.py`:

1. compara a miniatura com o arquivo, foto a foto — falha se diferir mais de 0,03;
2. olha a **mediana do conjunto** — falha se estiver fora de 0,35 a 0,72.

O item 2 é o que pega o erro de curva, porque ele é **global**: sem a curva, todas
as fotos ficam em ~0,85. Verificar foto a foto daria falso positivo, porque duas
destas fotos são naturalmente claras (0,84).

Medido agora: maior diferença miniatura↔arquivo **0,0056**; conjunto **0,605**.

## Uma tentativa que descartei

Cheguei a fazer a miniatura recortar a borda clara do filme, pensando que era ela
que "lavava" o preview. Com o arquivo correto, isso deixaria a miniatura **mais
escura** que o arquivo (medido: 0,40 contra 0,61) — criaria o problema oposto.

O `thumb()` mantém o parâmetro `recortar_borda`, mas **desligado**, com o motivo
escrito no código.

## Estado

- 26 positivos na orientação certa (4000x1868) e com a curva de exibição
- servidor no ar, 14 recursos
- **16 verificações, todas passando**
