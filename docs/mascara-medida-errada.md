# "0 restauradas, 4 puladas": a máscara era medida no lugar errado

## O sintoma

Ao selecionar 4 fotos e mandar restaurar: **0 restauradas, 4 puladas**.

```
pulado: máscara fraca (R/B=1.00)
```

## A causa

A proteção "máscara fraca" existe para não gastar com negativo que a IA não
recupera. Ela mede o quanto a máscara laranja do negativo sobreviveu — se
R/B ficar abaixo de 2,5, pula.

Só que a medida era feita **no positivo já invertido**:

```python
lin = pipeline.carregar(arq_pos, para_linear=True)   # o POSITIVO
base = core.detectar_base_do_filme(lin)              # procura máscara de NEGATIVO
rb = float(base[0] / max(base[2], 1e-9))
```

`detectar_base_do_filme` procura a parte do filme **não exposta** — que no
negativo é laranja e no positivo vira **preto**. Num positivo não há máscara
nenhuma para achar. A função "funcionava" e devolvia um número, só que sem
significado: **R = 1,0000 exato** em todas as fotos.

Como o limite é 2,5 e o valor medido era ~1,0, **toda restauração era pulada,
sempre** — e a mensagem ("máscara fraca") parecia plausível, o que tornava o bug
invisível.

## A correção

Medir no **DNG original**, pelo **mesmo caminho que a conversão usa**
(`neg35/servidor.py`, `_mascara_do_negativo`).

O detalhe do "mesmo caminho" importa muito. Medir no DNG cru dá valor
enganoso: vários DNG de celular vêm **sem metadados de cor**
(`camera_whitebalance` falha com `LibRawDataError`), e aí o decodificador
aplica balanço de padrão e **apaga o laranja**:

| arquivo | R/B no DNG cru | R/B após o Adobe |
|---|---|---|
| `20261012_133515` | 1,55 | **2,48** |
| `20261012_133734` | 1,55 | **2,71** |
| `20261012_215045` | 1,64 | **2,71** |

Ou seja: uma segunda armadilha, na mesma função.

## O resultado, medido

| | antes | depois |
|---|---|---|
| enviam para a IA | **0** | **19** |
| puladas | 26 | 7 |
| R/B mediana | 1,00 | **2,73** |
| R/B mín/máx | 0,94 / 1,20 | 1,53 / **3,30** |

## Regra nova: "não medido" ≠ "medido ruim"

Se não houver o DNG original (o usuário pode ter apagado, ou a pasta de origem
estar offline), a função devolve `None` e a restauração **não pula**. Não
conseguir medir não é o mesmo que medir mal — na dúvida, quem decide é o
usuário, não uma heurística.

Também é por isso que o limite é explícito e único (`servidor.LIMITE_MASCARA`),
em vez de um `2.5` solto no meio do código.

## Testes

```bash
.venv\Scripts\python.exe tools\_teste_mascara.py
```

- demonstra que medir no positivo dá valor abaixo do limite (o bug);
- confirma que a função correta mede no negativo, e que a máscara Kodak mede
  mais que a neutralizada;
- confirma que a foto com máscara boa **chega até a chamada da IA** (era o que
  o bug impedia);
- confirma que, sem o DNG, **não pula**.

Esse teste usa um limite menor (`LIMITE_SINTETICO = 1.3`) porque a máscara
Kodak **sintética** mede ~1,6 — não os 2,6–4,5 de um negativo real. O teste
verifica a **lógica**, não o valor absoluto do filme sintético.
