# "Sem permissão de escrita" ao mudar as pastas de saída

## Resposta curta

**Não. Você não precisa dar permissão em cada pasta nova.** O problema não era a
pasta — era **onde o Python do programa está instalado**.

## O que estava acontecendo

A mensagem vinha da verificação que testa gravar um arquivo na pasta. Parecia
permissão de pasta, mas o ACL estava liberado:

```
E:\Negativos\positivo
  BUILTIN\Administradores          FullControl
  NT AUTHORITY\SISTEMA             FullControl
  NT AUTHORITY\Usuários autenticados  Modify     <-- o seu usuário podia gravar
```

## A medição que explicou tudo

Mesmo usuário, mesma pasta, mesmo instante — só mudando o interpretador:

| interpretador | gravar em `E:\Negativos\positivo` |
|---|---|
| `.venv\Scripts\python.exe` (dentro de `C:\Temp`) | **FALHOU** (errno 13) |
| `C:\neg35\venv\Scripts\python.exe` | OK |
| `C:\Program Files\Python313\python.exe` | OK |

E também:

| destino | `.venv` em `C:\Temp` | venv fora de `C:\Temp` |
|---|---|---|
| `C:\Temp\Deepseek\...` | OK | OK |
| `C:\Temp` (a própria raiz) | **FALHOU** | OK |
| `E:\...` | **FALHOU** | OK |

Ou seja: o ambiente virtual guardado **dentro de `C:\Temp`** consegue gravar
**somente dentro de `C:\Temp`**. Antes isso não aparecia porque as pastas de
saída também estavam em `C:\Temp\Deepseek`. Quando você mudou para `E:`, o
limite apareceu.

Não é o ACL da pasta, não é o Kaspersky bloqueando a pasta, e não é o código.

## A correção

Criei o ambiente **fora de `C:\Temp`**:

```
C:\neg35\venv\Scripts\python.exe
```

com as mesmas versões: numpy 2.3.4, Pillow 11.3.0, requests 2.32.5, rawpy 0.27.1.

E os atalhos passaram a preferi-lo:

| arquivo | mudança |
|---|---|
| `run.cmd` | usa `C:\neg35\venv` se existir; avisa se cair no `.venv` de `C:\Temp` |
| `reiniciar.cmd` | idem |
| `verificar.cmd` | idem, e mostra qual interpretador está em uso |
| `tools/preparar_ambiente.py` | cria o ambiente em `C:\neg35\venv` (não mais no projeto) |

`preparar_ambiente.py` respeita `NEG35_VENV` se você quiser outro lugar.

## Mensagens de erro melhoradas

Antes: `sem permissão de escrita (Permission denied)` — sem dizer onde nem por quê.

Agora: `sem permissão de escrita em E:\Negativos\positivo (Permission denied). O
ambiente Python está em C:\Temp\... (dentro de C:\Temp); nesta máquina ele só
grava dentro de C:\Temp. Use o ambiente em C:\neg35\venv.`

O caminho aparece também quando a pasta não pode ser criada.

## Verificação

```
E:\Negativos\posivito      gravavel=True
E:\Negativos\restaurada    gravavel=True
origem                     existe=True, 38 imagens
tudo_ok                    True
problemas                  []
interpretador do servidor  C:\neg35\venv\Scripts\python.exe
```

## Como saber se está usando o ambiente certo

Rode `verificar.cmd`. A primeira linha mostra o interpretador:

```
Interpretador: C:\neg35\venv\Scripts\python.exe
```

Se aparecer algo começando com `C:\Temp`, é o ambiente errado para pastas em
outros discos.

## Se um dia mover o projeto

Mantenha o ambiente **fora de `C:\Temp`**. Se precisar mudar de lugar, crie o
novo com:

```
"C:\Program Files\Python313\python.exe" -m venv D:\algum\caminho\venv
```

e instale as quatro bibliotecas. O `run.cmd` prefere `C:\neg35\venv`; para outro
caminho, ajuste a variável `NEG35_PY` nele (ou defina `NEG35_VENV` ao rodar
`preparar_ambiente.py`).

## Observação sobre a sua pasta de origem

A origem mudou para `E:\Negativos\RAW` e tem **38 imagens**. O programa lê
normalmente. Só a **escrita** era o problema.
