# Comparação lado a lado: positivo × restaurado

Na tela, cada foto ganhou duas formas de ver a comparação:

1. **No visor de zoom** — o botão **"Comparar com a restaurada"** aparece
   quando a foto tem restaurada. Clica na miniatura, depois no botão.
2. **Atalho na célula** — nas fotos já restauradas aparece um ícone `⇄` no
   canto. Um clique abre a comparação direto.

Para ver as já restauradas na grade (elas somem depois de prontas), marque
**"Mostrar também as já restauradas"**.

## Como a comparação é montada

Rota: `GET /midia/comparar/<nome>?w=1500`

**Montada no servidor**, não com duas tags `<img>` no navegador. Motivo medido:
o navegador baixa **um** arquivo reduzido em vez de duas imagens grandes.

| | bytes |
|---|---|
| positivo cheio | 3.751.147 |
| restaurado cheio | 1.319.570 |
| **soma** | **5.070.717** |
| **comparação** | **702.361** (14% da soma) |

### Cuidado que parecia detalhe e não era

A IA devolve ~704×1472, enquanto o positivo é 1868×4000. Mesma proporção,
resoluções diferentes — o que é normal, porque o modelo normaliza a resolução
internamente.

A primeira versão da comparação apenas **igualava as alturas**. O resultado
ficou enganoso: a metade restaurada ficava com um terço da largura, e o olho
comparava **escalas diferentes** — o rosto parecia "maior" no lado do positivo,
dando impressão falsa de mais detalhe.

Corrigido com **letterbox**: as duas metades são escaladas pela mesma altura e
centradas numa caixa com a proporção do positivo. O que se compara é conteúdo,
não zoom.

## Legenda

Cada lado leva um rótulo no topo: `positivo (inversão local)` e
`restaurado pela IA`.

A altura da faixa é **proporcional à imagem** (2,5%, mínimo 40 px) e a fonte
escala junto. Com faixa fixa de 34 px o texto virava um risco ilegível em
imagens grandes — testado e corrigido.

A fonte TrueType é procurada entre `segoeui.ttf`, `arial.ttf` e
`DejaVuSans.ttf`; se nenhuma existir, cai para a fonte padrão do Pillow com a
faixa ajustada.

## Erros tratados

| Situação | Resposta |
|---|---|
| foto sem restaurada | 404 com `esta foto ainda não foi restaurada` |
| foto sem positivo | 404 com `sem positivo para comparar` |
| tipo de mídia inválido | 400 |
| falha ao montar | 500 com a causa |

A mensagem é específica de propósito: "o que fazer" muda conforme qual dos dois
lados falta.

## Testes

```bash
.venv\Scripts\python.exe tools\_teste_comparador.py
```

Cobre: PNG válido, respeito ao `largura_max`, altura escalando junto na
redução, **letterbox com a folga central**, economia de bytes contra a soma das
duas cheias, os dois erros de arquivo faltando, a rota HTTP (200 e os 404/400) e
a ligação no JS/HTML.

### Um erro de método que cometi

A primeira versão deste teste usava `synthetic.tira_de_teste`, que gera áreas
chapadas: o PNG saía com 1,3 KB e as asserções sobre tamanho não significavam
nada (a "comparação" ficava *maior* que as duas imagens somadas, porque o PNG
original comprimia melhor). Passei a usar a imagem real do teste.
