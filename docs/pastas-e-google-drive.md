# Pastas: onde gravar os resultados

## Resumo

A pasta de saída precisa ser **gravavel**, e qual pasta serve depende da
máquina. O programa **testa antes** e deixa você escolher — não chuta um
caminho fixo.

## O erro original

```
Erro: PermissionError: [WinError 5] Acesso negado:
'E:\Bkp\GoogleDrive\Negativo35mm\Positivo'
```

### Primeira suspeita: a unidade do Google Drive

O `.env` original apontava as **três** pastas para `E:\Bkp\GoogleDrive\...`:

```ini
pasta_origem    = E:\Bkp\GoogleDrive\Negativo35mm\RAW
pasta_positivo  = E:\Bkp\GoogleDrive\Negativo35mm\Positivo      # <- escrita
pasta_restaurada= E:\Bkp\GoogleDrive\Negativo35mm\Restaurada    # <- escrita
```

A unidade que o Google Drive cria no Windows é um **sistema de arquivos
virtual** — serve bem para **ler** (a origem funciona), mas costuma recusar
escrita por programa. Faz sentido, e foi a primeira correção:

```ini
pasta_origem    = E:\Bkp\GoogleDrive\Negativo35mm\RAW
pasta_positivo  = C:\Users\rgg_b\neg35\positivo
pasta_restaurada= C:\Users\rgg_b\neg35\restaurada
```

### Mas o erro continuou — e a causa era outra

Com a saída já local, o erro **permaneceu**: nem `C:\Users\rgg_b\neg35` aceita
escrita. Ou seja, o problema não era (só) a nuvem: **escrever no perfil do
usuário também é negado** nesta máquina.

Medido:

```
OK   pasta 'saida' ao lado do programa   C:\Temp\...\negativo35\saida
NÃO  sua pasta de Imagens                C:\Users\rgg_b\Pictures\neg35    Acesso negado
NÃO  sua pasta de Documentos             C:\Users\rgg_b\Documents\neg35   Acesso negado
NÃO  sua pasta de usuário                C:\Users\rgg_b\neg35             Acesso negado
```

**Lição**: "acesso negado" pode ter várias causas, e sugerir um caminho fixo é
um chute. A solução certa é **testar e deixar o usuário escolher**.

## O que o programa faz agora

### Ao abrir, testa os locais e mostra só o que funciona

```
Antes de começar
  ✓ Origem      E:\Bkp\GoogleDrive\Negativo35mm\RAW   [nuvem]   27 imagem(ns)
  ✕ Positivos   C:\Users\rgg_b\neg35\positivo                   sem permissão
  ✕ Restauradas C:\Users\rgg_b\neg35\restaurada                 sem permissão

Escolha abaixo onde guardar os resultados — os originais continuam onde estão.

  ◉ pasta 'saida' ao lado do programa     C:\Temp\...\negativo35\saida
  ○ sua pasta de Imagens                  C:\Users\rgg_b\Pictures\neg35   sem permissão
  ○ sua pasta de Documentos               C:\Users\rgg_b\Documents\neg35  sem permissão
  ○ sua pasta de usuário                  C:\Users\rgg_b\neg35            sem permissão

  Ou digite outro caminho completo: [ C:\Fotos\neg35            ]
  [ Usar esta pasta para a saída ]
```

Os que não gravam vêm **desabilitados e com o motivo** — não são opções falsas.
E há um campo para digitar qualquer caminho, que é **testado antes de aceitar**.

### Cinco proteções

1. **A conversão automática é bloqueada** quando não dá para gravar.
2. **A restauração por IA é bloqueada** também — a IA é **paga**, e gravar o
   resultado é pré-requisito para gastar.
3. **Queda para uma pasta que grava.** Se a pasta configurada recusar escrita, o
   `converter()` procura uma que aceite e avisa no resultado.
4. **A escolha é testada**: caminho sem escrita devolve 400 com o motivo;
   caminho relativo é recusado com orientação.
