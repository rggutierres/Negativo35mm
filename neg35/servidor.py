"""
Lógica da interface web: varredura, conversão e restauração com progresso.

Separado do servidor HTTP de propósito: estas funções são testáveis sem abrir
porta nenhuma. O servidor em tools/app.py só cuida de rotas.

FLUXO
-----
1. `estado()`       -> compara a pasta de origem com a de positivos e com a de
                       restaurados, e diz o que falta em cada etapa
2. `converter()`    -> gera os positivos que faltam, com callback de progresso
3. `restaurar()`    -> manda para a IA os que o usuário marcou, com progresso
"""

from __future__ import annotations

import json
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import adobe, api, config, core, curva, pipeline, post, render

__all__ = ["Item", "estado", "converter", "restaurar", "thumb", "comparar",
           "comparar_virtual", "parede_de_comparacoes", "verificar_pastas",
           "testar_escrita", "abrir_pasta", "copiar_para_area_de_transferencia",
           "RECOMENDADOS", "Trabalho"]

EXT_IMAGEM = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2",
              ".pef", ".jpg", ".jpeg", ".tif", ".tiff", ".png"}
EXT_RAW = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2", ".pef"}

# Limite de máscara para enviar à IA: R/B abaixo disto, o negativo perdeu a
# correção de cor laranja e a IA não recupera (ela inventa detalhes).
#
# Medido em negativos reais: um bem exposto fica entre 2,6 e 4,5; um
# neutralizado fica perto de 1. 2,5 separa os dois com folga.
LIMITE_MASCARA = 2.5


# Valores recomendados, com o mesmo conteúdo do botão "Restaurar recomendados"
# da tela. Ficam aqui (e não só no JavaScript) para que o servidor seja a
# fonte da verdade e a tela possa mostrá-los ao lado de cada campo.
RECOMENDADOS = {
    "filme": "generico",
    "saturacao": 1.15,
    "nitidez": 0.40,
    "balanco": 0.90,
    "curva_alvo": 0.50,
    "curva_gamma": 0.0,
    "max_lado_envio": 1536,
    "usar_curva": True,
    "usar_adobe": True,
}


@dataclass
class Item:
    """Uma foto, nas três etapas do fluxo."""
    nome: str
    fonte: Path
    tipo: str                      # "DNG" ou "JPG"
    mb: float
    tem_positivo: bool
    tem_restaurado: bool
    positivo: Path | None = None
    restaurado: Path | None = None
    aviso: str = ""

    def como_dict(self) -> dict:
        return {
            "nome": self.nome,
            "tipo": self.tipo,
            "mb": round(self.mb, 1),
            "tem_positivo": self.tem_positivo,
            "tem_restaurado": self.tem_restaurado,
            "aviso": self.aviso,
            "url_positivo": f"/midia/positivo/{self.nome}" if self.tem_positivo else None,
            "url_restaurado": f"/midia/restaurado/{self.nome}" if self.tem_restaurado else None,
        }


def nome_positivo(stem: str) -> str:
    return f"{stem}_positivo.png"


def desfazer_restaurado(cfg: config.Config, nome: str,
                        backup: str | None = None) -> dict:
    """
    Desfaz a última alteração feita na restaurada, voltando ao arquivo anterior.

    Serve para quando o ajuste ficou ruim: correção de olhos que pegou demais,
    recorte no lugar errado, giro que não era aquele. Todas essas operações já
    guardam cópia em `_antes_da_rotacao/`; esta função usa essas cópias.

    `backup` (opcional) escolhe UMA cópia específica -- é o que a tela manda
    quando sabe qual operação acabou de fazer. Sem ele, usa a mais recente
    daquela foto.

    SEGURANÇA: só aceita nome de arquivo simples, dentro da pasta de backups, e
    cujo nome comece pelo nome desta foto. Sem isso, `backup` viraria um "leia
    qualquer arquivo do disco e grave como imagem".

    NÃO guarda cópia do estado atual: desfazer significa que aquele resultado não
    serve. Guardar permitiria alternar sem parar e encheria a pasta.
    """
    pasta = Path(cfg.pasta_restaurada)
    alvo = pasta / nome_restaurado(nome)
    if not alvo.is_file():
        raise FileNotFoundError(f"não existe restaurada para {nome}")

    bkp_dir = pasta / "_antes_da_rotacao"
    if not bkp_dir.is_dir():
        raise FileNotFoundError("não há alteração anterior para desfazer")

    if backup:
        # `Path(...).name` descarta qualquer caminho: só sobra o nome do arquivo.
        cand = bkp_dir / Path(str(backup)).name
        if not cand.is_file():
            raise FileNotFoundError(f"não achei a cópia {Path(str(backup)).name}")
        if not cand.name.startswith(alvo.stem):
            raise ValueError("a cópia não pertence a esta foto")
    else:
        copias = sorted(bkp_dir.glob(f"{alvo.stem}_*.png"),
                        key=lambda p: p.stat().st_mtime)
        if not copias:
            raise FileNotFoundError("não há alteração anterior para desfazer")
        cand = copias[-1]

    from PIL import Image

    with Image.open(cand) as im:
        tamanho = list(im.size)

    shutil.copy2(cand, alvo)
    return {"nome": nome, "backup_usado": cand.name, "tamanho": tamanho}


def corrigir_olhos_restaurado(cfg: config.Config, nome: str,
                              x0: float = 0.0, y0: float = 0.0,
                              x1: float = 1.0, y1: float = 1.0,
                              forca: float = 0.85) -> dict:
    """
    Corrige olhos vermelhos na restaurada, DENTRO de um retângulo em fração.

    POR QUE A ÁREA É OBRIGATÓRIA, e não uma opção:

    Medi o detector nas 24 restauradas e ele acha entre 17 e 37 regiões por foto,
    somando 4 a 25 mil pixels. Os olhos vermelhos são 2 regiões e algumas centenas
    de pixels. O resto são falsos positivos: tons de pele, objetos avermelhados,
    ruído do filme.

    Aplicar isso na foto inteira neutralizaria vermelhos legítimos -- estragaria
    a foto. Então o usuário marca a região dos olhos e só ali o filtro trabalha.
    Dentro da área marcada, a filtragem de forma (área, proporção, preenchimento)
    continua valendo, e é ela que impede que uma blusa vermelha na mesma área
    seja neutralizada.

    Linhas:
    - guarda cópia antes de gravar, em `_antes_da_rotacao/`;
    - não grava nada se nenhuma região for encontrada (devolve pixels=0).
    """
    from . import olhos

    alvo = Path(cfg.pasta_restaurada) / nome_restaurado(nome)
    if not alvo.is_file():
        raise FileNotFoundError(f"não existe restaurada para {nome}")

    try:
        v = [float(x) for x in (x0, y0, x1, y1)]
    except (TypeError, ValueError):
        raise ValueError("coordenadas inválidas") from None
    if not all(0.0 <= x <= 1.0 for x in v):
        raise ValueError("coordenadas precisam estar entre 0 e 1")
    if not (v[0] < v[2] and v[1] < v[3]):
        raise ValueError("o retângulo está invertido")
    if (v[2] - v[0]) < 0.01 or (v[3] - v[1]) < 0.01:
        raise ValueError("área pequena demais")

    from PIL import Image

    with Image.open(alvo) as im:
        im = im.convert("RGB")
        a = np.asarray(im).astype(np.float64) / 255.0
        h, w = a.shape[:2]

        px0 = max(int(round(v[0] * w)), 0)
        py0 = max(int(round(v[1] * h)), 0)
        px1 = min(int(round(v[2] * w)), w)
        py1 = min(int(round(v[3] * h)), h)
        if px1 - px0 < 8 or py1 - py0 < 8:
            raise ValueError("área pequena demais em pixels")

        recorte = a[py0:py1, px0:px1]
        corrigido, info = olhos.corrigir(recorte, forca=forca)

        resultado = {
            "nome": nome,
            "regioes": info.get("regioes_aceitas", 0),
            "pixels": int(info.get("pixels", 0)),
            "forca": float(forca),
            "area": [px0, py0, px1, py1],
            "gravado": False,
        }
        if not resultado["pixels"]:
            # Nada encontrado: não grava, para não criar backup à toa.
            return resultado

        backup_dir = Path(cfg.pasta_restaurada) / "_antes_da_rotacao"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = (backup_dir
                  / f"{alvo.stem}_olhos_{time.strftime('%Y%m%d_%H%M%S')}.png")
        shutil.copy2(alvo, backup)

        a[py0:py1, px0:px1] = corrigido
        tmp = alvo.with_suffix(".tmp.png")
        Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)).save(
            tmp, format="PNG", optimize=True)
    tmp.replace(alvo)
    resultado["gravado"] = True
    resultado["backup"] = str(backup)
    return resultado


def recortar_restaurado(cfg: config.Config, nome: str, x0: float, y0: float,
                        x1: float, y1: float) -> dict:
    """
    Recorta a imagem RESTAURADA por um retângulo dado em FRAÇÃO (0 a 1).

    Fracao, e não pixel, de propósito: a tela mostra a imagem com zoom variável,
    e a mesma fração vale para qualquer tamanho de janela. Se viesse em pixel, o
    recorte dependeria do zoom em que o usuário estava -- e a foto seria cortada
    no lugar errado.

    Também guarda cópia antes de gravar, pela mesma razão da rotação: recortar
    errado é fácil, e a restauração custou dinheiro. A cópia fica em
    `<restaurada>/_antes_da_rotacao/`, que a listagem da tela não enxerga.

    Recusa recorte com menos de 5% em qualquer lado, e recusa a imagem inteira
    (não é recorte, é nada).
    """
    alvo = Path(cfg.pasta_restaurada) / nome_restaurado(nome)
    if not alvo.is_file():
        raise FileNotFoundError(f"não existe restaurada para {nome}")

    try:
        v = [float(x) for x in (x0, y0, x1, y1)]
    except (TypeError, ValueError):
        raise ValueError("coordenadas inválidas") from None

    if not all(0.0 <= x <= 1.0 for x in v):
        raise ValueError("coordenadas precisam estar entre 0 e 1")
    if not (v[0] < v[2] and v[1] < v[3]):
        raise ValueError("o retângulo está invertido")
    if (v[2] - v[0]) < 0.05 or (v[3] - v[1]) < 0.05:
        raise ValueError("recorte menor que 5% em um dos lados")
    if (v[2] - v[0]) > 0.995 and (v[3] - v[1]) > 0.995:
        raise ValueError("o retângulo é a imagem inteira; nada a recortar")

    backup_dir = Path(cfg.pasta_restaurada) / "_antes_da_rotacao"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{alvo.stem}_recorte_{time.strftime('%Y%m%d_%H%M%S')}.png"
    shutil.copy2(alvo, backup)

    from PIL import Image

    with Image.open(alvo) as im:
        im = im.convert("RGB")
        w, h = im.size
        px0 = max(int(round(v[0] * w)), 0)
        py0 = max(int(round(v[1] * h)), 0)
        px1 = min(int(round(v[2] * w)), w)
        py1 = min(int(round(v[3] * h)), h)
        if px1 - px0 < 8 or py1 - py0 < 8:
            raise ValueError("recorte pequeno demais em pixels")
        cortada = im.crop((px0, py0, px1, py1))
        tamanho = list(cortada.size)
        tmp = alvo.with_suffix(".tmp.png")
        cortada.save(tmp, format="PNG", optimize=True)
    tmp.replace(alvo)

    return {"nome": nome, "tamanho": tamanho, "backup": str(backup),
            "pixels": [px0, py0, px1, py1]}


def nome_restaurado(stem: str) -> str:
    return f"{stem}_restaurado.png"


