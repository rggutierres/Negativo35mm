# "A imagem restaurada ficou muito escura": o espaço de cor no envio

## O sintoma

A restauração saía escura. Comparação medida com a versão que o usuário fez à
mão no Gemini, com o mesmo positivo:

| imagem | p50 (mediana) | saturação | quase preto |
|---|---|---|---|
| positivo (local) | 0,610 | 0,344 | 8,5% |
| **restaurado (app)** | **0,038** | 0,591 | **53%** |
| **restaurado (Gemini)** | **0,465** | 0,493 | 7,8% |

O app ficou **0,427 mais escuro** que o Gemini, com 53% da imagem quase preta.

## A pista que resolveu

O restaurado do app tinha **exatamente** a mediana do que o programa *enviava*
(0,038 contra 0,039).

Ou seja: **a IA não escureceu nada.** Ela recebeu escuro e devolveu o que
recebeu. O problema estava inteiramente antes do envio.

Isso mudou o alvo da investigação — de "por que o modelo escurece" para
"o que exatamente estamos mandando".

## A causa raiz, em uma linha

```
bruto do arquivo (sRGB)                    0,6096
core.normalizar(b, linear=False)           0,3386   <- linearizou
core.normalizar(b, linear=True)            0,6096
pipeline.carregar(para_linear=False)       0,3386   <- promete sRGB, entrega linear
```

`pipeline.carregar(para_linear=False)` **prometia sRGB e devolvia luz linear.**

O motivo: a função `core.normalizar(img, linear)` **sempre devolve luz linear**.
O parâmetro `linear` descreve a **entrada**, não a saída. E para PNG/JPEG o
`carregar` chamava `core.recortar` → `core.normalizar(..., linear=False)`, que
**decodifica o gama** — o oposto do que o nome do parâmetro sugeria.

Dado sRGB tratado como linear já estava ~3,3x mais escuro. Foi esse valor que
foi enviado.

## As hipóteses erradas que testei antes

Registro porque cada uma consumiu tempo, e todas foram descartadas por medição:

1. **"A IA está escurecendo."** Não — ela devolveu o que recebeu.
2. **"O redimensionamento escurece."** Não: PIL reduzindo 4000x1868 → 1536x717
   preservou a mediana (0,6096 → 0,6096). Testei LANCZOS e BOX.
3. **"A curva de exibição está errada."** Em parte: eu aplicava a curva sobre
   um dado que já tinha passado por ela, causando codificação dupla. Mas era
   **consequência** do problema de espaço de cor, não a causa.
4. **"Converter sRGB→linear e voltar resolve."** Não: a ida e volta não fecha
   (0,3386 linear → 0,6096 sRGB → 0,1016 linear de novo).

## A correção

Função nova e explícita, `pipeline.carregar_srgb`, que devolve os pixels **como
estão no arquivo**:

```python
bruto = np.asarray(im)                     # 0..255
return np.clip(bruto / 255.0, 0.0, 1.0)    # só escala, sem gama
```

E o envio passou a ser só isto:

```
positivo.png (sRGB, já tratado) -> reduzir -> ENVIAR
```

Sem curva, sem balanço, sem normalização — o positivo salvo **já passou por
tudo isso** quando foi convertido (`pipeline.salvar(..., curva=cur)`).

## O resultado, medido

```
positivo no disco        : 0,6096
carregar_srgb            : 0,6096
ENVIADO a IA             : 0,6096    <- idêntico
diferença vs positivo    : -0,0000
```

Antes: 0,0390. Agora: 0,6096. **Quinze vezes mais claro**, e exatamente o
positivo.

## Testes

```bash
.venv\Scripts\python.exe tools\_teste_cor_envio.py
```

- `carregar_srgb` bate com os pixels do arquivo;
- **documenta o comportamento enganoso** de `carregar(para_linear=False)`, para
  registrar por que existe uma função separada;
- `preparar_envio` preserva a exposição;
- redução forte (4200 → 1536) **não altera** a exposição;
- sem redução, não redimensiona.

## Nota para quem for mexer no código

`core.normalizar(img, linear)` e `pipeline.carregar(caminho, para_linear)`
usam o mesmo nome de parâmetro com significados diferentes:

- `normalizar(linear=...)` → descreve a **entrada** (é sRGB ou já é linear?);
- `carregar(para_linear=...)` → promete a **saída** (mas não cumpre em `False`).

Quando precisar do dado de exibição, use `carregar_srgb`. Quando o destino for
o pipeline, use `carregar` — ele trabalha em luz linear, que é o que as etapas
seguintes esperam.