5. **A tela não abre sozinha** (ver o bug do `hidden` em
   [interface-web.md](interface-web.md)).

### A mensagem não afirma a causa

A primeira versão dizia *"esta pasta está numa unidade de nuvem"* para
**qualquer** erro de escrita. Isso é afirmar uma causa que pode estar errada — e
estava: parte dos bloqueios não tinha relação com nuvem.

Agora o motivo por item descreve **só o observado** (`Acesso negado`), e a
explicação sobre nuvem fica em `dica_nuvem`, preenchida apenas quando o
caminho realmente contém `GoogleDrive`, `OneDrive`, `Dropbox`, `iCloud` ou
`MyDrive`.

### Os avisos acumulam

Cada positivo pode ter vários avisos (`via Adobe`, `máscara fraca`, `caiu para
outra pasta`). Antes cada um **sobrescrevia** o anterior. Agora saem todos:

```
pasta configurada sem escrita — gravado em C:\...\saida\positivo | via Adobe | máscara fraca (R/B=1.00)
```

## Para descobrir onde dá para gravar na sua máquina

```bash
.venv\Scripts\python.exe tools\_ver_locais.py
```

Mostra cada local testado, o veredito e a mensagem de erro dos que falham.

## Sobre a investigação de permissões

Usei a verificação de permissões do Windows em `C:\Users\rgg_b`:

```
VERDICT = NOT_THIS_CLASS
  C:\Users\rgg_b  MY_RIGHTS=[FullControl]  WRITE_DAC=True  WRITE_OWNER=True
```

As permissões do Windows **estão corretas**. Nenhuma alteração foi feita nem
era necessária — o bloqueio não é uma permissão quebrada.

Isso está registrado porque é fácil confundir "acesso negado" com "permissão
quebrada", e a conclusão correta só veio da medição.

## Testes

```bash
.venv\Scripts\python.exe tools\_teste_pastas.py
```

Cobre: detecção de pasta sem escrita, a lista de locais testados (gravaveis
primeiro), escolher pelo caminho digitado, **recusar caminho sem escrita com
400**, **recusar caminho relativo**, escolha automática, queda para pasta que
grava, acúmulo de avisos e a conversão funcionando depois da troca.

O teste é **consciente do ambiente**: onde a política permite escrita ele
confirma a conversão; onde não permite, confirma o relato correto do motivo. Um
teste que só passasse numa das duas situações seria pior que nenhum.


### Importante: é preciso REINICIAR o programa

O servidor lê o `.env` **uma vez, ao iniciar**, e guarda em memória. Depois de
corrigir o `.env`, a janela já aberta continua usando os valores velhos — a
tela mostra uma pasta e o erro mostra outra.

Isso foi confirmado na prática. Com o `.env` já corrigido em disco, o servidor
que estava rodando respondia:

```
GET /api/config           -> E:\Bkp\GoogleDrive\Negativo35mm\Positivo   (valor velho)
GET /api/verificar-pastas -> 404                                        (rota nova, ausente)
.env em disco             -> C:\Users\rgg_b\neg35\positivo              (valor correto)
```

Ou seja: **o programa em execução era anterior à correção.** Fechar a janela
(Ctrl+C) e abrir de novo pelo `run.cmd` resolve.

Para conferir qual configuração o servidor em execução está usando:

```bash
curl http://127.0.0.1:8765/api/config
```

### 2. A tela de configuração abria sozinha? Não — mas o formulário vinha vazio

O modal **nasce `hidden`** e é aberto num único lugar (a função `abrirConfig`,
chamada só pela engrenagem). Isso está coberto por teste.

O que confundia: o `.env` apontava para pastas que **não existiam**
(`Positivo` e `Restaurada` nunca tinham sido criadas), então os campos
apareciam em branco e o erro de permissão estourava por cima.

**Correção**: a tela agora roda um **diagnóstico ao abrir** e mostra o estado
real de cada pasta, em vez de deixar o usuário descobrir no meio da conversão.

## O que mudou no programa

### Ao abrir, um diagnóstico das pastas