def girar_restaurado(cfg: config.Config, nome: str, angulo: float) -> dict:
    """
    Gira a imagem RESTAURADA por um ângulo QUALQUER, em graus, sentido horário.

    Para que serve o ângulo fino: negativo fotografado meio torto precisa de 1 ou
    2 graus para o quadro ficar reto. Múltiplos de 90 não resolvem isso.

    `expand=True` é obrigatório: sem ele, girar uma imagem em pé produz uma faixa
    cortada em vez da imagem girada. Com ângulo que não é múltiplo de 90, a imagem
    cresce e os cantos vazios ficam PRETOS -- é de propósito: preto não se
    confunde com conteúdo, e o usuário pode recortar as bordas depois com a
    ferramenta de recorte.

    Recusa ângulo zero (não é rotação) e acima de 360.

    ANTES DE GRAVAR, GUARDA UMA CÓPIA, pela mesma razão da rotação de 90: girar
    por engano é fácil e a restauração custou dinheiro. A cópia fica em
    `<restaurada>/_antes_da_rotacao/`, que a listagem da tela não enxerga.

    Devolve {"nome", "angulo", "tamanho", "backup"}.
    """
    alvo = Path(cfg.pasta_restaurada) / nome_restaurado(nome)
    if not alvo.is_file():
        raise FileNotFoundError(f"não existe restaurada para {nome}")

    try:
        angulo = float(angulo)
    except (TypeError, ValueError):
        raise ValueError("ângulo inválido") from None
    if abs(angulo) < 0.05:
        raise ValueError("ângulo zero não é rotação")
    if abs(angulo) > 360:
        raise ValueError("ângulo acima de 360 graus")

    backup_dir = Path(cfg.pasta_restaurada) / "_antes_da_rotacao"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{alvo.stem}_{time.strftime('%Y%m%d_%H%M%S')}.png"
    shutil.copy2(alvo, backup)

    from PIL import Image

    with Image.open(alvo) as im:
        im = im.convert("RGB")
        # rotate() do PIL gira no sentido ANTI-horário para ângulo positivo,
        # então negamos para girar no horário (que é o que o botão promete).
        girada = im.rotate(-angulo, expand=True, resample=Image.BICUBIC,
                           fillcolor=(0, 0, 0))
        tamanho = list(girada.size)
        tmp = alvo.with_suffix(".tmp.png")
        girada.save(tmp, format="PNG", optimize=True)
    tmp.replace(alvo)

    return {"nome": nome, "angulo": angulo, "tamanho": tamanho,
            "backup": str(backup)}


def rotacionar_restaurado(cfg: config.Config, nome: str,
                          giros: int = 1) -> dict:
    """
    Gira a imagem RESTAURADA em 90 graus no sentido horário, `giros` vezes.

    Atalho para `girar_restaurado`, que aceita qualquer ângulo. Mantido porque o
    botão "Rotacionar 90°" e os testes usam esta forma, em passos inteiros.

    Devolve {"nome", "giros", "angulo", "tamanho", "backup"}.
    """
    giros = int(giros) % 4
    if giros == 0:
        raise ValueError("giros precisa ser 1, 2 ou 3")
    r = girar_restaurado(cfg, nome, 90 * giros)
    r["giros"] = giros
    return r


def _escanear(pasta: Path, sufixo: str) -> dict[str, Path]:
    """Mapa {nome_base: caminho} dos arquivos que terminam com o sufixo."""
    saida: dict[str, Path] = {}
    if not pasta.is_dir():
        return saida
    for p in pasta.iterdir():
        if p.is_file() and p.name.endswith(sufixo):
            base = p.name[: -len(sufixo)]
            saida[base] = p
    return saida


def testar_escrita(pasta: Path) -> tuple[bool, str]:
    """
    Tenta gravar de verdade na pasta. Devolve (ok, motivo).

    Existe porque a unidade que o Google Drive cria no Windows é um sistema de
    arquivos virtual: escrever nela por programa falha com "Acesso negado".
    Descobrir isso na abertura é melhor que descobrir depois de converter 20
    fotos -- e melhor ainda que descobrir depois de pagar a IA.

    O motivo descreve SÓ o que foi observado. Não afirmamos a causa: já
    aconteceu de o bloqueio não ter nada a ver com nuvem (perfil de rede,
    política da máquina), e uma mensagem que chuta a causa errada atrapalha.
    """
    try:
        pasta.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        motivo = e.strerror or str(e)
        return False, (f"não consegui criar a pasta {pasta} ({motivo}). "
                       f"Se não for uma restrição da máquina, tente outra pasta.")
    teste = pasta / "_neg35_escrita.tmp"
    try:
        teste.write_bytes(b"x")
        teste.unlink()
        return True, ""
    except OSError as e:
        motivo = e.strerror or str(e)
        dica = ""
        # Causa medida nesta máquina: o ambiente virtual dentro de C:\Temp só
        # grava dentro de C:\Temp (ver config.testar_escrita_simples).
        exe = _ambiente_dentro_do_temp()
        if exe:
            dica = (f" O ambiente Python está em {exe} (dentro de C:\\Temp);"
                    f" nesta máquina ele só grava dentro de C:\\Temp. Use o"
                    f" ambiente em C:\\neg35\\venv.")
        return False, f"sem permissão de escrita em {pasta} ({motivo}).{dica}"


def _ambiente_dentro_do_temp() -> str:
    """
    Caminho do interpretador, se ele estiver dentro de C:\\Temp; senão "".

    Isolado numa função para poder ser testado sem tocar em disco.
    """
    import sys as _sys

    exe = _sys.executable or ""
    return exe if exe.lower().startswith("c:\\temp\\") else ""


def verificar_pastas(cfg: config.Config) -> dict:
    """
    Confere origem, positivos e restauradas: existem? dá para gravar?

    Devolve um diagnóstico que a tela mostra ao abrir, em vez de deixar o
    usuário descobrir o problema no meio da conversão.
    """
    origem = Path(cfg.pasta_origem)
    positivo = Path(cfg.pasta_positivo)
    restaurada = Path(cfg.pasta_restaurada)

    origem_ok = origem.is_dir()
    n_origem = 0
    if origem_ok:
        n_origem = sum(1 for p in origem.iterdir()
                       if p.is_file() and p.suffix.lower() in EXT_IMAGEM)

    pos_ok, pos_erro = testar_escrita(positivo)
    res_ok, res_erro = testar_escrita(restaurada)

    problemas = []
    if not origem_ok:
        problemas.append(f"A pasta de origem não existe: {origem}")
    elif n_origem == 0:
        problemas.append(f"A pasta de origem não tem imagens: {origem}")
    if not pos_ok:
        problemas.append(f"Positivos: {pos_erro}")
    if not res_ok:
        problemas.append(f"Restauradas: {res_erro}")

    # A dica da nuvem só aparece quando o caminho REALMENTE parece de nuvem --
    # não como explicação genérica de qualquer "acesso negado".
    dica_nuvem = ""
    if not pos_ok and (_parece_unidade_de_nuvem(positivo)
                       or _parece_unidade_de_nuvem(restaurada)):
        dica_nuvem = ("A saída está numa unidade de nuvem (Google Drive/OneDrive), "
                      "que costuma recusar escrita por programa. Aponte a saída "
                      "para uma pasta local: os originais continuam onde estão.")

    return {
        "origem": {
            "caminho": str(origem), "existe": origem_ok,
            "imagens": n_origem,
            "na_nuvem": _parece_unidade_de_nuvem(origem),
        },
        "positivo": {
            "caminho": str(positivo), "existe": positivo.is_dir(),
            "gravavel": pos_ok, "erro": pos_erro,
            "na_nuvem": _parece_unidade_de_nuvem(positivo),
        },
        "restaurada": {
            "caminho": str(restaurada), "existe": restaurada.is_dir(),
            "gravavel": res_ok, "erro": res_erro,
            "na_nuvem": _parece_unidade_de_nuvem(restaurada),
        },
        "tudo_ok": origem_ok and n_origem > 0 and pos_ok and res_ok,
        "pode_converter": origem_ok and n_origem > 0 and pos_ok,
        "pode_restaurar": pos_ok and res_ok,
        "problemas": problemas,
        "dica_nuvem": dica_nuvem,
        "sugestao_local": str(config.pasta_local_padrao()),
    }


def _parece_unidade_de_nuvem(pasta: Path) -> bool:
    """
    Heurística: a pasta está numa unidade de nuvem?

    Não dá para detectar com certeza. Procuramos indícios no caminho:
    "GoogleDrive", "OneDrive", "Dropbox", "iCloud", ou uma letra de unidade
    diferente de C: com esses nomes no meio.
    """
    texto = str(pasta).lower()
    for marca in ("googledrive", "google drive", "onedrive", "dropbox",
                  "icloud", "box sync", "mydrive"):
        if marca in texto:
            return True
    return False


def estado(cfg: config.Config) -> dict:
    """
    Compara origem, positivos e restaurados.

    Devolve o estado completo: pastas, contagens e a lista de itens com o que
    falta em cada etapa.
    """
    origem = Path(cfg.pasta_origem)
    positivo_dir = Path(cfg.pasta_positivo)
    restaurado_dir = Path(cfg.pasta_restaurada)

    # Agrupa origem por nome-base, preferindo DNG sobre JPG.
    fontes: dict[str, dict] = {}
    if origem.is_dir():
        for p in sorted(origem.iterdir()):
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext not in EXT_IMAGEM:
                continue
            item = fontes.setdefault(p.stem, {})
            if ext in EXT_RAW:
                item["raw"] = p
            elif ext in {".jpg", ".jpeg"}:
                item["jpg"] = p
            else:
                item.setdefault("outro", p)

    positivos = _escanear(positivo_dir, "_positivo.png")
    restaurados = _escanear(restaurado_dir, "_restaurado.png")

    itens: list[Item] = []
    for nome, f in sorted(fontes.items()):
        fonte = f.get("raw") or f.get("jpg") or f.get("outro")
        if fonte is None:
            continue
        tipo = "DNG" if fonte.suffix.lower() in EXT_RAW else "JPG"
        pos = positivos.get(nome)
        res = restaurados.get(nome)
        itens.append(Item(
            nome=nome,
            fonte=fonte,
            tipo=tipo,
            mb=fonte.stat().st_size / 1048576,
            tem_positivo=pos is not None,
            tem_restaurado=res is not None,
            positivo=pos,
            restaurado=res,
        ))

    faltam_positivo = [i for i in itens if not i.tem_positivo]
    faltam_restaurar = [i for i in itens if i.tem_positivo and not i.tem_restaurado]

    return {
        "pastas": {
            "origem": str(origem),
            "positivo": str(positivo_dir),
            "restaurada": str(restaurado_dir),
            "origem_existe": origem.is_dir(),
            "positivo_existe": positivo_dir.is_dir(),
            "restaurada_existe": restaurado_dir.is_dir(),
        },
        "config": {
            "modelo": cfg.modelo,
            "provedor": cfg.provedor,
            "filme": cfg.filme,
            "saturacao": cfg.saturacao,
            "nitidez": cfg.nitidez,
            "balanco": cfg.balanco,
            "usar_curva": cfg.usar_curva,
            "curva_alvo": cfg.curva_alvo,
            "usar_adobe": cfg.usar_adobe,
            "max_lado_envio": cfg.max_lado_envio,
            "tem_chave": bool(
                cfg.openrouter_api_key if cfg.provedor == "openrouter" else cfg.gemini_api_key
            ),
        },
        "adobe_disponivel": adobe.disponivel(cfg.adobe_exe or None),
        "contagens": {
            "total": len(itens),
            "com_positivo": len(itens) - len(faltam_positivo),
            "com_restaurado": sum(1 for i in itens if i.tem_restaurado),
            "faltam_positivo": len(faltam_positivo),
            "faltam_restaurar": len(faltam_restaurar),
        },
        "itens": [i.como_dict() for i in itens],
        "pendentes_positivo": [i.nome for i in faltam_positivo],
        "pendentes_restaurar": [i.nome for i in faltam_restaurar],
    }


