# "Deu o mesmo erro de novo": o servidor estava velho

## O sintoma

Depois de corrigir a medida da máscara, o usuário selecionou 4 fotos e recebeu
**de novo** "0 restauradas, 4 puladas".

O detalhe que denunciou tudo: a mensagem dizia **`R/B=1.00`**.

Esse valor é a assinatura do **código antigo**. O código corrigido mede no DNG
e devolve 1,5 a 3,3 — nunca 1,00 exato. Se apareceu 1,00, o processo em
execução era anterior à correção.

Confirmado: a correção **estava** no arquivo e, rodando direto, devolvia

```
20261012_133746  R/B = 2.64   ENVIA
20261012_133756  R/B = 2.65   ENVIA
20261012_133825  R/B = 1.70   pula
20261012_214922  R/B = 1.91   pula
```

Duas das quatro passariam. O servidor no ar dizia 1,00 para todas.

## A causa

**O Python carrega os módulos uma vez, ao iniciar, e não recarrega.** Uma janela
do `run.cmd` aberta antes de uma correção continua rodando o código antigo — para
sempre, até ser fechada.

Isso já confundiu várias vezes nesta sessão. O sintoma é traiçoeiro: o erro
volta **idêntico**, e a conclusão natural é "a correção não funcionou", quando
na verdade ela nem chegou a rodar.

## A correção: a tela detecta sozinha

Não dá para impedir o Python de manter o módulo em memória. Mas dá para
**detectar** e avisar.

1. O servidor anuncia os recursos que implementa (`servidor.RECURSOS`).
2. A tela declara os recursos que espera (`RECURSOS_ESPERADOS`) e confere a
   cada carga de estado.
3. Se faltar algum, aparece uma faixa no topo:

```
A janela do programa está desatualizada

Esta tela é mais nova que o programa que está rodando. O Python carrega o
código uma vez, ao iniciar, e não recarrega sozinho — então correções recentes
não estão valendo nesta janela.

Feche a janela do run.cmd e abra de novo.

faltando: mascara_medida_no_negativo
```

Optei por **lista de recursos** em vez de carimbo de data. Comparar datas exige
sincronizar dois relógios e dois arquivos; comparar recursos responde à
pergunta que importa — "o servidor sabe fazer o que eu preciso?".

## Um limite duplicado que também tirei

Havia um `2.5` cru na função de conversão (`servidor.py:544`), enquanto a
restauração usava a constante `LIMITE_MASCARA`. Dois lugares para o mesmo
número: mudar um e esquecer o outro produziria comportamento inconsistente.
Agora os dois usam a constante.

## Testes

O `_teste_web.py` passou a conferir que **todo recurso que a tela espera existe
no servidor**. Se alguém acrescentar um recurso ao front e esquecer de
implementá-lo (ou o contrário), o teste acusa:

```
servidor implementa : 6 recursos
tela espera         : 4
ok  todo recurso que a tela espera existe no servidor
```

## Se acontecer de novo

1. Olhe a faixa no topo da tela. Se ela aparecer, **feche e reabra** o `run.cmd`.
2. Para conferir sem a tela:

```bash
curl http://127.0.0.1:8765/api/estado
```

A resposta traz `"recursos": [...]`. Se a lista não tiver
`mascara_medida_no_negativo`, o processo é antigo.
