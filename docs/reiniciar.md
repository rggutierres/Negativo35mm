# Reiniciar o programa (e por que é preciso)

## O problema

O Python carrega os módulos **uma vez, ao iniciar**, e não recarrega. Uma janela
aberta antes de uma correção continua rodando o código antigo — para sempre,
até ser fechada.

Isso custou tempo várias vezes nesta sessão. O sintoma é traiçoeiro: o erro
volta **idêntico**, e a conclusão natural é "a correção não funcionou", quando
na verdade ela nem chegou a rodar.

Aconteceu de novo com a correção de cor: a função certa estava no arquivo, e o
servidor no ar ainda reportava o comportamento antigo:

```
GET /api/estado -> recursos: [mascara_medida_no_negativo, ...]
                   sem "cor_no_envio"
```

## A solução: `reiniciar.cmd`

```
reiniciar.cmd
```

Ele encerra qualquer janela antiga do neg35 e abre uma nova. Use este arquivo
depois de uma atualização; o `run.cmd` continua sendo o do dia a dia.

## Como saber se a janela está velha

**1. A própria tela avisa.** O servidor anuncia os recursos que implementa
(`servidor.RECURSOS`) e a tela confere se tem tudo o que espera. Se faltar,
aparece uma faixa no topo:

```
A janela do programa está desatualizada
...
Feche a janela do run.cmd e abra de novo.
faltando: cor_no_envio
```

**2. Pelo terminal:**

```bash
curl http://127.0.0.1:8765/api/estado
```

A lista `recursos` precisa conter:

| recurso | o que garante |
|---|---|
| `mascara_medida_no_negativo` | a máscara é medida no DNG, não no positivo |
| `cor_no_envio` | a imagem vai para a IA em sRGB, sem escurecer |
| `abrir_pasta_no_explorer` | clicar no caminho abre a pasta |
| `cache_adobe_configuravel` | `pasta_cache_adobe` no `.env` |
| `pastas_de_saida_testadas` | testa escrita antes de escolher a pasta |
| `chave_do_env` | usa a chave de API do `.env` |
| `converter_auto_opcional` | a conversão automática pode ser desligada |
| `comparacao_lado_a_lado` | comparação positivo × restaurado |

## O `.env` não precisa mais de reinício

A configuração **passou a ser relida** sempre que o arquivo muda (comparamos o
mtime). Antes ela ficava em memória desde a inicialização, e editar as pastas
pela engrenagem não se refletia até reiniciar.

Ou seja: **pastas e ajustes** mudam na hora. **Código** ainda precisa de
reinício — não há como recarregar módulos em uso com segurança.

## Testes

Vários testes sobem um servidor com um `.env` próprio. Depois da releitura
automática, eles precisaram apontar também `ENV_PADRAO` — senão a releitura
trazia de volta o `.env` do projeto e o teste passava a enxergar as pastas do
usuário (o `_teste_app` chegou a contar 27 fotos onde esperava 3).

Está registrado aqui porque é uma armadilha para quem for escrever testes novos
com servidor: **aponte `ENV_PADRAO` e `_cfg_atual`**, não só um dos dois.
