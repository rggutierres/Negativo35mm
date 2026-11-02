# Onde fica a pasta `_adobe_convertido`

## Resposta curta

Ela **não estava no `.env`** porque não era configurável: o caminho era
**derivado da pasta de positivos**, como pasta irmã.

```
pasta_positivo = C:\Temp\Deepseek\negativo35\saida\positivo
                                              ^^^^^^
cache          = C:\Temp\Deepseek\negativo35\saida\_adobe_convertido
```

E a regra estava escrita **em três lugares diferentes** do código:

```
neg35/servidor.py:334   (na medida da máscara)
neg35/servidor.py:462   (na conversão)
tools/lote.py:561       (na linha de comando)
```

Três cópias da mesma regra é convite para divergirem. Agora existe **uma só**
(`config.pasta_cache_adobe`).

## Por que o cache existe

O Adobe DNG Converter regrava **sem compressão**. O original do celular tem
~14 MB; o reconvertido fica com **~43 MB** — três vezes maior.

Medido na sua pasta: **26 arquivos, 1.117 MB (1,1 GB)**.

Ele existe porque a conversão do Adobe leva alguns segundos por arquivo, e o
resultado é reusado nas próximas execuções.

**Importante**: o cache **não é necessário** para a correção em si. O positivo
gerado já tem tudo. Apagar a pasta é seguro — só custa tempo na próxima
conversão.

## O que mudou

### 1. Local configurável

Nova chave no `.env`, e um campo na engrenagem:

```ini
pasta_cache_adobe=      # vazio = pasta temporária do sistema
```

### 2. O padrão passou a ser a pasta temporária

Antes, o cache ficava ao lado dos positivos — que pode ser uma pasta sincronizada
(Google Drive, OneDrive) ou um destino que você escolheu por outro motivo.
Dado descartável de 1,1 GB não pertence ali.

Agora o padrão é a pasta temporária do sistema, que é o lugar próprio para isso.

### 3. O cache antigo é REUSADO, não descartado

Se já existir `_adobe_convertido` na pasta irmã dos positivos **com arquivos**,
o programa continua usando esse endereço. Recriar 26 arquivos custa minutos, e
jogar 1,1 GB fora para recomeçar seria desperdício.

Ou seja: **nada foi apagado.** Você decide quando limpar.

### 4. Se não houver onde gravar, o Adobe é desativado com aviso

Se nenhuma pasta de cache aceitar escrita, o programa avisa e segue sem o
Adobe (menos robusto para DNG defeituoso) em vez de estourar erro.

## Uma armadilha no caminho: o campo não aparecia no `.env`

Ao acrescentar `pasta_cache_adobe`, o campo passou a existir na classe `Config`
e apareceu na tela — mas **não foi gravado no `.env`**.

**Causa**: o `salvar()` monta o arquivo a partir de um **modelo fixo de
linhas**. Acrescentar um campo à classe não o acrescenta ao modelo. O campo
existe, a tela mostra, e o arquivo não tem — e a alteração do usuário se perde
na próxima gravação.

O mesmo aconteceu com `converter_auto`, criado na mesma leva.

**Correção**: os dois entraram no modelo, com comentário explicativo. E criei
`tools/_teste_env_completo.py`, que compara **todos** os campos da classe
`Config` com as chaves efetivamente escritas no arquivo. Se alguém acrescentar
um campo e esquecer o modelo, o teste acusa:

```
campos em Config : 23
chaves no .env   : 23
ok  todo campo do Config é gravado no .env
```

O `.env` do projeto foi regravado (com backup em `.env.bak`), preservando todos
os valores — pastas, chave de API e o prompt de 1300 caracteres.

## Como limpar o cache, se quiser

```powershell
Remove-Item -Recurse "C:\Temp\Deepseek\negativo35\saida\_adobe_convertido"
```

Ou aponte `pasta_cache_adobe` para outro lugar pela engrenagem. O programa
recria o que precisar na próxima conversão.

## Para conferir onde está

```bash
.venv\Scripts\python.exe tools\_ver_cache_adobe.py
```

Mostra o caminho resolvido, quantos arquivos tem, quanto ocupam e se o
Adobe está instalado.
