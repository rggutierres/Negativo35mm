# A restauração falhava: a chave não era usada

## O sintoma

No console do navegador:

```
Failed to load resource: the server responded with a status of 409 (Conflict)
  :8765/api/restaurar
falhas: Array(1)      app.js:421
```

O `409` e o "falhas" eram **dois problemas diferentes**.

## Problema 1: a chave do `.env` era ignorada

**O mais grave.** A tela mostrava *"Chave de API configurada ✓"*, o `.env` tinha
a chave preenchida (73 caracteres), e a restauração falhava com:

```
Falta a chave de API. Defina OPENROUTER_API_KEY (ou passe api_key=...).
```

**Causa**: `api.Restauracao`, quando não recebe a chave, procura **apenas em
variável de ambiente** (`_chave_do_ambiente`). O `.env` — que é onde o usuário
configura, inclusive pela engrenagem da tela — **nunca era consultado**. E o
`servidor.restaurar` não passava a chave:

```python
rest = api.Restauracao(
    provedor=cfg.provedor, modelo=cfg.modelo, prompt=cfg.prompt
)          # <- sem api_key
```

Mensagem enganosa: mandava definir uma variável de ambiente, quando o valor
estava no arquivo de configuração que o próprio programa gerencia.

**Correção**: `servidor._chave_do_provedor(cfg)` resolve a chave pelo `.env`
(e usa a variável de ambiente como reserva), e o `Restauracao` recebe o valor.

Provado com a camada HTTP interceptada — a chave certa é enviada:

```
Authorization enviado: Bearer sk-or-v1-CHAVE-DE-TESTE-12345...
ok  enviou a chave que está no .env
ok  chegou até a camada HTTP (não parou antes)
```

## Problema 2: o `409` e o "veja o console"

O servidor recusa um segundo trabalho enquanto o primeiro roda (um por vez,
para o progresso não virar sopa). Isso é intencional — mas a tela:

- convertia esse `409` num toast com o texto cru do servidor;
- quando havia falhas, dizia **"N falha(s). Veja o console (F12)"**.

Ou seja: o motivo real ficava escondido no console, e o usuário tinha de abrir
o F12 para descobrir *o que* falhou.

**Correção**:

1. **`409` tratado antes de enviar.** A tela verifica se há trabalho em
   andamento e explica — em vez de deixar o servidor recusar.
2. **O motivo aparece na tela.** Os resultados são agrupados por motivo (o
   mesmo motivo costuma valer para várias fotos) e mostrados numa faixa que
   **fica visível** e pode ser relida depois que o aviso desaparece.
3. **"Máscara fraca" é explicado.** Quando todas as puladas são por máscara
   fraca, a tela explica o que isso significa e como forçar, se quiser.

Agora o resultado aparece assim, sem precisar do console:

```
Restauração: 0 de 1 ok
  Falta a chave de API do openrouter no arquivo .env (campo openrouter_api_key).
  Preencha pela engrenagem ou edite o .env.
```

## Sobre a proteção de máscara fraca

A restauração **pula** (sem gastar) os positivos cujo negativo perdeu a
correção de cor laranja — R/B abaixo de 2,5. Medido:

```
boa     base=(0.3773, 0.2675, 0.1471)  R/B=2.57  envia para a IA
fraca   base=(1.0000, 1.0000, 1.0000)  R/B=1.00  PULA (máscara fraca)
```

Isso **não é um erro** — é uma proteção. A IA não recupera esses casos: ela
inventa detalhes, e o resultado engana. A tela agora distingue "pulada" de
"falhou", e a caixa **"Forçar mesmo com máscara fraca"** permite tentar mesmo
assim (é pago).

## Testes

```bash
.venv\Scripts\python.exe tools\_teste_pastas.py
```

A verificação nova intercepta a camada HTTP e confere **qual chave seria
enviada** — sem chamar a rede e sem gastar. Se alguém voltar a não passar a
chave, o teste acusa.
