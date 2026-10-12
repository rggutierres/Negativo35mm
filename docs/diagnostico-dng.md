# Por que os DNG do S22 Ultra não decodificam

Investigação completa, com medições. Resumo: **não é o modo de captura**, ao
contrário do que a primeira análise sugeriu.

## Resultado do teste Pro vs Expert RAW

Você fotografou a mesma cena nos dois modos. Os dois falharam, por motivos
**diferentes**:

| Arquivo | Dimensão | Compressão | Bits | LibRaw | ImageMagick |
|---|---|---|---|---|---|
| `Pro_20261012_141119.dng` | 4000×1868 | `7` | 12 | ❌ Data error | decodifica |
| `Expert_20261012_141057.dng` | 4000×3000 | `52546` | 16 | ❌ Unsupported | ❌ recusa |
| `20261012_110646.dng` (funciona) | 4000×1868 | `7` | 12 | ✅ OK | OK |

## Duas causas distintas, não uma

### Causa A — compressão `52546` (arquivos do Expert RAW em 4:3)

O Expert RAW grava em dois sabores:

- **4000×3000, 16 bits, compressão `52546`** → formato proprietário. Nem LibRaw
  nem ImageMagick decodificam. Nada a fazer no código.
- **4000×1868, 12 bits, compressão `7`** → JPEG lossy padrão, que o LibRaw sabe
  ler.

O que decide entre os dois parece ser configuração de captura do Expert RAW
(resolução/proporção), não o modo por si.

### Causa B — um bloco JPEG corrompido (arquivos em 4000×1868)

Aqui está o achado que muda tudo. Nos arquivos de 4000×1868 que falham, o LibRaw
reclama de **exatamente um bloco corrompido**, em offset diferente por arquivo:

```
Pro_20261012_141119.dng    bloco corrompido em 1631779
20261012_133515.dng        bloco corrompido em 2381991
20261012_133734.dng        bloco corrompido em 1131784
20261012_133746.dng        bloco corrompido em 1000262
...
20261012_110646.dng        NENHUM bloco corrompido   <-- o único que decodifica
```

**Um bloco ruim é suficiente para o LibRaw abortar o arquivo inteiro.** Ele não
degrada: ele desiste. O ImageMagick usa a mesma LibRaw mas tolera o bloco e
entrega a imagem com um remendo.

### A leitura é estável — logo a corrupção veio no upload

Li cada arquivo 3 vezes: MD5 idêntico e mmesmos offsets nas três leituras. Isso
descarta o Google Drive em modo streaming devolvendo blocos incompletos.

Então a corrupção está **dentro do arquivo que chegou ao Drive** — ou já saiu
assim da câmera, ou se perdeu na transferência celular → Drive.

Evidência circunstancial de que é transferência: o `110646`, que funciona, veio
dentro de um **ZIP** (`drive-download-...zip`), e os corrompidos vieram
soltos. Mas eu não tenho o ZIP dos novos para provar.

## O fallback do ImageMagick não salva

Medido nos arquivos que ele consegue decodificar:

| Fonte | Máscara (R/B) | Positivo (p05 / p50 / saturação) |
|---|---|---|
| `110646` (LibRaw) | **4,32** | 0,544 / 0,787 / 0,082 |
| `Pro_141119` (ImageMagick) | 1,76 | 0,794 / 0,960 / 0,037 |

O ImageMagick aplica o balanço de branco da câmera, o que **neutraliza a máscara
laranja**. O positivo saiu praticamente branco — inutilizável. E testado antes:
mandar esse positivo para a IA devolve imagem borrada e esverdeada.

## Teste que resolve a dúvida (precisa de você)

**Zipe no celular e baixe pelo navegador.** Depois rode:

```bash
.venv\Scripts\python.exe tools\comparar_modos.py "pasta"
```

- Se os arquivos do ZIP **decodificarem** → era corrupção de transferência.
  Solução: transferir sempre por ZIP.
- Se continuarem falhando nos mesmos offsets → a corrupção sai da câmera, ou o
  Google Drive corrompe no upload. Aí a solução é o Adobe DNG Converter.

## Alternativas, em ordem de preferência

1. **Transferir por ZIP** (gratuito, resolve se for transferência).
2. **Adobe DNG Converter** — converte para DNG padrão que o LibRaw lê. Também
   conserta os arquivos de compressão `52546`. Não pude testar (não instalado).
3. **Fotografar e developar no celular**: o Samsung Gallery/Expert RAW consegue
   gerar o JPEG revelado. Se você exportar esse JPEG, o pipeline processa — com
   a máscara neutralizada (como qualquer JPEG), mas pelo menos com a imagem
   correta e sem corrupção.
4. **Copiar por cabo/SD** em vez de pela nuvem, e testar se decodifica.

## Ferramenta de diagnóstico

```bash
.venv\Scripts\python.exe tools\comparar_modos.py [pasta]
```

Mostra, por arquivo: se o LibRaw decodifica de verdade, dimensão, compressão,
bits, e a máscara laranja resultante. É o teste que separa "arquivo bom" de
"arquivo que só parece bom".
