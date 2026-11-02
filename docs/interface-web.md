# Interface web

```bash
.venv\Scripts\python.exe tools\app.py
```

Abre em **http://127.0.0.1:8765/**. Se a porta estiver ocupada, ele procura a
próxima livre e mostra o endereço no terminal.

## A tela de configurações abria sozinha — o bug do `hidden`

**Sintoma**: a tela de configurações aparecia sozinha ao abrir, com todos os
campos vazios. O HTML tinha o atributo `hidden` no modal e o JavaScript punha
`hidden = true`. Nada disso importava.

**Causa**: `hidden` só esconde porque o **navegador** aplica
`[hidden] { display: none }` por padrão. Essa regra é do navegador e **perde
para qualquer `display` declarado na folha de estilo do autor**. Como `.modal`
e `.visor` usam `display: flex`, eles ficavam **visíveis** mesmo com o atributo
presente.

```
.modal { position: fixed; ...; display: flex; }   <- vence o [hidden] do navegador
```

Era por isso que o `.toast` funcionava: ele **não** declara `display`, então o
padrão do navegador valia para ele.

**Correção**: uma regra explícita, com `!important`:

```css
[hidden] { display: none !important; }
```

O `!important` é necessário — é a única forma de "escondido" ganhar de qualquer
`display` que alguém venha a declarar depois.

### Por que os testes não pegaram

Os testes verificavam o que estava **escrito**: que o HTML tinha o atributo
`hidden`, que o JS punha `hidden = true`, que o modal só era aberto num lugar.
Tudo isso era verdade — e insuficiente. O que faltava era verificar o
**efeito**: que existisse uma regra de estilo fazendo `hidden` realmente
esconder, já que uma classe nossa declara `display`.

Duas verificações novas:

- a folha de estilo precisa ter `[hidden] { display: none !important }`;
- para cada elemento que nasce com `hidden` **e** cuja classe declara
  `display`, a regra `!important` é obrigatória.

Além disso, o `tools/_teste_abertura.js` **executa o `iniciar()` de verdade**
contra um DOM simulado e confirma que o modal termina escondido. Se o
JavaScript estourar numa exceção na abertura, esse teste acusa — era o outro
caminho possível para o mesmo sintoma.

## Se a tela discordar do `.env`

**Sintoma**: o `.env` diz uma pasta e a tela (ou o erro) mostra outra.

**Causa**: o servidor lê o `.env` **uma vez, ao iniciar**, e guarda em memória.
Ele não recarrega sozinho. Se você editar o `.env` por fora, ou atualizar o
programa, a janela já aberta continua com os valores velhos.

**Solução**: feche a janela do `run.cmd` (**Ctrl+C**, ou feche a janela) e abra
de novo.

Para conferir qual configuração o servidor em execução está usando:

```bash
curl http://127.0.0.1:8765/api/config
```

Comparar esse resultado com o `.env` em disco é a forma mais rápida de
distinguir "configuração errada" de "servidor velho".

### O que o programa faz para evitar essa confusão

1. **Ao iniciar, mostra qual `.env` está usando e quando foi alterado**:
   ```
   config      : C:\Temp\Deepseek\negativo35\.env (alterado 12/10 22:07)
   origem      : E:\Bkp\GoogleDrive\Negativo35mm\RAW
   positivos   : C:\Users\rgg_b\neg35\positivo
   restauradas : C:\Users\rgg_b\neg35\restaurada
   ```
2. **Avisa antes de começar** se alguma pasta não existe ou não aceita escrita.
3. **Serve HTML/CSS/JS sem cache** (`Cache-Control: no-store`). São três
   arquivos pequenos e locais; em troca, o navegador nunca fica com uma versão
   velha da tela depois de uma correção — o que já causou confusão real
   (layout antigo convivendo com código novo).

## Opções

```bash
--porta 8765      porta preferida (procura outra se ocupada)
--host 127.0.0.1  endereço
--env CAMINHO     usa outro .env (padrão: raiz do projeto)
--abrir           abre o navegador sozinho
--sem-auto        não converte automaticamente ao abrir a página
```

## O que a tela faz

Na ordem que você pediu:

1. **Ao abrir, compara** a pasta de origem com a de positivos e a de
   restaurados.
2. **Converte automaticamente** tudo que ainda não tem positivo, com barra de
   progresso mostrando `N de M`, a etapa atual (`adobe`, `invertendo`) e o nome
   do arquivo.
3. Depois, mostra **só os que ainda não foram restaurados**, em grade com
   miniatura.
4. **Clicar na miniatura abre a imagem grande**, com zoom (`+`, `-`, `100%`)
5. **Caixa de seleção** por foto; botões "Marcar todos" e "Desmarcar"
6. Mostra o **custo estimado** das selecionadas antes de gastar
7. Botão **"Restaurar selecionadas"** chama a IA só nas marcadas
8. Engrenagem abre as **configurações** (pastas, saturação, curva, Adobe), que
   são gravadas no `.env`

### A tela de configurações

**Ela só abre se você clicar na engrenagem.** O modal nasce `hidden` no HTML e
o `iniciar()` reforça isso antes de ligar qualquer evento — para nunca aparecer
sozinha na abertura.

**Todos os campos vêm preenchidos com o valor recomendado**, e o rótulo mostra
qual é esse valor:

```
Saturação  [recomendado: 1.15]   1.15
Nitidez    [recomendado: 0.4]    0.4
```