# ---------------------------------------------------------------------------
# Conversão para positivo
# ---------------------------------------------------------------------------
def copiar_para_area_de_transferencia(texto: str) -> tuple[bool, str]:
    """
    Copia texto para a área de transferência do Windows.

    Tenta primeiro o `tkinter`, que copia DENTRO deste processo. Isso importa
    porque criar processos externos é justamente o que falha sob sessão
    restrita: medido neste ambiente, `powershell` e `clip.exe` não conseguem
    subir. O `tkinter` não precisa de processo novo e funcionou.

    Devolve (ok, método usado ou motivo da falha).
    """
    import sys as _sys

    if _sys.platform != "win32":
        return False, "copiar para a área de transferência só está implementado no Windows"

    # 1) tkinter: sem processo externo.
    try:
        import tkinter

        raiz = tkinter.Tk()
        raiz.withdraw()
        raiz.clipboard_clear()
        raiz.clipboard_append(texto)
        raiz.update()          # sem isto o conteúdo evapora ao fechar a janela
        raiz.destroy()
        return True, "tkinter"
    except Exception:  # noqa: BLE001
        pass

    # 2) PowerShell, quando disponível.
    try:
        import subprocess

        p = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Set-Clipboard -Value '{texto}'"],
            capture_output=True, timeout=30,
        )
        if p.returncode == 0:
            return True, "powershell"
    except Exception:  # noqa: BLE001
        pass

    # 3) clip.exe, último recurso.
    try:
        import subprocess

        p = subprocess.run(["clip"], input=texto, text=True,
                           capture_output=True, timeout=20)
        if p.returncode == 0:
            return True, "clip"
    except Exception:  # noqa: BLE001
        pass

    return False, "nenhum método de cópia funcionou nesta máquina"


