# Comparação mostrando imagem velha depois de refazer

## O sintoma

O usuário apagou uma restaurada que estava recortada, processou de novo, mas a
aba Comparar continuou mostrando a versão recortada.

## A causa: cache do navegador

O arquivo no disco estava **correto**:

```
20261012_214922_restaurado.png   1472x704   criado 23/10 18:24
```

E a comparação gerada pelo servidor **na hora** também estava correta. O que
estava errado era o que o navegador mostrava.

O motivo estava no `_bytes()` do servidor:

```python
def _bytes(self, dados, tipo, cache: bool = True)   # -> max-age=3600
```

As rotas de `/midia/` usavam o padrão, ou seja **1 hora de cache**. A URL da
comparação é:

```
/midia/comparar/<nome>?w=2200&s=<compVersao>
```

O `s` só mudava em ações da própria tela (refazer, girar, recortar). Quando a
foto era refeita pelo fluxo normal e a página recarregada, `compVersao` voltava a
0 e a URL era **idêntica** à anterior — então o navegador servia o PNG velho do
cache por até 1 hora.

## A correção, em duas camadas

**1. `no-store` nas rotas de mídia.** Tudo o que reflete um arquivo que pode
mudar passa a ir sem cache:

| rota | por quê |
|---|---|
| `/midia/comparar/...` | depende de dois arquivos que mudam |
| `/midia/<tipo>/?thumb=1` | miniatura da grade |
| `/midia/<tipo>/` (cheia) | imagem do visor |
| `/imagem/<tipo>/...` | imagem reduzida do visor |

**2. Renovação da versão no JavaScript.** `compVersao` agora é incrementado:

- ao **abrir** a aba Comparar;
- quando um **trabalho termina** (restauração, recorte, rotação).

Assim a URL muda quando o conteúdo pode ter mudado, sem depender de o usuário
acertar o momento do recarregamento.

## Problema sério encontrado no caminho

Os testes `_teste_rotacao_arq.py` e `_teste_recorte_arq.py` operavam **no arquivo
real do usuário**: giravam/recortavam a restaurada de verdade e depois tentavam
"restaurar do backup mais recente". Esse palpite é frágil — com várias cópias, o
"mais recente" pode ser o girado — e foi o que aconteceu: a
`20261012_214720_restaurado.png` ficou em 704x1472 (girada).

**Reescritos** para trabalhar numa **cópia em pasta temporária**, e agora cada um
termina conferindo que o arquivo real não foi tocado:

```
ok  o arquivo real do usuário não foi tocado
```

A `214720` foi corrigida de volta para 1472x704 (conferida visualmente: crianças
de pé).

## Verificação

```
/midia/comparar/...      no-store
/midia/positivo?thumb=1  no-store
/imagem/restaurado?...   no-store
comparação gerada agora: 1400x329, as duas metades completas
19 verificações passando
```

## O que o usuário precisa fazer

**Ctrl+F5 uma vez.** O navegador ainda tem a imagem velha guardada da regra
antiga; depois desse recarregamento a página passa a sempre buscar do servidor.
