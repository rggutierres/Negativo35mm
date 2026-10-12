# Restauração por IA: qual modelo funciona (e qual é armadilha)

Testado na sua foto `20261012_110646`, positivo gerado localmente pelo neg35
(DNG, base R/B 4,32), prompt `PROMPT_ESTRITO` (882 caracteres).

---

## Resultado

| Versão | O que aconteceu |
|---|---|
| **1. Positivo local** | Lavado, baixo contraste, resíduo esverdeado — mas fiel |
| **2. Gemini 2.5 Flash Image** | ✅ **Restauração real**: cor corrigida, contraste firme, traços preservados |
| **3. Gemini, resolução cheia** | Mesma qualidade do 2 — subir 4 MP não ajudou |
| **4. GPT-5 Image Mini** | ❌ **Alucinou outra foto**: criança a mais, outro ângulo, outro fundo |

### O desastre do GPT-5-image-mini

Ele não restaurou: **gerou uma foto nova**. Mudanças observadas:

- **Inventou uma segunda criança** no colo do homem
- Mudou o ângulo da cabeça e a expressão do rosto
- Trocou o fundo (folhagem diferente)
- Esmagou o formato: enviei 717×1536 (retrato), devolveu **1024×1024 (quadrado)**
- O ursinho virou ilustração
- No recorte 1:1, ampliou a boca do homem em vez de mostrar a região pedida

É bonito de olhar e **inútil como restauração**: perdeu a identidade e a
composição. Custou $0,010 — barato e sem valor.

### Por que o Gemini acertou

- Manteve o enquadramento e a pose
- Corrigiu a cor cruzada do filme (o problema central do seu material)
- Pele em tom natural, não plastificada
- No recorte 1:1: removeu pó, riscos e ruído de scanner, **preservando a
  trama do tecido** da jaqueta
- Contraste: mediana subiu de 0.787 para 0.459 com p95 em 0.787 — ou seja,
  ele *escureceu* o meio-tom corrigindo o véu de baixo contraste, que é
  exatamente o que faltava

---

## Métricas

| Versão | lum p05 | p50 | p95 | saturação | detalhe |
|---|---|---|---|---|---|
| Positivo local | 0,544 | 0,787 | 0,961 | 0,082 | 7,5 |
| Gemini (downscale) | 0,213 | 0,459 | 0,787 | 0,130 | 25,0 |
| Gemini (res. cheia) | 0,245 | 0,571 | 0,902 | 0,115 | 12,0 |
| GPT-5-image-mini | 0,037 | 0,233 | 0,771 | 0,231 | 16,7 |

O salto de "detalhe" (7,5 → 25) é remoção de ruído de scanner e grão. O GPT
tem saturação 0,231 porque inventou cores que não existiam.

---

## Descobertas operacionais

### 1. Enviar em resolução cheia não melhora nada

Enviei 1868×4000 (7,5 MP) com `--max-lado 4000`: a saída foi **704×1472**,
idêntica à do envio reduzido. O modelo normaliza a resolução internamente.

**Consequência:** reduza antes de enviar (`--max-lado 1536`, que é o padrão).
Economiza upload e tempo, mesmo resultado. Se você enviar 4 MP, o modelo
descarta a maior parte.

### 2. A saída é ~1 MP, não 4K

Nenhuma das chamadas devolveu mais que **704×1472 ≈ 1 MP**. Se você quer
resolução alta, o caminho é:

1. Gemini para corrigir cor e limpar (~1 MP)
2. Upscale dedicado depois (Real-ESRGAN), que é outra ferramenta

Não espere 4K de um modelo de edição de imagem, apesar do que o prompt pede.

### 3. Custo real

| Modelo | US$/imagem | Serve? |
|---|---|---|
| `google/gemini-2.5-flash-image` | **$0,039** | ✅ sim |
| `google/gemini-nano-banana-2.1` | $0,039 | deu HTTP 429 (pool compartilhado) |
| `openai/gpt-5-image-mini` | $0,010 | ❌ alucina |

O mais barato foi o pior. **Para restauração, use `gemini-2.5-flash-image`.**

### 4. Confira sempre a identidade

O teste que pega alucinação em 5 segundos: olhe **os rostos e o fundo** lado a
lado. Se um detalhe mudou de lugar, o modelo inventou. O recorte 1:1 em
`04_recorte_pele_1x1.png` é gerado justamente para isso.

---

## Recomendação

```bash
# Por foto escolhida:
set OPENROUTER_API_KEY=sk-or-v1-...
.venv\Scripts\python.exe tools/restaurar_ia.py positivo.png \
    --provedor openrouter --modelo google/gemini-2.5-flash-image
```

Fluxo completo, que respeita o custo:

1. **Inversão local** de tudo, a partir do DNG — grátis
2. Escolher as fotos que valem
3. **Gemini 2.5 Flash Image** só nas escolhidas — $0,039 cada
4. Upscale dedicado, se precisar de resolução

Lembre de **revogar a chave de API** usada nos testes e gerar outra.