def abrir_pasta(caminho: str | Path) -> tuple[bool, str]:
    """
    Abre a pasta no gerenciador de arquivos do sistema.

    Se a pasta configurada ainda não existe, abre o ancestral existente mais
    próximo -- é mais útil que um erro, porque o usuário quer "ir até lá".

    IMPORTANTE: em alguns ambientes isto NÃO funciona, e o motivo não está no
    nosso código. Medido numa sessão restrita do Windows: `os.startfile` nega
    acesso e o `explorer.exe` é criado mas morre na inicialização
    (erro 0xc0000142, STATUS_DLL_INIT_FAILED) -- nenhuma janela aparece.

    Por isso a tela oferece também "copiar o caminho", que funciona nesses
    casos. Aqui devolvemos (ok, motivo) sem levantar exceção: falhar ao abrir
    uma janela não pode derrubar nada.
    """
    import subprocess
    import sys as _sys

    alvo = Path(caminho)
    if not alvo.exists():
        for pai in alvo.parents:
            if pai.exists():
                alvo = pai
                break
        else:
            return False, f"o caminho não existe: {caminho}"

    if _sys.platform != "win32":
        comando = (["open", str(alvo)] if _sys.platform == "darwin"
                   else ["xdg-open", str(alvo)])
        try:
            subprocess.Popen(comando)
            return True, str(alvo)
        except Exception as e:  # noqa: BLE001
            return False, f"não consegui abrir ({type(e).__name__}: {e})"

    # Windows: os.startfile é a via oficial quando dá; explorer como reserva.
    try:
        import os as _os

        _os.startfile(str(alvo))  # noqa: S606
        return True, str(alvo)
    except Exception:  # noqa: BLE001
        pass

    try:
        subprocess.Popen(["explorer", str(alvo)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, str(alvo)
    except Exception as e:  # noqa: BLE001
        return False, (f"não consegui abrir a pasta ({type(e).__name__}). "
                       f"Use o botão de copiar o caminho e cole no Explorer.")


# Recursos que ESTA versão do servidor implementa.
#
# A tela confere esta lista ao abrir. Se faltar algum recurso que ela espera, é
# porque o servidor está rodando código ANTIGO em memória (o Python carrega o
# módulo uma vez e não recarrega) -- e aí a tela avisa para reiniciar, em vez
# de deixar o usuário achar que a correção não funcionou.
RECURSOS = [
    "mascara_medida_no_negativo",   # mede a máscara no DNG, não no positivo
    "cache_adobe_configuravel",     # pasta_cache_adobe no .env
    "pastas_de_saida_testadas",     # testa escrita antes de escolher
    "chave_do_env",                 # usa a chave de API do .env
    "comparacao_lado_a_lado",
    "converter_auto_opcional",      # conversão automática desligável
    "cor_no_envio",                 # envia o positivo em sRGB, sem escurecer
    "abrir_pasta_no_explorer",      # clicar no caminho abre a pasta
    "copiar_caminho",               # alternativa quando o Explorer não abre
    "dica_por_foto",                # mede a foto e envia os números no prompt
    "refazer_com_brilho",           # refaz a restauração ajustando o brilho
    "zoom_so_restaurada",           # clicar abre só a restaurada, ampliada
    "recorte_de_borda",             # tira os furinhos e o quadro vizinho
    "aba_de_falhas",                # lista os negativos que não geraram positivo
    "aba_falha_restauro",           # falhas de restauração + botão de forçar
    "rotacionar_restaurada",        # girar 90° no visor e salvar no arquivo
    "recortar_restaurada",          # recortar arrastando as alças no visor
]

# Carimbo de build: data/hora da última alteração deste arquivo.
def versao_do_codigo() -> str:
    """Data/hora da última alteração deste arquivo, para diagnóstico."""
    try:
        return str(int(Path(__file__).stat().st_mtime))
    except OSError:
        return "0"


def _mascara_do_negativo(
    cfg: config.Config, nome: str
) -> tuple[float | None, str]:
    """
    Mede a máscara laranja no NEGATIVO, pelo MESMO caminho que a conversão usa.

    Devolve (R/B, motivo). R/B=None significa "não deu para medir" -- e aí NÃO
    pulamos: não medir não é o mesmo que medir ruim, e na dúvida quem decide é
    o usuário.

    Detalhe que importa: medimos no negativo passado pelo Adobe DNG Converter
    quando ele está disponível, porque é exatamente o arquivo que a conversão
    usa. Medir no DNG cru dá valores enganosos: vários DNG do celular vêm sem
    metadados de cor (`camera_whitebalance` falha com LibRawDataError), e aí o
    decodificador aplica balanço padrão e apaga o laranja -- medimos R/B ~1,6
    no cru e ~2,7 no convertido.
    """
    fonte = Path(cfg.pasta_origem)
    if not fonte.is_dir():
        return None, "(a pasta de origem não está acessível para medir a máscara)"

    candidatos = sorted(fonte.glob(f"{nome}.*"))
    raw = [c for c in candidatos if c.suffix.lower() in EXT_RAW]
    if not raw:
        return None, "(sem o DNG original para medir a máscara)"

    alvo = raw[0]
    if cfg.usar_adobe and adobe.disponivel(cfg.adobe_exe or None):
        cache = config.pasta_cache_adobe(cfg)
        if cache is not None:
            try:
                gerados, _ = adobe.converter([alvo], cache, exe=cfg.adobe_exe or None)
                if gerados:
                    alvo = gerados[0]
            except Exception:  # noqa: BLE001
                pass          # sem cache: mede no cru

    try:
        neg = pipeline.carregar(alvo, para_linear=True)
        base = core.detectar_base_do_filme(neg)
        rb = float(base[0] / max(base[2], 1e-9))
        return rb, ""
    except Exception as e:  # noqa: BLE001
        return None, f"(não consegui medir a máscara: {type(e).__name__})"


def apagar_restaurado(cfg: config.Config, nome: str) -> str:
    """
    Apaga o restaurado de uma foto, se existir. Devolve o caminho apagado ou "".

    Usado pela regeneração: refazer a restauração sem apagar a anterior deixaria
    duas versões no disco e o usuário sem saber qual está vendo.
    """
    alvo = Path(cfg.pasta_restaurada) / nome_restaurado(nome)
    try:
        if alvo.is_file():
            alvo.unlink()
            return str(alvo)
    except OSError:
        pass
    return ""


# Fator de escurecimento do modelo de imagem.
#
# Medido em quatro fotos: o resultado volta com a mediana da luminância em ~68%
# da que foi enviada. É sistemático -- por isso uma constante basta, e não é
# preciso um modelo de visão analisando cada foto para descobrir o parâmetro.
FATOR_ESCURECIMENTO_MODELO = 0.68


def analisar_foto(pos_srgb: np.ndarray) -> dict:
    """
    Mede o que interessa de uma foto, SEM chamar nenhum modelo.

    Devolve os números que alimentam a dica enviada à IA e o controle de brilho
    da tela. Tudo calculado aqui, em milissegundos e de graça.

    Por que assim: eu cogitei mandar a foto para um modelo de visão devolver os
    parâmetros por foto. Medi antes e a resposta foi clara -- os ajustes
    necessários são SISTEMÁTICOS (as quatro fotos pediam exatamente o mesmo
    1,47x), não específicos de cada foto. Duas chamadas para chegar a uma
    constante que se calcula localmente seria complexidade sem ganho.
    """
    a = post._srgb(pos_srgb)
    lum = post.luminancia(a)

    med = float(np.median(lum))
    p05 = float(np.percentile(lum, 5))
    p95 = float(np.percentile(lum, 95))
    escuro = float((lum < 0.05).mean())
    claro = float((lum >= 0.95).mean())

    m = (lum > np.percentile(lum, 30)) & (lum < np.percentile(lum, 70))
    cor = np.median(a[m], axis=0) if m.any() else np.median(a.reshape(-1, 3), axis=0)
    r, g, b = (float(x) for x in cor)

    # Quanto clarear na ENTRADA, se o usuário quiser forçar. O padrão é 1.0:
    # a dica enviada no prompt já pede o resultado na faixa certa, e clarear a
    # entrada E pedir a faixa seria duas correções para o mesmo problema.
    brilho_sugerido = float(np.clip(1.0 / FATOR_ESCURECIMENTO_MODELO, 1.0, 2.0))

    return {
        "p50": med,
        "p05": p05,
        "p95": p95,
        "escuro": escuro,
        "claro": claro,
        "G_R": g / max(r, 1e-9),
        "R_B": r / max(b, 1e-9),
        "brilho_sugerido": brilho_sugerido,
    }


def dica_para_a_ia(m: dict) -> str:
    """
    Monta o texto com os números medidos, para enviar JUNTO com a imagem.

    A ideia: o modelo não tem como saber qual é a exposição correta nem se a
    imagem tem cast de cor -- ele só vê o que recebe. Estes números são
    informação que ele não tem, e custam zero (é texto no prompt).

    A instrução de exposição é MANDATÓRIA, não sugestiva. Medido, o modelo
    devolve com mediana em ~68% da que recebe: se eu só disser "não escureça",
    ele escurece do mesmo jeito. Então digo o número que quero na saída.

    Escrito em inglês porque o prompt principal também está -- misturar idiomas
    num prompt de imagem tende a confundir o modelo.
    """
    alvo_min, alvo_max = 0.50, 0.62
    partes = [
        f"MEASURED DATA for this specific image (use it, it is not a guess): "
        f"median luminance is {m['p50']:.2f} right now."
    ]

    # Exposição, com número de saída. A referência é o próprio positivo: ele já
    # está correto, então a saída tem de ficar na mesma faixa.
    partes.append(
        f"Exposure requirement: the restored result MUST have its median "
        f"luminance between {alvo_min:.2f} and {alvo_max:.2f}. The input is "
        f"already correctly exposed, so do NOT darken it -- a darker result is "
        f"a defect, not a style."
    )

    # Sombras
    if m["escuro"] > 0.18:
        partes.append(
            f"Shadows: {m['escuro']*100:.0f}% of pixels are already near black. "
            f"Open them slightly and keep detail; do not crush them further."
        )

    # Altas luzes
    if m["claro"] > 0.20:
        partes.append(
            f"Highlights: {m['claro']*100:.0f}% of pixels are near white (the "
            f"film border). Leave them as they are."
        )

    # Cor -- uma instrução só, sem contradição.
    if m["G_R"] > 1.15:
        partes.append(
            f"Color cast: green measures {m['G_R']:.2f}x red in the midtones, a "
            f"cast from the aged film. Neutralise it toward realistic skin tones."
        )
    elif m["G_R"] < 0.90:
        partes.append(
            f"Color cast: red measures {1.0/max(m['G_R'],1e-6):.2f}x green in the "
            f"midtones. Balance toward neutral, realistic skin."
        )
    elif m["R_B"] < 1.05:
        partes.append(
            f"Color: red/blue is {m['R_B']:.2f}, so the image is nearly neutral "
            f"and slightly cool. Add a touch of warmth for realistic skin."
        )

    return " ".join(partes)


def prompt_efetivo(cfg: config.Config, medicao: dict | None = None) -> str:
    """
    Monta o prompt que será enviado, resolvendo instruções que se contradizem.

    O PROBLEMA QUE ISTO RESOLVE, e que custou caro:

    O prompt do .env termina com "preserve the original framing, aspect ratio and
    perspective exactly" e "DO NOT: crop, reframe, zoom or change the image
    dimensions". Ao mesmo tempo, o positivo digitalizado traz a borda do filme
    com os furinhos.

    Resultado medido: a IA obedecia -- mantinha o enquadramento exato, inclusive
    os furinhos -- e a foto restaurada saía com a moldura do negativo. Ela não
    estava inventando a borda; estava PRESERVANDO, como foi mandado.

    Então não basta acrescentar "remova os furinhos": é preciso tirar a instrução
    que manda manter tudo. Aqui a regra de não cortar passa a valer para o
    CONTEÚDO da fotografia, e a borda do filme é explicitamente descartável.

    Ordem de composição:

        1. prompt do .env (com a linha de "não cortar" ajustada)
        2. instrução sobre a borda do filme
        3. números medidos desta foto, se habilitado
    """
    texto = cfg.prompt

    if getattr(cfg, "limpar_borda_no_prompt", True):
        # Ajusta a linha que proíbe cortar, em vez de deixar a contradição.
        texto = texto.replace(
            "- crop, reframe, zoom or change the image dimensions",
            "- crop, reframe, zoom or change the image dimensions OF THE "
            "PHOTOGRAPH ITSELF (only the film border may be removed)",
        )
        texto += (
            "\n\nThe image may include the film border, the sprocket holes "
            "(the black rectangles along the edges) and a sliver of the "
            "neighbouring frame. REMOVE all of that: output only the "
            "photograph itself, cropped to its edges. Do not draw any border, "
            "frame, sprocket holes or film edge -- not even a thin one. The "
            "photograph's own content must fill the frame edge to edge."
        )

    if medicao is not None and getattr(cfg, "dica_por_foto", True):
        dica = dica_para_a_ia(medicao)
        if dica:
            texto = f"{texto}\n\n{dica}"

    return texto


def _chave_do_provedor(cfg: config.Config) -> str:
    """
    Devolve a chave de API do provedor configurado.

    Fonte: o `.env` (é onde o usuário configura, pela tela ou à mão). A
    variável de ambiente serve de reserva, para quem preferir não guardar a
    chave em arquivo.

    Esta função existe porque o `api.Restauracao` só olha variável de ambiente.
    Sem passar a chave explicitamente, a restauração falhava com "Falta a chave
    de API" mesmo com a chave corretamente preenchida no `.env` -- um erro
    confuso, porque a tela mostrava "Chave de API configurada ✓".
    """
    do_env = {
        "openrouter": cfg.openrouter_api_key,
        "gemini": cfg.gemini_api_key,
        "openai": getattr(cfg, "openai_api_key", ""),
    }.get(cfg.provedor, "")

    if do_env and do_env.strip():
        return do_env.strip()

    import os
    for nome in {
        "openrouter": ("OPENROUTER_API_KEY",),
        "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "openai": ("OPENAI_API_KEY",),
    }.get(cfg.provedor, ()):
        v = os.environ.get(nome)
        if v and v.strip():
            return v.strip()

    raise api.RestaurarErro(
        f"Falta a chave de API do {cfg.provedor} no arquivo .env "
        f"(campo {'openrouter_api_key' if cfg.provedor == 'openrouter' else 'gemini_api_key'}). "
        f"Preencha pela engrenagem ou edite o .env."
    )


def _curva_fn(cfg: config.Config):
    """Monta a função de curva de exibição, ou None se desativada."""
    if not cfg.usar_curva:
        return None

    def f(x, alvo=cfg.curva_alvo, g=cfg.curva_gamma, p=cfg.curva_preto):
        return curva.aplicar(x, gamma=(g if g > 0 else None), alvo=alvo, preto=p)

    return f


# Caracteres proibidos em nome de arquivo no Windows.
_PROIBIDOS = set('<>:"/\\|?*') | {chr(c) for c in range(32)}


def limpar_prefixo(prefixo: str) -> str:
    """
    Deixa o prefixo utilizável como nome de arquivo.

    O usuário vai digitar coisas como "filme1-tira1" ou "Filme 1 - Tira 2". Aqui
    tiramos espaços das pontas, trocamos espaço por hífen, removemos caractere
    proibido pelo Windows e juntamos underscores repetidos. Assim o nome final
    fica previsível, sem surpresa de o Windows recusar.
    """
    p = (prefixo or "").strip()
    for ruim in _PROIBIDOS:
        p = p.replace(ruim, "")
    p = p.replace(" ", "-")
    while "__" in p:
        p = p.replace("__", "_")
    return p.strip("-_.")


def caminho_renomeados(cfg: config.Config) -> Path:
    """
    Registro das fotos já renomeadas.

    Fica ao lado do registro de falhas, pela mesma razão. Guardar isto é o que
    permite a aba mostrar só o que AINDA não foi documentado: o nome do arquivo
    não diz se já recebeu etiqueta (o nome original também tem underscores).
    """
    return Path(cfg.pasta_positivo).parent / "_renomeados.json"


def ler_renomeados(cfg: config.Config) -> list[dict]:
    f = caminho_renomeados(cfg)
    if not f.is_file():
        return []
    try:
        dados = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [d for d in dados if isinstance(d, dict) and d.get("para")] \
        if isinstance(dados, list) else []


def _gravar_renomeados(cfg: config.Config, lista: list[dict]) -> None:
    f = caminho_renomeados(cfg)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(lista, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(f)
    except OSError:
        pass


def listar_para_renomear(cfg: config.Config) -> dict:
    """
    Lista os negativos que ainda não receberam prefixo.

    "Ainda não renomeado" é decidido pelo REGISTRO, não pelo formato do nome: o
    nome original já tem underscores (`20261012_133746`), então tentar adivinhar
    pelo padrão daria erro.

    Mostra também se a foto já tem positivo e restaurada, porque renomear move
    esses arquivos junto (o programa liga os três pelo nome-base).
    """
    origem = Path(cfg.pasta_origem)
    positivo = Path(cfg.pasta_positivo)
    restaurada = Path(cfg.pasta_restaurada)

    feitos = {d.get("para") for d in ler_renomeados(cfg)}

    com_positivo = set()
    if positivo.is_dir():
        for f in positivo.glob("*_positivo.png"):
            com_positivo.add(f.name.replace("_positivo.png", ""))
    com_restaurada = set()
    if restaurada.is_dir():
        for f in restaurada.glob("*_restaurado.png"):
            com_restaurada.add(f.name.replace("_restaurado.png", ""))

    itens = []
    if origem.is_dir():
        por_nome: dict[str, list[Path]] = {}
        for f in origem.iterdir():
            if f.is_file():
                por_nome.setdefault(f.stem, []).append(f)
        for nome, arquivos in sorted(por_nome.items()):
            if nome in feitos:
                continue
            itens.append({
                "nome": nome,
                "arquivos": sorted(a.name for a in arquivos),
                "extensoes": sorted({a.suffix.lower() for a in arquivos}),
                "tem_positivo": nome in com_positivo,
                "tem_restaurado": nome in com_restaurada,
            })

    return {
        "total": len(itens),
        "itens": itens,
        "origem": str(origem),
        "renomeados": len(feitos),
    }


def renomear_fotos(cfg: config.Config, nomes: list[str],
                   prefixo: str) -> dict:
    """
    Acrescenta um prefixo ao nome das fotos escolhidas.

    Renomeia TUDO o que pertence à mesma foto: os arquivos da origem (DNG e JPG)
    e, se existirem, o positivo e a restaurada. O programa liga os três pelo
    nome-base -- renomear só o negativo faria a foto "perder" o positivo já
    convertido.

    O prefixo entra na frente, separado por underscore:

        20261012_133746.dng  ->  filme1-tira1_20261012_133746.dng

    NUNCA sobrescreve: se o destino já existir, aquela foto falha com mensagem
    clara e as outras continuam. Perder arquivo por colisão de nome seria
    irreversível.

    Devolve {"ok", "falhas", "resultados"} no mesmo formato da restauração.
    """
    p = limpar_prefixo(prefixo)
    if not p:
        raise ValueError("informe um prefixo com pelo menos uma letra ou número")
    if len(p) > 60:
        raise ValueError("prefixo longo demais (máximo 60 caracteres)")
    if not nomes:
        raise ValueError("nenhuma foto selecionada")

    origem = Path(cfg.pasta_origem)
    positivo = Path(cfg.pasta_positivo)
    restaurada = Path(cfg.pasta_restaurada)

    resultados = []
    registro = ler_renomeados(cfg)
    feitos = {d.get("para") for d in registro}

    for nome in nomes:
        tentativas: list[tuple[Path, Path]] = []

        # 1) arquivos da origem
        for f in sorted(origem.glob(f"{nome}.*")):
            if f.is_file():
                tentativas.append((f, f.with_name(f"{p}_{f.name}")))
        # 2) positivo e restaurada
        for pasta, sufixo in ((positivo, "_positivo.png"),
                              (restaurada, "_restaurado.png")):
            f = pasta / f"{nome}{sufixo}"
            if f.is_file():
                tentativas.append((f, pasta / f"{p}_{nome}{sufixo}"))

        if not tentativas:
            resultados.append({"nome": nome, "ok": False,
                               "msg": "arquivo não encontrado"})
            continue

        # Confere TODOS os destinos antes de mover qualquer um: assim uma
        # colisão no meio não deixa a foto metade renomeada.
        colisoes = [d.name for _, d in tentativas if d.exists()]
        if colisoes:
            resultados.append({
                "nome": nome, "ok": False,
                "msg": f"já existe: {', '.join(colisoes)}",
            })
            continue

        try:
            for de, para in tentativas:
                de.rename(para)
        except OSError as e:
            resultados.append({"nome": nome, "ok": False,
                               "msg": f"{type(e).__name__}: {e.strerror or e}"})
            continue

        novo = f"{p}_{nome}"
        registro.append({
            "de": nome,
            "para": novo,
            "prefixo": p,
            "arquivos": [d.name for _, d in tentativas],
            "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        feitos.add(novo)
        resultados.append({"nome": nome, "ok": True, "novo": novo,
                           "msg": f"{len(tentativas)} arquivo(s)"})

    _gravar_renomeados(cfg, registro)

    ok = sum(1 for r in resultados if r["ok"])
    return {"total": len(nomes), "ok": ok, "falhas": len(nomes) - ok,
            "prefixo": p, "resultados": resultados}


def caminho_falhas_restauro(cfg: config.Config) -> Path:
    """
    Registro das falhas de RESTAURAÇÃO (distinto do de conversão).

    Fica no mesmo lugar (`saida/_falhas_restauracao.json`), pela mesma razão: não
    se mistura com as imagens e sobrevive se a pasta de restauradas mudar.
    """
    return Path(cfg.pasta_positivo).parent / "_falhas_restauracao.json"


def ler_falhas_restauro(cfg: config.Config) -> list[dict]:
    """Lê o registro de falhas de restauração."""
    f = caminho_falhas_restauro(cfg)
    if not f.is_file():
        return []
    try:
        dados = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(dados, list):
        return []
    return [d for d in dados if isinstance(d, dict) and d.get("nome")]


def _gravar_falhas_restauro(cfg: config.Config, lista: list[dict]) -> None:
    f = caminho_falhas_restauro(cfg)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(lista, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(f)
    except OSError:
        pass


def registrar_falha_restauro(cfg: config.Config, nome: str, motivo: str,
                             detalhe: str = "", mascara_fraca: bool = False,
                             r_b: float | None = None) -> None:
    """
    Anota que a restauração desta foto não foi feita, e por quê.

    Guarda `mascara_fraca` e `r_b` separadamente porque esses dois casos têm
    tratamento próprio na tela: a máscara fraca não é defeito do programa, é
    negativo ruim -- e o usuário pode escolher tentar mesmo assim (é pago).
    """
    lista = [d for d in ler_falhas_restauro(cfg) if d.get("nome") != nome]
    lista.append({
        "nome": nome,
        "motivo": motivo,
        "detalhe": detalhe,
        "mascara_fraca": bool(mascara_fraca),
        "r_b": r_b,
        "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    lista.sort(key=lambda d: d.get("nome", ""))
    _gravar_falhas_restauro(cfg, lista)


def limpar_falha_restauro(cfg: config.Config, nome: str) -> None:
    """Remove a foto do registro (quando ela é restaurada com sucesso)."""
    lista = ler_falhas_restauro(cfg)
    nova = [d for d in lista if d.get("nome") != nome]
    if len(nova) != len(lista):
        _gravar_falhas_restauro(cfg, nova)


def falhas_restauro(cfg: config.Config) -> dict:
    """
    Lista o que falhou na restauração, para a aba própria.

    Diferença para a aba de conversão: aqui NÃO se varre "positivo sem
    restaurada", porque isso listaria toda foto ainda não restaurada -- que é o
    estado normal, não uma falha. Só aparece o que o programa anotou como falha.

    Uma foto que já tem restaurada sai da lista: o erro foi superado.
    """
    restaurado_dir = Path(cfg.pasta_restaurada)
    prontas: set[str] = set()
    if restaurado_dir.is_dir():
        for f in restaurado_dir.glob("*_restaurado.png"):
            prontas.add(f.name.replace("_restaurado.png", ""))

    lista = []
    for d in ler_falhas_restauro(cfg):
        if d["nome"] in prontas:
            continue                    # já foi restaurada: falha superada
        d = dict(d)
        d["tem_positivo"] = (Path(cfg.pasta_positivo)
                             / f"{d['nome']}_positivo.png").is_file()
        lista.append(d)

    return {
        "total": len(lista),
        "falhas": lista,
        "limite_mascara": LIMITE_MASCARA,
        "restaurada": str(restaurado_dir),
    }


def caminho_falhas(cfg: config.Config) -> Path:
    """
    Onde fica o registro das falhas de conversão.

    Fica na pasta PAI da saída (`saida/_falhas_conversao.json`), não dentro da
    pasta de positivos: assim não se mistura com as imagens e sobrevive se a
    pasta de positivos for trocada no `.env`.

    Por que precisou de persistência: as falhas existiam só na memória do
    trabalho. Quando o trabalho terminava, o resumo ficava no objeto e a
    informação se perdia -- o usuário via "1 falha de 26" e não tinha como saber
    QUAL foto nem por quê.
    """
    return Path(cfg.pasta_positivo).parent / "_falhas_conversao.json"


def ler_falhas(cfg: config.Config) -> list[dict]:
    """Lê o registro de falhas. Devolve [] se não existir ou estiver corrompido."""
    f = caminho_falhas(cfg)
    if not f.is_file():
        return []
    try:
        dados = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(dados, list):
        return []
    return [d for d in dados if isinstance(d, dict) and d.get("nome")]


def _gravar_falhas(cfg: config.Config, lista: list[dict]) -> None:
    f = caminho_falhas(cfg)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(lista, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(f)                      # troca atômica
    except OSError:
        pass                                # não perder a conversão por isso


def registrar_falha(cfg: config.Config, nome: str, origem: str,
                    motivo: str) -> None:
    """
    Registra (ou atualiza) a falha de uma foto.

    Guarita o motivo, o arquivo de origem e o tamanho -- o tamanho ajuda a
    identificar arquivo truncado / não sincronizado da nuvem.
    """
    lista = [d for d in ler_falhas(cfg) if d.get("nome") != nome]
    tamanho = 0
    try:
        tamanho = Path(origem).stat().st_size
    except OSError:
        pass
    lista.append({
        "nome": nome,
        "origem": origem,
        "arquivo": Path(origem).name if origem else "",
        "tamanho": tamanho,
        "motivo": motivo,
        "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    lista.sort(key=lambda d: d.get("nome", ""))
    _gravar_falhas(cfg, lista)


def limpar_falha(cfg: config.Config, nome: str) -> None:
    """Remove a foto do registro (quando ela converte com sucesso depois)."""
    lista = ler_falhas(cfg)
    nova = [d for d in lista if d.get("nome") != nome]
    if len(nova) != len(lista):
        _gravar_falhas(cfg, nova)


def falhas_e_pendentes(cfg: config.Config,
                       progresso: Callable[[dict], None] | None = None
                       ) -> dict:
    """
    Lista o que está com problema na conversão, para a aba de falhas.

    Junta DUAS origens, porque uma sem a outra esconde casos:

    1. o registro persistido (falhas que o programa viu e anotou o motivo);
    2. uma varredura ao vivo da pasta de origem: negativos que NÃO têm positivo.
       Isto pega falhas anteriores a este registro existir, e também conversões
       interrompidas.

    `sem_motivo` marca as que vieram só da varredura, para a tela não inventar
    uma explicação que não foi medida.
    """
    registradas = {d["nome"]: d for d in ler_falhas(cfg)}

    achadas: list[dict] = []
    origem = Path(cfg.pasta_origem)
    positivo = Path(cfg.pasta_positivo)

    # Definido AQUI, fora do `if`, porque é usado depois para decidir se uma
    # falha registrada ainda faz sentido mostrar.
    com_positivo: set[str] = set()
    if positivo.is_dir():
        for f in positivo.glob("*_positivo.png"):
            com_positivo.add(f.name.replace("_positivo.png", ""))

    if origem.is_dir():
        nomes_origem: dict[str, list[Path]] = {}
        for f in origem.iterdir():
            if f.is_file():
                nomes_origem.setdefault(f.stem, []).append(f)

        if progresso:
            progresso({"msg": f"{len(nomes_origem)} negativos, "
                              f"{len(com_positivo)} com positivo"})

        for nome, arquivos in sorted(nomes_origem.items()):
            if nome in com_positivo:
                continue
            reg = registradas.get(nome)
            if reg is not None:
                achadas.append(dict(reg, sem_motivo=False))
                continue
            raws = [a for a in arquivos if a.suffix.lower() in EXT_RAW]
            alvo = raws[0] if raws else arquivos[0]
            try:
                tamanho = alvo.stat().st_size
            except OSError:
                tamanho = 0
            achadas.append({
                "nome": nome,
                "origem": str(alvo),
                "arquivo": alvo.name,
                "tamanho": tamanho,
                "motivo": "",
                "quando": "",
                "sem_motivo": True,
            })

    # Registradas que já não estão na origem nem têm positivo: mostra também,
    # para o usuário saber que existiram.
    nomes_achados = {d["nome"] for d in achadas}
    for nome, reg in registradas.items():
        if nome in nomes_achados or nome in com_positivo:
            continue
        achadas.append(dict(reg, sem_motivo=False))

    return {
        "total": len(achadas),
        "falhas": achadas,
        "origem": str(origem),
        "positivo": str(positivo),
    }


def diagnosticar_negativo(cfg: config.Config, nome: str) -> dict:
    """
    Tenta converter UM negativo e registra o motivo da falha (ou do sucesso).

    Serve para a aba de falhas dizer POR QUE a foto falhou, em vez de só listar
    o nome. A varredura ao vivo sabe QUEM não tem positivo, mas não sabe o
    motivo sem tentar abrir -- e abrir é caro (um DNG de 14 MB leva segundos),
    então isto é sob demanda, não na abertura da aba.

    Devolve {"nome", "ok", "motivo"}.
    """
    origem_dir = Path(cfg.pasta_origem)
    candidatos = sorted(origem_dir.glob(f"{nome}.*"))
    raws = [a for a in candidatos if a.suffix.lower() in EXT_RAW]
    alvo = raws[0] if raws else (candidatos[0] if candidatos else None)

    if alvo is None:
        motivo = "arquivo de origem não encontrado"
        registrar_falha(cfg, nome, "", motivo)
        return {"nome": nome, "ok": False, "motivo": motivo}

    try:
        res = pipeline.desenvolver(
            alvo,
            pipeline.Parametros(
                filme=cfg.filme,
                saturacao=cfg.saturacao,
                nitidez=cfg.nitidez,
                balanco_forca=cfg.balanco,
            ),
            manter_etapas=False,
        )
    except Exception as e:  # noqa: BLE001
        motivo = f"{type(e).__name__}: {str(e)[:300]}"
        registrar_falha(cfg, nome, str(alvo), motivo)
        return {"nome": nome, "ok": False, "motivo": motivo}

    # Abriu: então a falha anterior não era de leitura (foi escrita ou
    # interrupção). Grava o positivo agora, para a foto sair da lista.
    try:
        destino = Path(cfg.pasta_positivo) / nome_positivo(nome)
        destino.parent.mkdir(parents=True, exist_ok=True)
        pipeline.salvar(res.positivo, destino, linear=True, curva=None)
        limpar_falha(cfg, nome)
        return {"nome": nome, "ok": True,
                "motivo": "abriu e converteu agora -- foi gravada"}
    except Exception as e:  # noqa: BLE001
        motivo = f"abriu, mas falhou ao gravar: {type(e).__name__}: {str(e)[:200]}"
        registrar_falha(cfg, nome, str(alvo), motivo)
        return {"nome": nome, "ok": False, "motivo": motivo}


def converter(
    cfg: config.Config,
    nomes: list[str] | None = None,
    progresso: Callable[[dict], None] | None = None,
    parar: threading.Event | None = None,
) -> dict:
    """
    Gera os positivos que faltam.

    nomes=None converte tudo que falta. `progresso` é chamado a cada arquivo
    com {feitos, total, nome, etapa, ok, msg}.

    Não levanta exceção se a pasta de saída for inacessível: relata o erro em
    cada item. Antes, um `mkdir` sem proteção derrubava a função inteira -- e
    o usuário via um erro de permissão cru em vez de uma explicação.
    """
    est = estado(cfg)
    alvos = [
        i for i in est["itens"]
        if not i["tem_positivo"] and (nomes is None or i["nome"] in nomes)
    ]
    total = len(alvos)
    positivo_dir = Path(cfg.pasta_positivo)

    try:
        positivo_dir.mkdir(parents=True, exist_ok=True)
        gravavel = True
    except OSError:
        gravavel = False

    if gravavel:
        gravavel, motivo_escrita = testar_escrita(positivo_dir)
    else:
        motivo_escrita = testar_escrita(positivo_dir)[1]

    # Guarda se a pasta CONFIGURADA gravava, para poder avisar quando os
    # arquivos forem para outro lugar.
    gravavel_original = gravavel
    pasta_original = positivo_dir

    if not gravavel:
        # A pasta configurada não grava. Em vez de só falhar, procuramos uma
        # que grava -- e avisamos no resultado, para o usuário saber que os
        # arquivos foram para outro lugar.
        alternativa = config.pasta_local_gravavel()
        if str(alternativa) != str(positivo_dir.parent):
            positivo_dir = alternativa / "positivo"
            try:
                positivo_dir.mkdir(parents=True, exist_ok=True)
                ok2, _ = testar_escrita(positivo_dir)
            except OSError:
                ok2 = False
            if ok2:
                gravavel = True
                motivo_escrita = (
                    f"a pasta configurada ({pasta_original}) não aceitava "
                    f"escrita; os positivos foram gravados em {positivo_dir}"
                )

    # Onde guardar os DNG reconvertidos. Fica numa pasta configurável (por
    # padrão, a temporária do sistema): o Adobe regrava sem compressão, então
    # cada arquivo ocupa ~43 MB contra os ~14 MB do original.
    cache_adobe = config.pasta_cache_adobe(cfg) if cfg.usar_adobe else None
    usar_adobe = (cfg.usar_adobe and cache_adobe is not None
                  and adobe.disponivel(cfg.adobe_exe or None))

    cur = _curva_fn(cfg)
    resultados = []
    t0 = time.time()

    for i, alvo in enumerate(alvos, 1):
        if parar is not None and parar.is_set():
            break
        nome = alvo["nome"]

        # Se a pasta de saída não é gravável, não adianta processar: registra o
        # motivo real (e a orientação) em vez de estourar uma exceção crua.
        if not gravavel:
            resultados.append({"nome": nome, "ok": False, "msg": motivo_escrita})
            # O arquivo de origem ainda não foi resolvido neste ponto do laço,
            # então o registro fica sem o caminho -- o motivo é o que importa.
            registrar_falha(cfg, nome, "", motivo_escrita)
            if progresso:
                progresso({"feitos": i, "total": total, "nome": nome,
                           "etapa": "erro", "ok": False, "msg": motivo_escrita})
            continue

        fonte = Path(cfg.pasta_origem)
        # Reencontra o arquivo de origem (o DNG tem prioridade).
        candidatos = sorted(fonte.glob(f"{nome}.*"))
        raw = [c for c in candidatos if c.suffix.lower() in EXT_RAW]
        origem = raw[0] if raw else (candidatos[0] if candidatos else None)

        if progresso:
            progresso({"feitos": i - 1, "total": total, "nome": nome,
                       "etapa": "abrindo", "ok": None, "msg": ""})

        if origem is None:
            resultados.append({"nome": nome, "ok": False, "msg": "origem não encontrada"})
            registrar_falha(cfg, nome, "", "origem não encontrada")
            if progresso:
                progresso({"feitos": i, "total": total, "nome": nome,
                           "etapa": "erro", "ok": False, "msg": "origem não encontrada"})
            continue

        try:
            via_adobe = False
            if usar_adobe and origem.suffix.lower() in EXT_RAW:
                if progresso:
                    progresso({"feitos": i - 1, "total": total, "nome": nome,
                               "etapa": "adobe", "ok": None, "msg": ""})
                try:
                    gerados, _ = adobe.converter([origem], cache_adobe,
                                                exe=cfg.adobe_exe or None)
                except Exception:  # noqa: BLE001
                    gerados = []
                if gerados:
                    origem = gerados[0]
                    via_adobe = True

            if progresso:
                progresso({"feitos": i - 1, "total": total, "nome": nome,
                           "etapa": "invertendo", "ok": None, "msg": ""})

            res = pipeline.desenvolver(
                origem,
                pipeline.Parametros(
                    filme=cfg.filme,
                    saturacao=cfg.saturacao,
                    nitidez=cfg.nitidez,
                    balanco_forca=cfg.balanco,
                ),
                manter_etapas=False,
            )
            destino = positivo_dir / nome_positivo(nome)
            pipeline.salvar(res.positivo, destino, linear=True, curva=cur)

            base = res.base_filme
            rb = float(base[0] / max(base[2], 1e-9)) if base is not None else 0.0
            # ACUMULA os avisos numa lista. Antes, cada aviso sobrescrevia o
            # anterior, então quando havia mais de um o usuário só via o
            # último -- e o aviso de "caiu para outra pasta" sumia.
            avisos = []
            if not gravavel_original:
                avisos.append(f"pasta configurada sem escrita — gravado em {positivo_dir}")
            if via_adobe:
                avisos.append("via Adobe")
            if rb < LIMITE_MASCARA:
                avisos.append("máscara fraca (R/B=%.2f)" % rb)
            msg = " | ".join(avisos)

            resultados.append({"nome": nome, "ok": True, "msg": msg})
            # Deu certo: sai do registro de falhas (pode ter sido corrigida).
            limpar_falha(cfg, nome)
            if progresso:
                progresso({"feitos": i, "total": total, "nome": nome,
                           "etapa": "pronto", "ok": True, "msg": msg})
        except Exception as e:  # noqa: BLE001
            motivo = f"{type(e).__name__}: {str(e)[:140]}"
            resultados.append({"nome": nome, "ok": False, "msg": motivo})
            registrar_falha(cfg, nome, str(origem), motivo)
            if progresso:
                progresso({"feitos": i, "total": total, "nome": nome,
                           "etapa": "erro", "ok": False, "msg": motivo})

    ok = sum(1 for r in resultados if r["ok"])
    return {
        "total": total,
        "ok": ok,
        "falhas": total - ok,
        "segundos": round(time.time() - t0, 1),
        "resultados": resultados,
    }


# ---------------------------------------------------------------------------
# Restauração por IA
# ---------------------------------------------------------------------------
def custo_estimado(cfg: config.Config, quantos: int) -> tuple[float, str]:
    """Custo estimado em USD e a origem do dado de preço."""
    if cfg.provedor != "openrouter":
        tabela = {"google/gemini-2.5-flash-image": 0.039, "openai/gpt-image-1-mini": 0.010}
        return tabela.get(cfg.modelo, 0.0) * quantos, "tabela local"
    try:
        for mid, preco, _ in api.listar_modelos_de_imagem():
            if mid == cfg.modelo:
                return float(preco) * api.TOKENS_POR_IMAGEM * quantos, "OpenRouter"
    except Exception:  # noqa: BLE001
        pass
    tabela = {"google/gemini-2.5-flash-image": 0.039,
              "google/gemini-nano-banana-2.1": 0.039,
              "openai/gpt-5-image-mini": 0.010}
    return tabela.get(cfg.modelo, 0.0) * quantos, "tabela local (consulta falhou)"


def restaurar(
    cfg: config.Config,
    nomes: list[str],
    progresso: Callable[[dict], None] | None = None,
    parar: threading.Event | None = None,
    forcar: bool = False,
    brilho: float | None = None,
) -> dict:
    """
    Manda os positivos escolhidos para a IA.

    `nomes` são os nomes-base (sem sufixo). Só processa quem tem positivo.
    forcar=True envia mesmo com máscara fraca.
    `brilho` clareia a imagem enviada (multiplicador; None = usa o do .env).
    """
    positivo_dir = Path(cfg.pasta_positivo)
    restaurado_dir = Path(cfg.pasta_restaurada)
    restaurado_dir.mkdir(parents=True, exist_ok=True)

    cur = _curva_fn(cfg)
    total = len(nomes)
    resultados = []
    gasto = 0.0
    t0 = time.time()

    for i, nome in enumerate(nomes, 1):
        if parar is not None and parar.is_set():
            break
        arq_pos = positivo_dir / nome_positivo(nome)
        if not arq_pos.exists():
            resultados.append({"nome": nome, "ok": False, "msg": "sem positivo"})
            if progresso:
                progresso({"feitos": i, "total": total, "nome": nome,
                           "etapa": "erro", "ok": False, "msg": "sem positivo"})
            continue

        if progresso:
            progresso({"feitos": i - 1, "total": total, "nome": nome,
                       "etapa": "enviando", "ok": None, "msg": ""})

        try:
            # LÊ EM sRGB, e isto é essencial.
            #
            # O arquivo do positivo está em sRGB (foi salvo assim). Usar
            # `pipeline.carregar` aqui convertia para luz linear, derrubando a
            # mediana de 0,610 para 0,339 -- e era ISSO que ia para a IA.
            # Ela devolvia 0,038 porque RECEBIA escuro; não era o modelo que
            # escurecia.
            #
            # Medido: o redimensionamento preserva a mediana (0,6096 -> 0,6096),
            # então a redução nunca foi o problema. Era só o espaço de cor.
            lin = pipeline.carregar_srgb(arq_pos)

            # A máscara tem de ser medida no NEGATIVO ORIGINAL, não no positivo.
            #
            # `detectar_base_do_filme` procura a máscara laranja do negativo (a
            # parte do filme que não foi exposta). Num positivo já invertido
            # essa máscara virou PRETO, e a função devolve lixo -- medi R=1.00
            # exato em todas as 28 fotos. Como o limite é R/B >= 2,5, TODA
            # restauração era pulada, sem exceção.
            rb, motivo_mascara = _mascara_do_negativo(cfg, nome)

            if rb is not None and rb < LIMITE_MASCARA and not forcar:
                motivo = f"máscara fraca (R/B={rb:.2f})"
                resultados.append({
                    "nome": nome, "ok": False, "pulado": True,
                    "mascara_fraca": True, "r_b": rb,
                    "msg": f"pulado: {motivo}. {motivo_mascara}",
                })
                registrar_falha_restauro(cfg, nome, motivo, motivo_mascara,
                                         mascara_fraca=True, r_b=rb)
                if progresso:
                    progresso({"feitos": i, "total": total, "nome": nome,
                               "etapa": "pulado", "ok": False,
                               "msg": motivo})
                continue

            # Prepara o que vai para a IA.
            #
            # UMA chamada só. Já houve duas aqui (resíduo de uma edição), e o
            # efeito era recortar e reduzir duas vezes -- trabalho dobrado e
            # risco de o segundo recorte agir sobre uma imagem já reduzida.
            if progresso:
                progresso({"feitos": i - 1, "total": total, "nome": nome,
                           "etapa": "preparando", "ok": None,
                           "msg": "lendo e reduzindo o positivo"})
            sRGB = preparar_envio(lin, cfg, brilho=brilho)
            retangulo = getattr(preparar_envio, "ultimo_recorte", None)
            if retangulo is not None and progresso:
                progresso({"feitos": i - 1, "total": total, "nome": nome,
                           "etapa": "preparando", "ok": None,
                           "msg": f"borda recortada → "
                                  f"{sRGB.shape[1]}x{sRGB.shape[0]}"})

            # Dica com os números medidos, montada AQUI e enviada junto com a
            # imagem. O modelo só vê o que recebe; estes números são informação
            # que ele não tem, e custam zero.
            medicao = analisar_foto(sRGB)
            prompt_final = prompt_efetivo(cfg, medicao)
            if progresso:
                progresso({"feitos": i - 1, "total": total, "nome": nome,
                           "etapa": "preparando", "ok": None,
                           "msg": f"p50 do envio {medicao['p50']:.2f}, "
                                  f"com dica de {len(prompt_final) - len(cfg.prompt)} "
                                  f"caracteres"})

            if progresso:
                progresso({"feitos": i - 1, "total": total, "nome": nome,
                           "etapa": "enviando", "ok": None,
                           "msg": f"enviando {sRGB.shape[1]}x{sRGB.shape[0]} para a IA"})

            rest = api.Restauracao(
                provedor=cfg.provedor,
                modelo=cfg.modelo,
                prompt=prompt_final,
                # A chave tem de vir daqui. O api.Restauracao, sem isto, só
                # procura em variável de ambiente -- e falhava com "Falta a
                # chave de API" mesmo com a chave preenchida no .env, que é
                # onde o usuário a configura pela tela.
                api_key=_chave_do_provedor(cfg),
            )

            # A chamada da IA é o passo mais demorado (10 a 60 s). Marcamos o
            # início para a tela poder mostrar o tempo decorrido -- sem isso, o
            # usuário fica sem saber se está travado ou trabalhando.
            if progresso:
                progresso({"feitos": i - 1, "total": total, "nome": nome,
                           "etapa": "aguardando", "ok": None,
                           "msg": "a IA está processando", "marco": time.time()})

            resposta = rest.restaurar(sRGB)

            if progresso:
                progresso({"feitos": i - 1, "total": total, "nome": nome,
                           "etapa": "recebendo", "ok": None,
                           "msg": "resposta recebida, gravando"})

            # A resposta da IA JÁ está em sRGB (é uma imagem pronta).
            #
            # Aqui havia `core.normalizar(resposta, linear=False)`, que
            # DECODIFICA o gama -- o mesmo mal-entendido que deixava o envio
            # escuro. Consequência medida: a IA recebia com p50=0,5216 e o
            # arquivo gravado saía com 0,2627, metade do brilho.
            #
            # `para_float01` só cuida de escala e canais, sem tocar em gama.
            restaurado = core.para_float01(resposta)

            # A IA devolve o resultado mais escuro que o positivo. Medido em
            # três fotos: 0,234 a menos na mediana. Igualamos a mediana, o que
            # é visível na comparação lado a lado.
            if cfg.casar_exposicao:
                antes = float(np.median(post.luminancia(restaurado)))
                restaurado = post.casar_exposicao(sRGB, restaurado,
                                                  forca=cfg.exposicao_forca)
                depois = float(np.median(post.luminancia(restaurado)))
                if progresso:
                    progresso({"feitos": i - 1, "total": total, "nome": nome,
                               "etapa": "recebendo", "ok": None,
                               "msg": f"exposição ajustada "
                                      f"{antes:.2f} → {depois:.2f}"})

            destino = restaurado_dir / nome_restaurado(nome)
            pipeline.salvar(restaurado, destino, linear=False)

            unitario, _ = custo_estimado(cfg, 1)
            gasto += unitario
            resultados.append({
                "nome": nome, "ok": True,
                "msg": f"{restaurado.shape[1]}x{restaurado.shape[0]}",
            })
            # Deu certo: sai da aba de falhas de restauração.
            limpar_falha_restauro(cfg, nome)
            if progresso:
                progresso({"feitos": i, "total": total, "nome": nome,
                           "etapa": "pronto", "ok": True,
                           "msg": f"{restaurado.shape[1]}x{restaurado.shape[0]}"})
        except api.RestaurarErro as e:
            texto = str(e)[:200]
            resultados.append({"nome": nome, "ok": False, "msg": texto})
            # Falha de API (chave, rede, resposta sem imagem) também vai para a
            # aba, com botão de forçar -- é o caso de "tentar de novo".
            registrar_falha_restauro(cfg, nome, texto)
            if progresso:
                progresso({"feitos": i, "total": total, "nome": nome,
                           "etapa": "erro", "ok": False, "msg": texto})
        except Exception as e:  # noqa: BLE001
            texto = f"{type(e).__name__}: {str(e)[:140]}"
            resultados.append({"nome": nome, "ok": False, "msg": texto})
            registrar_falha_restauro(cfg, nome, texto)
            if progresso:
                progresso({"feitos": i, "total": total, "nome": nome,
                           "etapa": "erro", "ok": False, "msg": texto})

    ok = sum(1 for r in resultados if r["ok"])
    return {
        "total": total,
        "ok": ok,
        "falhas": total - ok,
        "custo": round(gasto, 4),
        "segundos": round(time.time() - t0, 1),
        "resultados": resultados,
    }


def _reduzir(lin, largura: int):
    """Reduz a imagem para envio (devolve uint8 sRGB)."""
    from . import render
    return render.ampliar(lin, largura=largura, ja_srgb=False)


def preparar_envio(lin: np.ndarray, cfg: config.Config,
                   brilho: float | None = None) -> np.ndarray:
    """
    Prepara a imagem que vai para a IA. Devolve sRGB [0,1].

    A ordem importa, e essa foi uma lição: DETECTAR O QUADRO ANTES DE REDUZIR.

    A detecção procura a borda do filme pelo gradiente quase zero (medido:
    0,00000 na borda contra 0,005 no quadro). Depois de reduzir a imagem, o
    redimensionamento suaviza a transição e o gradiente da borda deixa de ser
    zero -- a detecção passa a falhar. Enquanto detectei depois de reduzir, só
    uma das três fotos era recortada; detectando antes, todas as que têm borda
    detectável são.

    Ordem correta:

        positivo (sRGB) -> RECORTAR o quadro -> reduzir -> ENVIAR

    Os pixels vêm como estão no arquivo: não há curva nem balanço aplicados
    aqui. O positivo salvo já passou por isso quando foi convertido.

    `brilho` (opcional) usa curva de tom para clarear ou escurecer o envio. Ver
    `post.clarear_com_curva`.
    """
    from PIL import Image

    img = np.asarray(lin, dtype=np.float64)
    if img.dtype != np.float64 or img.max() > 1.001:
        img = img / 255.0

    # 1) Recorta a borda do filme, se pedido e se a detecção tiver certeza.
    recortado = None
    if getattr(cfg, "recortar_bordas", False):
        img, recortado = post.cortar_quadro(
            img, margem=getattr(cfg, "recorte_margem", 0.0))

    # 2) Clareia, se pedido. Antes de reduzir, para a curva trabalhar no dado
    #    cheio (o resultado é o mesmo, mas evita uma segunda interpolação).
    fator = float(brilho if brilho is not None
                  else getattr(cfg, "brilho_envio", 1.0))
    if abs(fator - 1.0) > 0.01:
        img = post.clarear_com_curva(img, fator)

    # 3) Reduz para o envio.
    if cfg.max_lado_envio and max(img.shape[:2]) > cfg.max_lado_envio:
        escala = cfg.max_lado_envio / max(img.shape[:2])
        largura = max(int(img.shape[1] * escala), 1)
        altura = max(int(round(img.shape[0] * escala)), 1)
        im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
        im = im.resize((largura, altura), Image.LANCZOS)
        img = np.asarray(im).astype(np.float64) / 255.0

    # Guarda o retângulo usado, para quem chamou poder informar.
    preparar_envio.ultimo_recorte = recortado
    return np.clip(img, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Thumbnail
# ---------------------------------------------------------------------------
def thumb(caminho: Path, largura: int = 320,
          recortar_borda: bool = False) -> bytes:
    """
    Gera um PNG reduzido, para a grade da interface.

    NÃO aplica curva, gama nem recorte: lê o arquivo e reduz. Isso é o correto,
    e foi verificado por medição:

        arquivo     mediana de luminância 0,6096
        miniatura   mediana de luminância 0,6052

    O `recortar_borda` existe, mas fica DESLIGADO por padrão. Cheguei a ligá-lo
    pensando que o preview "lavado" vinha da borda clara do filme; medindo, a
    miniatura dava 0,89 contra 0,52 do arquivo -- mas essa diferença era do
    ARQUIVO estar errado, não da miniatura. Eu havia reconvertido os positivos
    com `curva=None` em vez da curva de exibição, e o positivo saiu lavado.

    Com o arquivo correto, a miniatura é fiel. Recortar a borda aqui só deixaria
    a miniatura MAIS ESCURA que o arquivo (medido: 0,40 contra 0,61), criando o
    problema oposto.
    """
    import io

    from PIL import Image

    with Image.open(caminho) as im:
        if im.mode != "RGB":
            im = im.convert("RGB")

        if recortar_borda:
            a = np.asarray(im).astype(np.float64) / 255.0
            corte, retangulo = post.cortar_quadro(a)
            if retangulo is not None:
                im = Image.fromarray(
                    (np.clip(corte, 0, 1) * 255).astype(np.uint8))

        im.thumbnail((largura, largura), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def imagem_reduzida(caminho: Path, largura: int) -> bytes:
    """
    Reduz uma imagem para a largura pedida, preservando a proporção.

    Usado pela tela de comparação ao abrir SÓ a metade restaurada grande: o
    arquivo tem ~1472 px de largura, e ampliar para a tela toda com redução
    controlada dá um resultado melhor que deixar o navegador fazer isso -- e
    evita baixar mais bytes do que o necessário.
    """
    import io

    from PIL import Image

    largura = max(int(largura), 64)
    with Image.open(caminho) as im:
        if im.mode != "RGB":
            im = im.convert("RGB")
        if im.width > largura:
            altura = max(int(round(im.height * largura / im.width)), 1)
            im = im.resize((largura, altura), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _cortar_faixa(img, texto: str, altura: int | None = None):
    """
    Faixa com legenda no topo, para marcar cada lado da comparação.

    A altura é proporcional à imagem (2,5%, mínimo 40 px) para o texto
    continuar legível depois de reduzir a comparação para caber na tela --
    uma faixa fixa de 34 px virava um risco ilegível em imagens grandes.
    """
    from PIL import Image, ImageDraw

    if altura is None:
        altura = max(int(img.height * 0.025), 40) if img.height else 40

    faixa = Image.new("RGB", (img.width, altura), (18, 20, 26))
    d = ImageDraw.Draw(faixa)

    # Fonte proporcional à faixa. A padrão do Pillow é pequena e não escala,
    # então reduzimos o texto na marra quando não há fonte TrueType.
    tamanho = max(int(altura * 0.52), 12)
    fonte = None
    try:
        from PIL import ImageFont

        for nome in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
            try:
                fonte = ImageFont.truetype(nome, tamanho)
                break
            except OSError:
                continue
    except Exception:  # noqa: BLE001
        fonte = None

    if fonte is not None:
        d.text((int(altura * 0.35), int(altura * 0.22)), texto,
               fill=(230, 232, 236), font=fonte)
    else:
        # Sem TrueType: a fonte padrão do Pillow não tem tamanho variável,
        # então usamos ela e aumentamos a faixa para o texto caber.
        d.text((8, max((altura - 11) // 2, 2)), texto, fill=(230, 232, 236))

    saida = Image.new("RGB", (img.width, img.height + altura), (18, 20, 26))
    saida.paste(faixa, (0, 0))
    saida.paste(img, (0, altura))
    return saida


def _painel(im, rotulo: str, altura: int, largura: int, altura_faixa: int):
    """
    Redimensiona uma imagem para a altura pedida, centraliza numa caixa e
    acrescenta a faixa de legenda.

    A caixa tem sempre as MESMAS dimensões (largura x altura), com fundo escuro
    preenchendo o que sobra. É isso que garante que as duas metades de uma
    comparação fiquem na mesma escala.
    """
    from PIL import Image

    h = altura
    w = max(int(round(im.width * h / im.height)), 1)
    redim = im.resize((w, h), Image.LANCZOS)
    caixa = Image.new("RGB", (largura, h), (18, 20, 26))
    caixa.paste(redim, (max((largura - w) // 2, 0), 0))
    return _cortar_faixa(caixa, rotulo, altura=altura_faixa)


def _eh_vertical(largura_a: int, altura_a: int, largura_b: int, altura_b: int,
                 max_largura: int, max_altura: int = 1250) -> bool:
    """
    Decide se as duas metades ficam MELHOR lado a lado (horizontal) ou uma
    sobre a outra (vertical).

    Para foto de retrato (que é o caso aqui: 1868x4000), lado a lado dá uma
    imagem altíssima e estreita que só cabe na tela muito reduzida -- e aí nada
    é visível. Empilhadas, cada metade usa a largura toda.

    Compara a área útil nos dois arranjos, respeitando os limites de tela.
    """
    def area(w: int, h: int) -> float:
        escala = min(max_largura / w, max_altura / h, 1.0)
        return (w * escala) * (h * escala)

    # proporção das duas imagens (a do positivo serve de referência)
    prop = largura_a / max(altura_a, 1)
    h_alvo = 1000
    largura_caixa = max(int(h_alvo * prop), 1)
    faixa = max(int(h_alvo * 0.045), 48)

    horiz_w = largura_caixa * 2 + 8
    horiz_h = h_alvo + faixa
    vert_w = largura_caixa
    vert_h = (h_alvo + faixa) * 2 + 8

    return area(vert_w, vert_h) > area(horiz_w, horiz_h)


def calcular_layout(la: int, ha: int, lb: int, hb: int,
                    largura_max: int) -> tuple[int, int, int, float]:
    """
    Dimensões das duas metades lado a lado. Exposta para os testes conferirem os
    invariantes sem precisar adivinhar números.

    Devolve (altura, largura_a, largura_b, escala_final).
    """
    lim = max(largura_max, 400)
    altura_minima = 620

    for alvo_h in (1400, 1200, 1000, 900, 800, 700, 620):
        lw = max(int(round(la * alvo_h / ha)), 1)
        rw = max(int(round(lb * alvo_h / hb)), 1)
        total = lw + 8 + rw
        if total <= lim or alvo_h <= altura_minima:
            return alvo_h, lw, rw, min(1.0, lim / total)

    alvo_h = 620
    lw = max(int(round(la * alvo_h / ha)), 1)
    rw = max(int(round(lb * alvo_h / hb)), 1)
    total = lw + 8 + rw
    return alvo_h, lw, rw, min(1.0, lim / total)


def _layout_lado_a_lado(a, b, largura_max: int) -> tuple:
    """
    Calcula as dimensões das duas metades lado a lado, a partir das imagens.

    Duas decisões, e as duas vieram de reclamação do usuário:

    1. **Sempre lado a lado.** Para foto em pé, empilhar deixava a comparação
       vertical -- e comparar lado a lado é o que se quer, mesmo que cada metade
       fique estreita na tela.

    2. **Sem espaço desperdiçado.** A caixa de cada metade tinha a largura da
       imagem mais ALTA, então uma foto em pé ao lado de uma deitada deixava
       faixas escuras enormes dos dois lados. Agora cada metade recebe a largura
       da sua própria imagem, escalada pela mesma ALTURA (que é o que mantém as
       duas na mesma escala de comparação).

    3. **Sem faixa de legenda.** As imagens ficam encostadas uma na outra, com
       8 px de separação. Antes havia uma tarja escura com texto em cima de cada
       uma, que o usuário pediu para tirar.

    A altura-alvo tem um MÍNIMO (620 px): sem ele, duas fotos de paisagem lado a
    lado saíam com 320 px de altura, finas demais para julgar qualquer coisa.
    """
    return calcular_layout(a.width, a.height, b.width, b.height, largura_max)


def comparar(
    positivo: Path,
    restaurado: Path,
    largura_max: int = 1400,
) -> bytes:
    """
    Monta uma imagem única com positivo e restaurado LADO A LADO, sem bordas.

    Por que no servidor e não com duas tags <img> no navegador: o navegador
    baixa UM arquivo reduzido em vez de duas imagens grandes (~5-7 MB cada).
    Medido: a comparação sai com ~14% do tamanho das duas somadas.

    As duas metades são escaladas pela MESMA altura, então a comparação é de
    conteúdo e não de zoom.

    Devolve PNG.
    """
    import io

    from PIL import Image

    if not positivo.exists():
        raise FileNotFoundError(f"positivo não encontrado: {positivo.name}")
    if not restaurado.exists():
        raise FileNotFoundError(f"restaurado não encontrado: {restaurado.name}")

    FUNDO = (18, 20, 26)

    with Image.open(positivo) as pa, Image.open(restaurado) as pb:
        a = pa.convert("RGB")
        b = pb.convert("RGB")

        altura, la, lb, escala = _layout_lado_a_lado(a, b, largura_max)

        def redim(im, largura):
            return im.resize((max(largura, 1), altura), Image.LANCZOS)

        ia = redim(a, la)
        ib = redim(b, lb)

        folga = 8
        saida = Image.new("RGB", (ia.width + folga + ib.width, altura), FUNDO)
        saida.paste(ia, (0, 0))
        saida.paste(ib, (ia.width + folga, 0))

        if escala < 1.0:
            saida = saida.resize(
                (max(int(saida.width * escala), 1),
                 max(int(saida.height * escala), 1)),
                Image.LANCZOS,
            )

        buf = io.BytesIO()
        saida.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def parede_de_comparacoes(
    pares: list[tuple[str, Path, Path]],
    largura_max: int = 1500,
    largura_mini: int = 760,
) -> bytes:
    """
    Monta VÁRIAS comparações numa imagem só, empilhadas em cartões.

    Cada cartão traz uma miniatura reduzida da comparação (não a imagem cheia),
    porque o objetivo é VISÃO GERAL: ver de longe quais fotos valem uma olhada
    de perto. Para o detalhe, a tela abre a comparação grande de uma foto.

    `pares` é [(nome, caminho_do_positivo, caminho_do_restaurado)].

    Devolve PNG.
    """
    import io

    from PIL import Image, ImageDraw

    FUNDO = (18, 20, 26)
    cartoes = []
    for nome, caminho_pos, caminho_res in pares:
        with Image.open(caminho_pos) as a, Image.open(caminho_res) as b:
            mini = comparar_virtual(a.convert("RGB"), b.convert("RGB"),
                                    largura_max=largura_mini,
                                    rotulo_a="positivo",
                                    rotulo_b="restaurado")
        cartoes.append((nome, mini))

    if not cartoes:
        raise ValueError("nenhum par para comparar")

    margem = 12
    largura = max(c.width for _, c in cartoes) + margem * 2
    altura_total = margem
    for _, c in cartoes:
        altura_total += 34 + c.height + margem      # 34 = faixa do nome

    saida = Image.new("RGB", (largura, altura_total), FUNDO)

    y = margem
    for nome, c in cartoes:
        ImageDraw.Draw(saida).text((margem + 4, y + 8), nome,
                                   fill=(230, 232, 236))
        saida.paste(c, (margem, y + 34))
        y += 34 + c.height + margem

    if saida.width > largura_max:
        escala = largura_max / saida.width
        saida = saida.resize(
            (largura_max, max(int(round(saida.height * escala)), 1)),
            Image.LANCZOS,
        )

    buf = io.BytesIO()
    saida.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def comparar_virtual(a, b, largura_max: int = 1200,
                     rotulo_a: str = "positivo (inversão local)",
                     rotulo_b: str = "restaurado pela IA"):
    """
    Como `comparar`, mas recebe as imagens já abertas.

    Existe para a parede de comparações reaproveitar a mesma montagem sem
    reler os arquivos do disco a cada cartão.
    """
    from PIL import Image

    FUNDO = (18, 20, 26)
    vertical = _eh_vertical(a.width, a.height, b.width, b.height, largura_max)

    if vertical:
        largura_caixa = min(a.width, largura_max)
        altura_conteudo = max(int(largura_caixa * a.height / a.width), 1)
        altura_faixa = max(int(altura_conteudo * 0.045), 48)
        pa = _painel(a, rotulo_a, altura_conteudo, largura_caixa, altura_faixa)
        pb = _painel(b, rotulo_b, altura_conteudo, largura_caixa, altura_faixa)
        folga = 8
        saida = Image.new("RGB",
                          (largura_caixa, pa.height + folga + pb.height), FUNDO)
        saida.paste(pa, (0, 0))
        saida.paste(pb, (0, pa.height + folga))
    else:
        altura_conteudo = max(a.height, b.height)
        largura_caixa = max(int(round(altura_conteudo * a.width / a.height)), 1)
        altura_faixa = max(int(altura_conteudo * 0.025), 40)
        pa = _painel(a, rotulo_a, altura_conteudo, largura_caixa, altura_faixa)
        pb = _painel(b, rotulo_b, altura_conteudo, largura_caixa, altura_faixa)
        folga = 6
        saida = Image.new("RGB",
                          (pa.width + folga + pb.width, pa.height), FUNDO)
        saida.paste(pa, (0, 0))
        saida.paste(pb, (pa.width + folga, 0))

    if saida.width > largura_max:
        escala = largura_max / saida.width
        saida = saida.resize(
            (largura_max, max(int(round(saida.height * escala)), 1)),
            Image.LANCZOS,
        )
    return saida


@dataclass
class Trabalho:
    """
    Estado de uma tarefa em andamento, para consulta via HTTP.

    O servidor roda a tarefa numa thread e o cliente acompanha por polling em
    /api/progresso.

    NOTA sobre a contagem: cada arquivo emite VÁRIOS eventos (abrindo, adobe,
    invertendo, pronto). Contar `ok`/`falhas` a cada evento inflava os números
    -- 3 arquivos viravam 12 "ok". Por isso a contagem vem do resultado final,
    não dos eventos.
    """
    tipo: str
    total: int = 0
    feitos: int = 0          # arquivos concluídos (não passos)
    arquivo_atual: str = ""
    etapa: str = ""
    ok: int = 0
    falhas: int = 0
    mensagem: str = ""
    resultados: list = field(default_factory=list)
    custo: float = 0.0
    segundos: float = 0.0
    terminado: bool = False
    erro: str = ""
    # Quando a etapa atual começou (epoch). A tela mostra o tempo decorrido.
    marco: float = 0.0
    parar: threading.Event = field(default_factory=threading.Event)

    def como_dict(self) -> dict:
        return {
            "tipo": self.tipo,
            "total": self.total,
            "feitos": self.feitos,
            "arquivo_atual": self.arquivo_atual,
            "etapa": self.etapa,
            "ok": self.ok,
            "falhas": self.falhas,
            "mensagem": self.mensagem,
            "resultados": self.resultados,
            "custo": self.custo,
            "segundos": self.segundos,
            "terminado": self.terminado,
            "erro": self.erro,
            "progresso": (self.feitos / self.total) if self.total else 0.0,
            "marco": self.marco,
            "agora": time.time(),
        }

    def alimentar(self, ev: dict) -> None:
        """Recebe um evento de progresso. Não conta ok/falhas -- só avança."""
        self.feitos = int(ev.get("feitos", self.feitos))
        self.arquivo_atual = ev.get("nome", self.arquivo_atual)
        self.etapa = ev.get("etapa", self.etapa)
        self.mensagem = ev.get("msg", "")
        # `marco` é quando a etapa atual começou. A tela usa para mostrar o
        # tempo decorrido -- sem isso o usuário não sabe se travou ou trabalha.
        if "marco" in ev:
            self.marco = float(ev["marco"])
        elif self.marco == 0.0:
            self.marco = time.time()

    def finalizar(self, resumo: dict) -> None:
        """Fecha o trabalho com os números do resumo (fonte da verdade)."""
        self.total = int(resumo.get("total", self.total))
        self.ok = int(resumo.get("ok", 0))
        self.falhas = int(resumo.get("falhas", 0))
        self.feitos = self.total
        self.custo = float(resumo.get("custo", 0.0))
        self.segundos = float(resumo.get("segundos", 0.0))
        self.resultados = resumo.get("resultados", [])
        self.etapa = "concluido"
        self.terminado = True
