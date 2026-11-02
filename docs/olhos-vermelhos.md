# Filtro de olhos vermelhos

## O que é

Botão **Olhos vermelhos** no visor: você marca a área dos olhos e o programa
neutraliza o vermelho do flash dentro dela.

## Por que a área é obrigatória (não é preguiça)

Testei o detector automático nas 24 restauradas, aplicado à foto inteira:

| foto | regiões detectadas |
|---|---|
| 133734 | 22 |
| 133746 | 24 |
| 133756 | 37 |
| 133814 | 35 |
| 214701 | 28 |

Olhos vermelhos são **2 regiões**, algumas centenas de pixels. O resto são falsos
positivos: tons de pele, objetos avermelhados, ruído do filme.

Aplicar isso na foto inteira neutralizaria vermelhos legítimos — estragaria a
foto. Então você marca o rosto, e só ali o filtro trabalha.

## Como funciona

1. **Button "Olhos vermelhos"** → abre a mesma caixa de seleção do recorte, já
   com folga de 25% (área de rosto, não recorte de borda).
2. Você ajusta a caixa em volta dos olhos.
3. **Corrigir olhos** → o servidor processa só aquele retângulo.

### A detecção, em duas etapas

**1. Marca pixels com vermelho anômalo:**

```
R > 0,28               (não é sombra)
R > 1,45 × maior(G,B)  (vermelho domina)
(R − menor)/R > 0,42   (saturação alta)
```

**2. Agrupa em regiões e descarta o que não tem cara de pupila:**

| critério | faixa | por quê |
|---|---|---|
| área | 12 a 8 000 px | blusa vermelha é maior |
| largura e altura | ≥ 3 px | borda de objeto é traço fino |
| preenchimento | ≥ 0,35 | pupila é redonda; "L" de tecido preenche pouco |

**3. Neutraliza:** `R := (G + B) / 2`, só nos pixels aceitos. G e B não são
tocados, então o resto da imagem fica idêntico.

### Calibração testada

Imagem sintética com duas pupilas vermelhas e uma blusa vermelha grande:

```
regiões aceitas        : 2        (as duas pupilas)
pupila antes           : (0,75, 0,12, 0,10)
pupila depois          : (0,11, 0,12, 0,10)   ← neutra
blusa depois           : (0,72, 0,14, 0,12)   ← intacta
```

## Segurança

- guarda cópia em `_antes_da_rotacao/` antes de gravar;
- se nenhuma região for aceita, **não grava nada** e avisa quantas foram
  descartadas — sem criar backup à toa;
- a força padrão é 0,85 (deixa um resto de cor, às vezes mais natural que
  neutralizar por completo).

## Limitações, ditas com clareza

- **funciona melhor com pupila bem vermelha.** Reflexo alaranjado fraco pode não
  atingir os limiares.
- **não corrige "olho branco"** (leucocoria) nem olho estourado sem cor.
- **se a pupila estiver muito pequena** (menos de ~4 px de diâmetro), a região
  cai no limite de área e não é aceita.
- o filtro **supõe que o vermelho da pupila é erro**. Se você marcar a área de
  um objeto realmente vermelho, ele pode neutralizar esse objeto — por isso a
  área deve ser só o rosto.

## Verificação

```
_regiões detectadas no sintético : 2
pupila corrigida                 : sim
blusa vermelha preservada        : sim
área sem vermelho                : não grava
retângulo invertido              : recusado
foto inexistente                 : recusado
arquivo real do usuário          : não foi tocado nos testes
```