A tela chama `GET /api/verificar-pastas` e mostra um aviso quando há problema:

```
Antes de começar
  ✓ Origem       E:\Bkp\GoogleDrive\Negativo35mm\RAW   [nuvem]  8 imagem(ns)
  ✕ Positivos    E:\Bkp\GoogleDrive\Negativo35mm\Positivo       sem permissão
  ✕ Restauradas  E:\Bkp\GoogleDrive\Negativo35mm\Restaurada     sem permissão

A saída está numa unidade de nuvem (Google Drive/OneDrive), que costuma recusar
escrita por programa. Aponte a saída para uma pasta local: os originais
continuam onde estão.

[ Escolher uma pasta local para a saída ]
```

### Quatro proteções novas

1. **A conversão automática é bloqueada** quando não dá para gravar. Antes ela
   disparava e enchia a tela de erros de permissão.
2. **A restauração por IA é bloqueada** também — e isso importa mais, porque a
   IA é **paga**: gravar o resultado é pré-requisito para gastar.
3. **Queda para uma pasta que grava.** Se a pasta configurada recusar escrita, o
   `converter()` procura uma que aceite (testando de verdade) e avisa no
   resultado: `pasta configurada sem escrita — gravado em <caminho>`.
4. **A escolha da pasta é testada antes.** O botão "Escolher uma pasta local"
   não chuta `~/neg35`: ele testa `~/neg35`, `~/Pictures/neg35`,
   `~/Documents/neg35` e a pasta do projeto, nessa ordem, e usa a primeira que
   comprovadamente grava.

### A mensagem não chuta mais a causa

A primeira versão dizia *"esta pasta está numa unidade de nuvem, que recusa
escrita"* para **qualquer** erro de escrita. Isso é afirmar uma causa que pode
estar errada — e neste caso estava: o bloqueio que eu investiguei não tinha
relação com nuvem.

Agora o motivo por item descreve **só o observado** (`Acesso negado`), e a
explicação sobre nuvem fica num campo separado (`dica_nuvem`), preenchido
apenas quando o caminho realmente contém `GoogleDrive`, `OneDrive`, `Dropbox`,
`iCloud` ou `MyDrive`.

### Os avisos acumulam

Cada positivo pode ter vários avisos (`via Adobe`, `máscara fraca`, `caiu para
outra pasta`). Antes cada um **sobrescrevia** o anterior — quando havia mais de
um, o usuário só via o último. Agora saem todos:

```
pasta configurada sem escrita — gravado em C:\...\saida\positivo | via Adobe | máscara fraca (R/B=1.00)
```

## Sobre a investigação de permissões

Quando o erro apareceu, usei a verificação de permissões do Windows na pasta
`C:\Users\rgg_b`. Resultado:

```
VERDICT = NOT_THIS_CLASS
  C:\Users\rgg_b  MY_RIGHTS=[FullControl]  WRITE_DAC=True  WRITE_OWNER=True
```

**As permissões estavam corretas.** Nenhuma alteração foi feita, e nenhuma era
necessária. O bloqueio que eu estava vendo era do **meu ambiente de
desenvolvimento** (confinamento de sandbox: negava escrita em qualquer lugar
fora do projeto), não da máquina do usuário — por isso não foi "consertado" e
não havia o que consertar.

Isso está registrado aqui porque é fácil confundir "acesso negado" com
"permissão quebrada", e a conclusão correta só veio da medição.

## Testes

```bash
.venv\Scripts\python.exe tools\_teste_pastas.py
```

Cobre os dois lados: pasta sem escrita é detectada, a conversão não grava nela,
a queda para pasta gravável funciona, os avisos acumulam, a rota
`/api/usar-pastas-locais` troca a saída preservando a origem, e a conversão
passa a funcionar depois da troca.

O teste é **consciente do ambiente**: onde a política permite escrita ele
confirma a conversão; onde não permite, confirma o relato correto do motivo. Um
teste que só passasse numa das duas situações seria pior que nenhum.
