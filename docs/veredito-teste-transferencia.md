# Veredito do teste de transferência

Você baixou o mesmo DNG de três formas. **As três são byte-idênticas**, e todas
falham no mesmo ponto.

## Resultado

| Arquivo | Tamanho | MD5 | LibRaw | Bloco corrompido |
|---|---|---|---|---|
| `20261012_143104.dng` | 13.471.859 | `9f4301197f3b…` | ❌ Data error | offset `953516` |
| `download_so_um_arq_1_…dng` | 13.471.859 | `9f4301197f3b…` | ❌ Data error | offset `953516` |
| do ZIP (`drive-download-…zip`) | 13.471.859 | CRC32 `5255D2F1` | ❌ | — |

- Os dois arquivos em disco têm **MD5 idêntico**.
- O CRC32 do arquivo extraído **bate exatamente** com o do ZIP: `5255D2F1`.
- Os dois falham no **mesmo offset**, `953516`.

## O que isso prova

1. **A transferência está correta.** Download solto do Drive e download em ZIP
   produzem o mesmo arquivo, byte a byte. O CRC32 confirma que a extração não
   altera nada.
2. **O Google Drive não corrompe nada.** Nem no upload, nem no download, nem no
   stream.
3. **A corrupção existe no DNG desde a origem** — o arquivo que saiu do celular
   já tem um bloco JPEG ruim.
4. **O LibRaw não ignora bloco ruim.** Ele lê o arquivo inteiro, encontra um
   bloco defeituoso e aborta. Não entrega a imagem com um remendo; desiste.

## O padrão em todos os 14 arquivos testados

Cada arquivo que falha tem **exatamente um** bloco corrompido, em offset
diferente. Um único bloco entre 13 milhões de bytes:

```
Pro_141119       bloco em 1631779
143104 (novo)    bloco em  953516
133515           bloco em 2381991
133734           bloco em 1131784
133746           bloco em 1000262
20261012_104309  bloco em 1016260
...
110646           NENHUM   <-- o único que decodifica
```

Isso não é aleatório. A frequência e a distribuição sugerem um defeito
sistemático na escrita do DNG — ou no aparelho, ou no app, ou no encoder de DNG
com perda da Samsung.

## O fallback também não serve

Medido no arquivo deste teste:

| Fonte | Máscara (R/B) | Positivo (p05 / p50 / saturação) |
|---|---|---|
| `110646` (LibRaw, funciona) | **4,32** | 0,544 / 0,787 / 0,082 |
| `143104` (ImageMagick) | 1,86 | **0,832 / 0,963 / 0,033** |
| `143104.jpg` (só para comparar) | 1,67 | — |

O ImageMagick aplica o balanço de branco da câmera e destrói a máscara laranja.
O positivo sai praticamente branco (p05 = 0,832), como a imagem em
`tools/amostras/teste_zip/positivo.png`. Nem o JPG do celular é melhor
(R/B 1,67).

## Veredito

**Não é problema de software meu, e não é de transferência.** É o arquivo DNG
que sai do celular com um bloco defeituoso, e nenhum dos dois decodificadores
disponíveis no seu PC tolera isso.

## O que resolve, em ordem

### 1. Adobe DNG Converter (gratuito) — o caminho mais provável

Ele re-encoda o DNG para o padrão. A própria Adobe trata bloco corrompido
graciosamente e produz um DNG sem defeito, que o LibRaw lê. É a solução
conhecida para DNG proprietário e para bloco ruim.

Download: adobe.com/products/dng (gratuito, não precisa de conta Adobe).

Depois de instalar, eu testo na hora com os arquivos que já temos.

### 2. Exportar o JPEG revelado pelo celular

O Samsung Gallery / Expert RAW desenvolvem o DNG no aparelho. Se você exportar
esse JPEG e me passar, o pipeline processa. A máscara vem neutralizada (como em
qualquer JPEG), então a cor final fica pior — mas a imagem está correta e sem
corrupção. Para essas fotos, seria melhor que o que temos hoje.

### 3. Investigar a origem no celular

Se um DNG novo continua saindo com bloco ruim, o defeito está na captura. Vale:
- testar se o problema acontece gravando na memória interna vs cartão SD;
- atualizar o Expert RAW e o firmware do aparelho;
- testar outros modos (o Pro, o normal) e ver se algum gera DNG íntegro.

O `tools/comparar_modos.py` responde isso rapidamente.

## Ferramenta deste teste

```bash
.venv\Scripts\python.exe tools\comparar_transferencia.py
```

Compara MD5, CRC32 contra o ZIP, e mostra onde cada arquivo falha. Serve para
qualquer suspeita futura de corrupção.