Se você mudar algo, a etiqueta fica em **destaque (âmbar)** para você perceber
que saiu do padrão. O botão **"Restaurar recomendados"** devolve todos os
valores, e há um botão **Salvar** que grava no `.env`.

Os valores recomendados vêm do **servidor** (`servidor.RECOMENDADOS`), não de
uma cópia no JavaScript — assim não há como a tela e o programa divergirem.

## Os campos, um por um

| Campo | Recomendado | O que faz |
|---|---|---|
| **Pastas** (3) | as do `.env` | origem, positivos locais, restauradas |
| **Filme** | Genérico | lista com os 10 presets do código. "Genérico" funciona bem; escolher o filme certo ajuda na cor |
| **Saturação** | 1,15 | 1 = neutro; acima de 1,4 deixa a pele alaranjada |
| **Nitidez** | 0,40 | 0 = desligado; muito alto realça o grão do filme |
| **Balanço de branco** | 0,90 | 0 = não corrige; 1 = corrige tudo (pode apagar o tom de época) |
| **Curva: alvo** | 0,50 | mediana de luminância desejada. Menor escurece, maior clareia |
| **Curva: gama fixo** | 0 | 0 = calcula por foto (recomendado) |
| **Lado máx. de envio** | 1536 | mandar maior **não melhora**; o modelo reduz internamente |
| **Usar curva de tom** | **marcado** | desmarcado, o positivo sai lavado |
| **Usar Adobe DNG Converter** | **marcado** | conserta os DNG que o decodificador normal recusa |

Resumindo: **não precisa colar nada.** Os campos já vêm certos; só clique em
Salvar, ou feche com Cancelar.

### Comparação lado a lado

Nas fotos restauradas há duas formas de comparar positivo × restaurado:

- no **visor de zoom**, o botão **"Comparar com a restaurada"** (aparece só
  quando existe restaurada);
- um **atalho `⇄`** no canto da célula das já prontas.

Para as restauradas aparecerem na grade, marque **"Mostrar também as já
restauradas"**.

A comparação é montada **no servidor**, com letterbox para as duas metades
ficarem na mesma escala. Detalhes e medições em
[docs/comparacao-lado-a-lado.md](comparacao-lado-a-lado.md).

## Sem dependências novas

Não usa FastAPI nem Flask — de propósito. Neste ambiente o `pip` trava (proxy
corporativo e `%TEMP%` bloqueado), então o servidor usa `http.server` da
biblioteca padrão e o front é HTML/CSS/JS puro, sem framework e sem CDN.

## Arquitetura

```
tools/app.py         servidor HTTP: rotas, mídia, miniatura, threads
neg35/servidor.py    lógica pura: estado, converter(), restaurar(), thumb()
web/index.html       a tela
web/estilo.css       tema escuro (pensado para julgar imagem)
web/app.js           polling de progresso, grade, zoom, seleção
```

A separação importa: `neg35/servidor.py` não abre porta nenhuma, então dá para
testar tudo sem servidor.

### Rotas

| Método | Rota | O que faz |
|---|---|---|
| GET | `/` | a página |
| GET | `/api/estado` | varredura completa: contagens, itens, filas |
| GET | `/api/config` | configuração atual |
| GET | `/api/progresso` | estado do trabalho em andamento (a tela consulta a cada 700 ms) |
| GET | `/api/custo?nomes=a,b` | custo estimado das selecionadas |
| GET | `/midia/positivo/<nome>?thumb=1` | miniatura; sem `thumb`, a imagem cheia |
| GET | `/midia/restaurado/<nome>` | idem para as restauradas |
| GET | `/midia/comparar/<nome>?w=1500` | positivo e restaurado lado a lado, em letterbox |
| POST | `/api/converter` | inicia a conversão dos pendentes |
| POST | `/api/restaurar` | inicia a restauração das selecionadas |
| POST | `/api/parar` | cancela o trabalho em andamento |
| POST | `/api/salvar-config` | grava as configurações no `.env` |

**Miniatura sob demanda**: gerada com Pillow e reduzida para 340 px. Medido:
55 KB contra 7 MB da imagem cheia, então a grade carrega rápido mesmo com
dezenas de fotos.

**Um trabalho por vez**: conversão e restauração não rodam juntas. É uma
ferramenta pessoal, e dois trabalhos simultâneos só confundiriam o progresso.
Se você recarregar a página com um trabalho em andamento, a tela **retoma o
acompanhamento** em vez de começar outro.

## Testes

```bash
.venv\Scripts\python.exe tools\_teste_app.py   # lógica + rotas HTTP reais
.venv\Scripts\python.exe tools\_teste_web.py   # HTML <-> JS <-> CSS
```

O `_teste_app.py` sobe o servidor numa porta livre temporária e exercita as
rotas de verdade: página, CSS, JS, estado, progresso, custo, miniatura, imagem
cheia, recusa de seleção vazia (400) e rota inexistente (404).

O `_teste_web.py` cobre o que mais quebra em runtime sem navegador: verifica
que **todo id que o JS busca existe no HTML**, que as rotas chamadas pelo front
existem no servidor, e que as classes que o JS aplica têm estilo no CSS.

### Limitação conhecida dos testes

Não há teste visual automatizado. Tentei Chrome/Edge em modo headless e o
sandbox bloqueia (os navegadores usam named pipes, que a política nega). O
layout foi validado por revisão do código, não por screenshot.

Se algo na tela não funcionar, abra o console do navegador (F12): o `app.js`
registra em `console.warn` a lista de falhas quando alguma conversão ou
restauração não dá certo.
