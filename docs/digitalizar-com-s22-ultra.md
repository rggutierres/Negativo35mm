# Digitalizar negativo 35mm com o Galaxy S22 Ultra

## O ponto que decide tudo: qual DNG

O S22 Ultra tem **dois** caminhos para DNG, e eles **não** são equivalentes:

| | **Expert RAW** | **Pro (câmera nativa)** |
|---|---|---|
| O que grava | DNG já demosaico, com redução de ruído multi-quadro e correções | **Bayer cru de quadro único** |
| Autenticidade | decisões de cor já tomadas pelo celular | máxima |
| Para digitalizar filme | aceitável, não ideal | **é o que você quer** |
| Onde fica | `DCIM/ExpertRAW/` | `DCIM/Camera/` |

O Expert RAW foi feito para *fotografia* — ele empilha vários quadros, remove
ruído e aplica nitidez **antes** de gravar o DNG. Num negativo, isso significa
que a câmera já mexeu no sinal que você quer preservar. Não é inútil (você
ainda tem 16 bits e bem mais margem que um JPEG), mas não é RAW de verdade.

**Verifique qual você tem:**

```bash
python tools/inspecionar_dng.py "C:\caminho\foto.dng"
```

A linha decisiva é `PhotometricInterpretation`:

- `32803 CFA (Bayer cru)` → RAW de verdade. Ótimo.
- `2 RGB (JÁ DEMOSAICADO!)` → a câmera processou antes de gravar.

Verificação rápida sem Python (PowerShell) — se o arquivo começa com `II*`,
é DNG; se começa com `ÿØ` (`FFD8`), é JPEG com nome trocado:

```powershell
Format-Hex -Path .\foto.dng -Count 4
```

Um DNG real de 12MP tem **~25 MB ou mais**. Se o arquivo tem 3-8 MB, ou é
JPEG disfarçado ou está comprimido/processado.

## Como fotografar (vale mais que qualquer ajuste depois)

Ordem de importância — os três primeiros respondem por ~80% do resultado:

1. **Luz difusa e uniforme por trás.** Tablet com tela branca no brilho máximo,
   ou mesa de luz. Encoste o negativo no vidro. Luz irregular vira erro de cor
   que nenhum software desfaz.
2. **Telefone paralelo e fixo.** Qualquer inclinação vira distorção de
   perspectiva. Use tripé, suporte de celular, ou empilhe livros — mas deixe
   a lente paralela ao plano do filme.
3. **Exposição manual travada** (Pro mode). Ajuste até a máscara laranja ficar
   clara **sem chegar ao branco puro**. Se estourar, a informação morreu.
   O pipeline avisa, mas não ressuscita.
4. **Distância de 15–25 cm.** Perto demais dá distorção de lente; longe demais
   perde resolução. Enquadre só o quadro do negativo.
5. **Inclua um pedaço da borda laranja no quadro.** É por ele que o pipeline
   detecta a máscara. Sem filme virgem visível, o balanço sai pior.
6. **Foco manual na granulação do filme**, não no brilho de fundo.
7. **Escureça o ambiente.** Luz externa bate no filme e cria reflexo.
8. **Use a lente telefoto (3x)** se puder: distorção menor que a principal para
   copiar documentos.

## Modo Pro passo a passo

1. App Câmera → **PRO**
2. **Formato**: ative **RAW** (ou "RAW e JPEG")
3. **Foco**: arraste para **Manual** e ajuste na granulação
4. **Velocidade**: ajuste para a máscara laranja ficar clara, sem estourar
5. **ISO**: o mais baixo que ainda permita a exposição (50–200 no tripé)
6. **Balanço de branco**: deixe automático ou fixe ~5000 K; o pipeline corrige
7. **Temporizador 2 s** ou comando de voz, para não tremer ao tocar

## No PC

```bash
pip install rawpy              # LibRaw, para ler DNG no desktop
python tools/inspecionar_dng.py "C:\...\foto.dng"
python -m neg35.cli amostrar   "C:\...\foto.dng"      # só diagnostica
python -m neg35.cli desenvolver "C:\...\foto.dng" --filme portra400
```

## Se só tiver JPEG

Ainda funciona, pior. Leve em conta:

- Ative o **modo de maior qualidade** do JPEG e desligue filtros/beleza
- O JPEG já vem com balanço de branco, curva de contraste e nitidez aplicados
  **por cima** do negativo — isso quebra a linearidade e suja a inversão
- Espere dominante de cor residual: aumente `--balanco 0.95` e considere
  `--por-canal`
- Não empilhe saturação: o JPEG já saturou

## Outros apps que gravam DNG

Se o Pro mode não bastar: **MotionCam Pro** (RAW verdadeiro, quadro único, foco
manual, muito usado para digitalização) e **Open Camera** (gratuito, suporta
Camera2 RAW). Ambos dão mais controle que o app nativo, ao custo de uma
interface pior.
