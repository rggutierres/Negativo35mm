# O Explorer não abre: limitação do ambiente

## O sintoma

Ao clicar no caminho da pasta, aparece o erro do Windows:

```
explorer.exe - Erro de aplicativo
O aplicativo não pôde ser inicializado corretamente (0xc0000142).
```

`0xc0000142` é `STATUS_DLL_INIT_FAILED`: o processo **foi criado**, mas não
conseguiu inicializar.

## O que testei

Quatro formas de abrir a pasta, todas medidas neste ambiente:

| método | resultado |
|---|---|
| `os.startfile` (ShellExecute) | `PermissionError: [WinError 5] Acesso negado` |
| `subprocess.Popen(["explorer", caminho])` | sem exceção, mas **0 processos** sobem |
| `subprocess.Popen('explorer "..."', shell=True)` | idem |
| `cmd /c start "" caminho` | idem |

O `explorer.exe` é criado e **morre imediatamente** — nenhuma janela aparece, e
o Windows mostra o diálogo de erro.

## A causa

O servidor roda numa **sessão restrita**, que impede a criação de processos de
interface. Não é um caminho errado nem permissão de pasta: o próprio
`explorer.exe` não consegue subir como processo filho.

**Não há correção possível pelo código.** Tentei as vias oficiais do Windows e
todas são bloqueadas pela mesma restrição. Em execução normal (fora desta
sessão), o `os.startfile` abre o Explorer sem problema.

## O que foi feito

**1. Botão de copiar o caminho.** Ao lado de cada pasta há um botão que copia o
caminho para a área de transferência, para colar no Explorer (Win+E, depois
Ctrl+L).

```
origem E:\Bkp\...\RAW ↗  ⧉     positivos C:\...\saida\positivo ↗  ⧉
```

**2. Se o Explorer falhar, a cópia acontece sozinha.** Clicar no caminho tenta
abrir; se não conseguir, copia o caminho e avisa — em vez de deixar você sem
nada.

**3. O método de cópia também precisou de cuidado.** Criar processos externos é
justamente o que está bloqueado, então `powershell Set-Clipboard` e `clip.exe`
**também falham** aqui. O que funciona é o `tkinter`, que copia **dentro do
próprio processo**:

```
tkinter      OK
powershell   FALHOU
clip.exe     FALHOU
```

Por isso a ordem é: `tkinter` → `powershell` → `clip`. A primeira que
funcionar é usada.

## Como usar

- **Clique no caminho**: tenta abrir o Explorer; se não der, copia o caminho.
- **Clique no ⧉**: só copia, sem tentar abrir.

Depois, para colar: `Win+E` abre o Explorer, `Ctrl+L` foca a barra de endereço,
`Ctrl+V` cola.

## Testes

O `_teste_app.py` verifica que a rota responde 200 para as três pastas e 400
para um valor inválido. Não dá para testar "a janela abriu" de forma
automatizada — e neste ambiente ela nunca abre.
