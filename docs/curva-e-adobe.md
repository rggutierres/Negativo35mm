# Curva de tom e conversão Adobe integrada

Duas melhorias implementadas e medidas.

## 1. Curva de tom: por que a imagem saía lavada

O positivo do pipeline é **luz linear** da cena. Codificá-lo direto para sRGB é
tecnicamente correto, mas negativo de filme tem densidade baixa, então:

| fonte | mediana sRGB sem curva |
|---|---|
| `110646` (LibRaw) | 0,701 |
| Adobe `143104` | 0,867 |

O olho espera ~0,50. Daí a sensação de imagem "lavada" que atravessou toda a
investigação.

### Uma curva fixa não resolve

Testei gama fixo: o `110646` melhora com gama ~2,0 e o `143104` só com ~3,2. A
diferença é grande demais — um valor fixo escurece demais um e de menos o outro.
A causa é que o Adobe aplica a própria curva ao converter.

### A solução: ancorar a mediana (adaptativo por imagem)

Em vez de gama fixo, cada imagem recebe o gama que leva a **mediana de
luminância para um alvo** (0,50 em sRGB). Assim:

- a **mediana** fica igual em todas as fotos → exposição consistente;
- a **curva** muda por foto, que é exatamente o que compensa a diferença de
  densidade entre negativos;
- **a cor não é tocada**: o mesmo gama vai nos três canais.

O gama é limitado a 1,2–4,5, para não exagerar numa foto fora do comum.

### Resultado medido

| arquivo | antes da curva | depois |
|---|---|---|
| `20261012_143104` | p50 0,867 | **p50 0,528**, sat 0,168 |
| `Pro_20261012_141119` | p50 0,878 | **p50 0,561**, sat 0,163 |
| `Expert_20261012_141057` | p50 0,867 | **p50 0,500**, sat 0,135 |

A saturação subiu ~80% em relação ao que medimos antes (0,037–0,090).

### Configuração no `.env`

```ini
usar_curva=true
curva_alvo=0.50      # mediana de luminância desejada, em sRGB
curva_gamma=0        # 0 = adaptativo por imagem (recomendado)
curva_preto=0.0      # levanta o preto, se o negativo tiver véu de base
```

## 2. Adobe DNG Converter integrado ao lote

Novo módulo `neg35/adobe.py` e integração automática no `tools/lote.py`.

### Como funciona no lote

Para cada DNG, antes de decodificar:

1. passa pelo Adobe, que regrava sem compressão (eliminando o bloco defeituoso);
2. se o Adobe recusar o arquivo, **segue com o original** — ele pode muito bem
   decodificar, e abortar por causa disso seria errado;
3. o reconvertido fica em `Positivo/_adobe_convertido/` e é **reusado** nas
   próximas execuções (a conversão é lenta).

O log mostra `via Adobe` quando o caminho foi usado.

### Configuração no `.env`

```ini
usar_adobe=true
adobe_exe=          # vazio = procura nos caminhos padrão de instalação
```

### Resultado

| arquivo | antes | depois do Adobe |
|---|---|---|
| `20261012_143104` | Data error (bloco 953516) | ✅ decodifica, máscara 1,86 → **3,35** |
| `Pro_20261012_141119` | Data error (bloco 1631779) | ✅ decodifica, máscara 1,76 → **3,30** |
| `Expert_20261012_141057` | Unsupported (comp 52546) | ✅ decodifica agora (o lote converteu) |

Validação de ponta a ponta com os 3 arquivos reais: **3 processadas, 0 falhas**.

## 3. Balanço de branco: tentei melhorar e não deu

Tentei substituir o gray-world por uma âncora mais confiável — usar o **filme
virgem** como preto neutro (é filme sem exposição, logo deve virar preto
neutro no positivo; nenhuma suposição sobre a cena).

**Medi e piorou.** O preto do filme fica em ~0,001 depois da inversão, então a
correção por canal vira divisão por ruído:

| método | G/B |
|---|---|
| gray-world | 2,32 |
| base (sem trava) | **20,3** |
| base (com trava de ganho) | 3,74 |

O `base` está implementado, protegido por trava (ganho limitado a 1,5x) e
**desativado por padrão**. Fica para experimentação.

### O cast verde continua

Ambos os métodos deixam G/R ~1,16-1,18 nos tons médios. A causa é conhecida e
documentada: **gray-world erra em cena dominada por uma cor** — esta foto é
quase toda folhagem verde, então o método assume que o verde é dominante e
compensa demais.

Solução de verdade seria o usuário informar um ponto neutro
(`--neutro R,G,B`), escolhendo na foto algo que ele sabe ser cinza. Ou usar a
IA, que corrige cor muito melhor que qualquer curva fixa — que é justamente o
que a Etapa 2 faz.

## Arquivos novos e alterados

```
neg35/
  curva.py       NOVO  curva de tom adaptativa (ancora a mediana)
  adobe.py       NOVO  conversão em lote com o Adobe DNG Converter
  config.py            + usar_curva, curva_alvo, curva_gamma, curva_preto,
                         usar_adobe, adobe_exe
  pipeline.py          + balanco_metodo; salvar() aceita curva
  post.py              + balancao_pela_base, mascara_filme_virgem
  __init__.py          exporta curva e adobe
tools/
  lote.py              integra Adobe + curva; log mostra "via Adobe"
  calibrar_curva.py    busca os parâmetros da curva
  comparar_balanco.py  compara gray-world vs base
  testar_adobe.py      testa a reconversão
  _teste_final.py      validação de ponta a ponta com arquivos reais
```

## Testes

```
tests/test_pipeline.py        19/19 passam
tools/_teste_lote.py          todos os passos passam
tools/_teste_mascara_fraca.py tudo certo
```
