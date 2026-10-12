# Resultado do Adobe DNG Converter

Testado com o executável instalado (`C:\Program Files\Adobe\Adobe DNG Converter`,
versão 18.7).

## O Adobe resolveu a decodificação

| Arquivo | Antes | Depois do Adobe |
|---|---|---|
| `143104` | ❌ Data error (bloco em 953516) | ✅ **decodifica** |
| `Pro_141119` | ❌ Data error (bloco em 1631779) | ✅ **decodifica** |
| `Expert_141057` | ❌ Unsupported (compressão 52546) | ❌ ainda falha |

E não só decodifica: **a máscara laranja ficou melhor**.

| Arquivo | Máscara R/B antes | depois |
|---|---|---|
| `143104` | 1,86 | **3,35** |
| `Pro_141119` | 1,76 | **3,30** |
| Referência boa (`110646`) | — | 4,32 |

O Adobe grava sem compressão (`comp=1`), o que elimina o bloco defeituoso.
Todos os modos de conversão (`-c`, `-u`, `-l`, `-flossless`) dão resultado
idêntico.

## Bug que encontrei e corrigi no meu código

O positivo ainda saía lavado (p05 = 0,807). A causa **não era o Adobe**: era o
meu `inverter_negativo`.

Ele normalizava pelo **máximo global** da imagem. Quando qualquer região é mais
clara que o filme virgem — luz direta, reflexo, a própria perfuração — esse
pixel satura e o branco inteiro estoura.

Troquei por um **ombro de destaque por canal**, que é o que filme de verdade
tem: o filme virgem vira um branco conhecido (0,90) e o que passa disso é
espremido em 0,90..1,0 com uma curva logarítmica, preservando separação em vez
de cortar.

Resultado, medido nos arquivos salvos:

| Fonte | p05 | p50 | saturação |
|---|---|---|---|
| `143104` **antes** da correção | 0,807 (lavado) | 0,950 | 0,037 |
| `143104` **depois** | **0,327** | 0,867 | 0,090 |
| `Pro_141119` depois | 0,314 | 0,878 | 0,087 |
| Referência boa `110646` | 0,274 | 0,701 | 0,133 |

O `143104` saiu de "sem preto nenhum" para "faixa razoável".

## Erro de método que cometi (e que me levou a conclusões erradas)

Durante a investigação eu medi o positivo local com `linear_para_srgb` (que
codifica gama) e o positivo da IA medindo o dado cru. **Comparava coisas
diferentes** e por isso alternei entre "melhorou" e "piorou" várias vezes.

Corrigido: agora tudo é medido do **arquivo salvo**, que é o que o olho vê.
Confirmado que o pipeline preserva os dados (medir o positivo e medir o arquivo
salvo dão o mesmo número).

Também confirmei, com um teste de valores conhecidos, que a função de inversão
está **correta**:

| transmitância | positivo linear | o que significa |
|---|---|---|
| 1,00 (filme virgem) | 0,037 | preto ✅ |
| 0,80 | 0,200 | sombra |
| 0,50 | 0,500 | meio tom |
| 0,25 | 0,750 | luz |
| 0,05 | 0,950 | quase branco |
| 0,00 | 1,000 | branco ✅ |

## O que ainda falta calibrar

Comparação final, mesma métrica para todos:

| versão | mean | p05 | p50 | sat | leitura |
|---|---|---|---|---|---|
| Adobe 143104 (local) | 0,793 | 0,327 | 0,867 | 0,090 | faixa razoável |
| REFERENCIA 110646 (local) | 0,694 | 0,274 | 0,701 | 0,133 | faixa razoável |
| JPG+IA | 0,515 | 0,139 | 0,546 | 0,228 | faixa razoável |
| Adobe+IA | 0,212 | 0,002 | 0,146 | 0,103 | **escuro demais** |
| DNG+IA (fallback) | 0,220 | 0,000 | 0,172 | 0,100 | **escuro demais** |

O caminho local agora está consistente (sequer duas fontes na mesma faixa).
Mas os positivos que passam pela IA **saem escuros demais** — a IA recebe uma
entrada clara (p50 0,87) e devolve escura (p50 0,15), quando o esperado era
0,4-0,6.

Isso é calibrável: falta uma curva de tom na fronteira de exibição, que mapeie
a faixa linear do filme para uma faixa de display natural. Hoje o positivo
transfere a escala linear direto, o que deixa o resultado mais claro que o
ideal e confunde a IA.

## Conclusão prática

**O Adobe DNG Converter resolve o bloqueio principal** — os arquivos passam a
decodificar com máscara boa. Vale converter os 13 arquivos problemáticos.

O `Expert_141057` continua falhando: a compressão `52546` é proprietária e o
Adobe não a converte (provavelmente porque a origem nem é RAW de sensor). Esse
arquivo está perdido; use o JPG dele se precisar.

Próximo passo, se quiser: calibrar a curva de tom, para o positivo local sair
numa faixa mais natural e a IA responder de forma consistente.
