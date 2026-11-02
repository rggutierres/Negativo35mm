# Aba "Falhas na conversão"

## O que é

Uma aba nova mostra os negativos que **não geraram positivo**. Antes o resumo
dizia "1 falha de 26" e não havia como saber qual foto nem por quê.

## A falha real encontrada (26 → 25 positivos)

`Expert_20261012_141057.dng` — 14,4 MB, cabeçalho TIFF válido, mas:

```
LibRawFileUnsupportedError: Unsupported file format or not RAW file
ImageMagick: magick: Unsupported file format or not RAW file
```

Medições que descartam arquivo truncado ou incompleto na nuvem:

| verificação | resultado |
|---|---|
| cabeçalho TIFF | válido (`II` 2A 00, magic 42, IFD em 8) |
| tamanho | 15.057.109 bytes (comparável ao que funciona: 15.438.108) |
| rawpy `sizes` | leu 4000x3000 |
| `postprocess` / leitura | falha nos dois decodificadores |

O nome `Expert_` indica **Samsung Expert RAW**, e o tamanho 4000x3000 (4:3) é
diferente das outras (4000x1868). É um DNG de outro modo de captura, em formato
que o libraw desta versão não abre.

**Não é problema do programa.** A foto precisa ser reexportada (DNG→DNG padrão)
ou convertida no app da Samsung antes de entrar na pasta.

## Como funciona

Duas fontes, porque uma sem a outra esconde casos:

1. **Registro persistido** (`saida/_falhas_conversao.json`): gravado quando uma
   conversão falha, com motivo, arquivo, tamanho e data. Some quando a foto
   converte com sucesso depois.
2. **Varredura ao vivo**: negativos na pasta de origem sem positivo. Pega as
   falhas anteriores ao registro existir e conversões interrompidas.

As que vêm só da varredura aparecem como **"motivo não registrado"** — o
programa não inventa uma explicação que não mediu.

## Na tela

- Contador na própria aba, para o problema aparecer sem abrir;
- Nome, arquivo e tamanho de cada negativo;
- **Diagnosticar**: abre o arquivo e registra o motivo real (sob demanda, porque
  abrir um DNG leva segundos);
- **Diagnosticar todas**: uma por vez;
- **Copiar lista**: nome + arquivo + motivo, para colar num relatório.

## Um detalhe que já mordeu antes

`/api/falhas` é **GET**, mas na primeira versão eu a coloquei no `do_POST` e a
tela recebia 404. É o mesmo erro que aconteceu com `/api/abrir-pasta`. O teste
`_teste_web` agora confere que toda rota usada pelo JS existe no servidor.

## Verificação

```
GET /api/falhas → total: 1 (Expert_20261012_141057)
HTML → aba, painel, lista, botões: OK
CSS  → .aba-conta, .falha-motivo: OK
JS   → carregarFalhas, /api/diagnosticar-falha: OK
recursos do servidor: 14 (inclui aba_de_falhas)
15 verificações, todas passando
```

## Um achado maior, que NÃO é desta tarefa

Ao testar o recorte eu vi que **o positivo salvo está rotacionado 90°**: no
arquivo `20261012_133746_positivo.png` (1868x4000) as pessoas aparecem
deitadas, e os furinhos do filme ficam nas **laterais**.

Isso explica por que o recorte é tão difícil: a orientação "visual" e a do
arquivo diferem, e as minhas contas de proporção (largura/altura) invertem.

Medido ao longo do caminho: com `recortar_bordas` e a instrução nova no prompt
ligadas, a IA passou a devolver a foto **deitada errada**. Por isso **desliguei
as duas** no `.env`:

```
recortar_bordas=false
limpar_borda_no_prompt=false
```

Volta ao comportamento que você aprovou, e a aba de falhas não depende disso.

**Próximo passo recomendado:** corrigir a orientação na conversão (ou aplicar
rotação por EXIF), e só depois retomar o recorte — com a orientação certa, a
proporção do quadro é 1,455 e a detecção já acerta.
