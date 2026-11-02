"""
neg35 -- interface web.

    .venv\\Scripts\\python.exe tools/app.py
    .venv\\Scripts\\python.exe tools/app.py --porta 8765 --abrir

O que a tela faz, na ordem em que você pediu:

1. ao abrir, compara a pasta de origem com a de positivos e a de restaurados
2. converte automaticamente tudo que ainda não tem positivo, com barra de
   progresso mostrando "N de M" e em qual arquivo está
3. depois, mostra só os que ainda não foram restaurados, com miniatura
4. clicar na miniatura abre a imagem grande (zoom)
5. caixa de seleção por foto; um botão manda as marcadas para a IA

Não usa FastAPI nem Flask de propósito: o `pip` trava neste ambiente (proxy e
%TEMP% bloqueados), então tudo roda com http.server da biblioteca padrão.
"""

from __future__ import annotations

import argparse
import datetime
import json
import mimetypes
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from neg35 import config, servidor  # noqa: E402

WEB = RAIZ / "web"
ENV_PADRAO = RAIZ / ".env"

# Trabalho em andamento (conversão ou restauração). Um por vez: é uma
# ferramenta pessoal, e dois trabalhos simultâneos só confundiriam.
_trabalho: servidor.Trabalho | None = None
_trava = threading.Lock()
_cfg_atual: config.Config | None = None
_cfg_mtime: float = 0.0


def _cfg() -> config.Config:
    """
    Devolve a configuração, RELENDO o .env se o arquivo mudou.

    O `.env` era lido uma vez, na inicialização, e ficava em memória. Isso
    causava confusão recorrente: o usuário editava as pastas, a tela continuava
    mostrando as antigas, e parecia que a alteração não tinha funcionado.

    Agora o mtime do arquivo é conferido a cada consulta. É uma chamada de
    sistema baratíssima, e elimina a classe inteira de problema.
    """
    global _cfg_atual, _cfg_mtime
    try:
        mtime = ENV_PADRAO.stat().st_mtime
    except OSError:
        mtime = 0.0

    if _cfg_atual is None or mtime != _cfg_mtime:
        _cfg_atual = config.carregar(ENV_PADRAO)
        _cfg_mtime = mtime
    return _cfg_atual


def _recarregar_cfg() -> config.Config:
    global _cfg_atual, _cfg_mtime
    _cfg_atual = config.carregar(ENV_PADRAO)
    try:
        _cfg_mtime = ENV_PADRAO.stat().st_mtime
    except OSError:
        _cfg_mtime = 0.0
    return _cfg_atual


class Handler(BaseHTTPRequestHandler):
    server_version = "neg35"
    protocol_version = "HTTP/1.1"

    # -- utilidades ------------------------------------------------------
    def log_message(self, fmt, *args):  # noqa: A003
        # Silencia o log padrão (poluído). Só mostramos erros.
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            print(f"  [{args[1]}] {args[0]}")

    def _json(self, dados: dict, status: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _erro(self, msg: str, status: int = 400) -> None:
        self._json({"erro": msg}, status=status)

    def _bytes(self, dados: bytes, tipo: str, cache: bool = True) -> None:
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def _corpo_json(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    # -- rotas -----------------------------------------------------------
    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        rota = u.path

        if rota in ("/", "/index.html"):
            return self._servir_arquivo(WEB / "index.html")
        if rota.startswith("/web/"):
            return self._servir_arquivo(WEB / rota[len("/web/"):])
        if rota == "/api/falhas-restauro":
            # GET, consulta. Ver a observação em /api/falhas.
            try:
                return self._json(servidor.falhas_restauro(_recarregar_cfg()))
            except Exception as e:  # noqa: BLE001
                return self._erro(f"falha ao listar: {type(e).__name__}: {e}",
                                  500)
        if rota == "/api/renomear":
            # GET: lista o que ainda não recebeu prefixo.
            try:
                return self._json(servidor.listar_para_renomear(_recarregar_cfg()))
            except Exception as e:  # noqa: BLE001
                return self._erro(f"falha ao listar: {type(e).__name__}: {e}",
                                  500)
        if rota == "/api/falhas":
            # GET, não POST: é consulta. (Já coloquei uma rota de consulta no
            # do_POST por engano antes -- /api/abrir-pasta -- e dava 404.)
            try:
                return self._json(servidor.falhas_e_pendentes(_recarregar_cfg()))
            except Exception as e:  # noqa: BLE001
                return self._erro(f"falha ao listar: {type(e).__name__}: {e}",
                                  500)
        if rota == "/api/estado":
            try:
                d = servidor.estado(_cfg())
                # Recursos + carimbo desta versão do servidor. A tela confere
                # se o servidor tem tudo o que ela espera; se faltar, é sinal
                # de processo antigo em memória (o Python não recarrega os
                # módulos sozinho) e a tela pede para reiniciar.
                d["recursos"] = list(servidor.RECURSOS)
                d["versao_servidor"] = servidor.versao_do_codigo()
                return self._json(d)
            except Exception as e:  # noqa: BLE001
                return self._erro(f"{type(e).__name__}: {e}", 500)
        if rota == "/api/abrir-pasta":
            # Abre a pasta no Explorer. Só aceita as três pastas CONFIGURADAS:
            # não recebe caminho arbitrário, para não virar um "abra qualquer
            # coisa" numa ferramenta que roda no seu computador.
            q = parse_qs(u.query)
            qual = (q.get("qual", [""])[0] or "").lower()
            c = _cfg()
            mapa = {
                "origem": c.pasta_origem,
                "positivo": c.pasta_positivo,
                "restaurado": c.pasta_restaurada,
                "restaurada": c.pasta_restaurada,
            }
            if qual not in mapa:
                return self._erro("informe qual pasta: origem, positivo ou "
                                  "restaurada", 400)
            ok, info = servidor.abrir_pasta(mapa[qual])
            if not ok:
                return self._erro(info, 400)
            return self._json({"ok": True, "aberto": info})
        if rota == "/api/copiar-caminho":
            # Copia o caminho de uma das pastas configuradas para a área de
            # transferência. Existe porque abrir o Explorer FALHA em alguns
            # ambientes (sessão restrita impede criar processos de interface),
            # e nesses casos isto é o que funciona.
            q = parse_qs(u.query)
            qual = (q.get("qual", [""])[0] or "").lower()
            c = _cfg()
            mapa = {
                "origem": c.pasta_origem,
                "positivo": c.pasta_positivo,
                "restaurado": c.pasta_restaurada,
                "restaurada": c.pasta_restaurada,
            }
            if qual not in mapa:
                return self._erro("informe qual pasta: origem, positivo ou "
                                  "restaurada", 400)
            caminho = mapa[qual]
            ok, info = servidor.copiar_para_area_de_transferencia(caminho)
            if not ok:
                return self._erro(info, 500)
            return self._json({"ok": True, "copiado": caminho, "metodo": info})
        if rota == "/api/verificar-pastas":
            # Diagnóstico das pastas: existem? dá para gravar?
            # A tela pede isto ao abrir, para o usuário saber do problema ANTES
            # de mandar converter (e antes de pagar a IA).
            try:
                d = servidor.verificar_pastas(_cfg())
                # Locais possíveis para a saída, cada um já TESTADO. A pasta
                # certa depende da máquina, então não dá para chutar um caminho
                # fixo -- a tela oferece só o que funciona.
                d["candidatos"] = config.candidatos_de_saida()
                return self._json(d)
            except Exception as e:  # noqa: BLE001
                return self._erro(f"{type(e).__name__}: {e}", 500)
        if rota == "/api/config":
            c = _cfg()
            return self._json({
                "pastas": {"origem": c.pasta_origem,
                           "positivo": c.pasta_positivo,
                           "restaurada": c.pasta_restaurada},
                "modelo": c.modelo, "provedor": c.provedor,
                "filme": c.filme, "saturacao": c.saturacao,
                "nitidez": c.nitidez, "balanco": c.balanco,
                "usar_curva": c.usar_curva, "curva_alvo": c.curva_alvo,
                "curva_gamma": c.curva_gamma,
                "usar_adobe": c.usar_adobe, "max_lado_envio": c.max_lado_envio,
                "pasta_cache_adobe": c.pasta_cache_adobe,
                "cache_adobe_resolvido": (
                    str(config.pasta_cache_adobe(c)) if c.usar_adobe else ""),
                "converter_auto": c.converter_auto,
                "casar_exposicao": c.casar_exposicao,
                "exposicao_forca": c.exposicao_forca,
                "dica_por_foto": c.dica_por_foto,
                "recortar_bordas": c.recortar_bordas,
                "recorte_margem": c.recorte_margem,
                "limpar_borda_no_prompt": c.limpar_borda_no_prompt,
                "brilho_envio": c.brilho_envio,
                "tem_chave": bool(c.openrouter_api_key if c.provedor == "openrouter"
                                  else c.gemini_api_key),
                # Valores recomendados, para a tela poder mostrá-los ao lado de
                # cada campo. Assim o usuário sabe o que é "normal" sem ter de
                # perguntar.
                "recomendados": servidor.RECOMENDADOS,
            })
        if rota == "/api/progresso":
            with _trava:
                t = _trabalho
            return self._json(t.como_dict() if t else {"tipo": None, "terminado": True})
        if rota == "/api/custo":
            q = parse_qs(u.query)
            nomes = [n for n in (q.get("nomes", [""])[0]).split(",") if n]
            valor, fonte = servidor.custo_estimado(_cfg(), len(nomes))
            return self._json({"quantos": len(nomes), "usd": round(valor, 4),
                               "fonte": fonte})
        if rota.startswith("/midia/"):
            return self._servir_midia(rota, u.query)
        if rota.startswith("/imagem/"):
            return self._servir_imagem(rota, u.query)
        return self._erro("rota não encontrada", 404)

    def do_POST(self):  # noqa: N802
        u = urlparse(self.path)
        rota = u.path
        dados = self._corpo_json()

        if rota == "/api/converter":
            return self._iniciar_conversao(dados)
        if rota == "/api/restaurar":
            return self._iniciar_restauracao(dados)
        if rota == "/api/regenerar":
            return self._iniciar_regeneracao(dados)
        if rota == "/api/recortar-restaurado":
            nome = (dados.get("nome") or "").strip()
            if not nome:
                return self._erro("informe o nome da foto")
            faltando = [k for k in ("x0", "y0", "x1", "y1") if k not in dados]
            if faltando:
                return self._erro(f"faltam as coordenadas: {', '.join(faltando)}")
            try:
                return self._json(servidor.recortar_restaurado(
                    _recarregar_cfg(), nome,
                    dados["x0"], dados["y0"], dados["x1"], dados["y1"]))
            except FileNotFoundError as e:
                return self._erro(str(e), 404)
            except ValueError as e:
                return self._erro(str(e), 400)
            except Exception as e:  # noqa: BLE001
                return self._erro(f"{type(e).__name__}: {e}", 500)
        if rota == "/api/renomear-fotos":
            # POST: renomeia as fotos marcadas com o prefixo.
            nomes = dados.get("nomes") or []
            if not isinstance(nomes, list) or not nomes:
                return self._erro("nenhuma foto selecionada")
            try:
                return self._json(servidor.renomear_fotos(
                    _recarregar_cfg(), nomes, dados.get("prefixo") or ""))
            except ValueError as e:
                return self._erro(str(e), 400)
            except Exception as e:  # noqa: BLE001
                return self._erro(f"{type(e).__name__}: {e}", 500)
        if rota == "/api/desfazer-restaurado":
            nome = (dados.get("nome") or "").strip()
            if not nome:
                return self._erro("informe o nome da foto")
            try:
                return self._json(servidor.desfazer_restaurado(
                    _recarregar_cfg(), nome, dados.get("backup")))
            except FileNotFoundError as e:
                return self._erro(str(e), 404)
            except ValueError as e:
                return self._erro(str(e), 400)
            except Exception as e:  # noqa: BLE001
                return self._erro(f"{type(e).__name__}: {e}", 500)
        if rota == "/api/olhos-vermelhos":
            nome = (dados.get("nome") or "").strip()
            if not nome:
                return self._erro("informe o nome da foto")
            try:
                return self._json(servidor.corrigir_olhos_restaurado(
                    _recarregar_cfg(), nome,
                    dados.get("x0", 0.0), dados.get("y0", 0.0),
                    dados.get("x1", 1.0), dados.get("y1", 1.0),
                    dados.get("forca", 0.85)))
            except FileNotFoundError as e:
                return self._erro(str(e), 404)
            except ValueError as e:
                return self._erro(str(e), 400)
            except Exception as e:  # noqa: BLE001
                return self._erro(f"{type(e).__name__}: {e}", 500)
        if rota == "/api/girar-restaurado":
            # Rotação por ângulo qualquer (para alinhar negativo torto).
            nome = (dados.get("nome") or "").strip()
            if not nome:
                return self._erro("informe o nome da foto")
            try:
                return self._json(servidor.girar_restaurado(
                    _recarregar_cfg(), nome, dados.get("angulo")))
            except FileNotFoundError as e:
                return self._erro(str(e), 404)
            except ValueError as e:
                return self._erro(str(e), 400)
            except Exception as e:  # noqa: BLE001
                return self._erro(f"{type(e).__name__}: {e}", 500)
        if rota == "/api/rotacionar-restaurado":
            nome = (dados.get("nome") or "").strip()
            if not nome:
                return self._erro("informe o nome da foto")
            try:
                giros = int(dados.get("giros", 1))
            except (TypeError, ValueError):
                return self._erro("giros inválido")
            try:
                return self._json(
                    servidor.rotacionar_restaurado(_recarregar_cfg(), nome, giros))
            except FileNotFoundError as e:
                return self._erro(str(e), 404)
            except ValueError as e:
                return self._erro(str(e), 400)
            except Exception as e:  # noqa: BLE001
                return self._erro(f"{type(e).__name__}: {e}", 500)
        if rota == "/api/diagnosticar-falha":
            return self._diagnosticar_falha(dados)
        if rota == "/api/parar":
            with _trava:
                if _trabalho is not None:
                    _trabalho.parar.set()
            return self._json({"ok": True})
        if rota == "/api/salvar-config":
            return self._salvar_config(dados)
        if rota == "/api/usar-pastas-locais":
            return self._usar_pastas_locais(dados)
        return self._erro("rota não encontrada", 404)

    # -- handlers específicos -------------------------------------------
    def _servir_arquivo(self, caminho: Path) -> None:
        if not caminho.is_file():
            return self._erro(f"não encontrado: {caminho.name}", 404)
        tipo = mimetypes.guess_type(str(caminho))[0] or "application/octet-stream"
        # SEM cache. São três arquivos pequenos e locais; em troca, o navegador
        # nunca fica com uma versão velha da tela depois de uma correção -- o
        # que já causou confusão real (layout antigo com código novo).
        return self._bytes(caminho.read_bytes(), tipo, cache=False)

    def _servir_midia(self, rota: str, query: str) -> None:
        """
        Serve o positivo, o restaurado, uma miniatura, ou a comparação.

        Rotas:
          /midia/positivo/<nome>       imagem cheia do positivo
          /midia/restaurado/<nome>     imagem cheia da restaurada
          /midia/comparar/<nome>       positivo e restaurado lado a lado,
                                       montado aqui e reduzido
        O parâmetro ?thumb=1 devolve a miniatura (340 px).
        """
        partes = rota.strip("/").split("/")
        if len(partes) < 3:
            return self._erro("rota de mídia inválida", 400)
        tipo = partes[1]
        nome = unquote("/".join(partes[2:]))
        c = _cfg()
        q = parse_qs(query)
        pequeno = q.get("thumb", ["0"])[0] == "1"

        positivo_dir = Path(c.pasta_positivo)
        restaurado_dir = Path(c.pasta_restaurada)

        def achar(base: Path) -> Path | None:
            if not base.is_dir():
                return None
            achados = sorted(base.glob(f"{nome}*.png"))
            return achados[0] if achados else None

        # --- comparação lado a lado
        if tipo == "comparar":
            pos = achar(positivo_dir)
            res = achar(restaurado_dir)
            if pos is None:
                return self._erro("sem positivo para comparar", 404)
            if res is None:
                return self._erro("esta foto ainda não foi restaurada", 404)
            try:
                largura = int(q.get("w", ["1400"])[0])
            except ValueError:
                largura = 1400
            try:
                # cache=False: a comparação depende de DOIS arquivos que mudam
                # (positivo e restaurado). Com cache de 1 h, refazer uma foto e
                # abrir a comparação mostrava a imagem VELHA -- foi o que
                # aconteceu depois de apagar e reprocessar uma restaurada.
                return self._bytes(servidor.comparar(pos, res, largura_max=largura),
                                   "image/png", cache=False)
            except Exception as e:  # noqa: BLE001
                return self._erro(f"falha ao montar a comparação: {e}", 500)

        # --- imagem simples
        if tipo not in ("positivo", "restaurado"):
            return self._erro("tipo inválido", 400)
        base = positivo_dir if tipo == "positivo" else restaurado_dir
        caminho = achar(base)
        if caminho is None:
            return self._erro("arquivo não encontrado", 404)

        if pequeno:
            try:
                # cache=False: a miniatura reflete o arquivo, que é regravado
                # quando a foto é reconvertida ou restaurada de novo. Em cache,
                # a grade continuaria mostrando a versão antiga por até 1 h.
                return self._bytes(servidor.thumb(caminho, 340), "image/png",
                                   cache=False)
            except Exception as e:  # noqa: BLE001
                return self._erro(f"falha ao gerar miniatura: {e}", 500)
        return self._bytes(caminho.read_bytes(), "image/png", cache=False)

    def _servir_imagem(self, rota: str, query: str) -> None:
        """
        Serve UMA imagem (o positivo ou o restaurado), opcionalmente reduzida.

        Existe para a tela de comparação poder abrir só a metade restaurada,
        grande. Abrir a comparação inteira mostra as duas metades e cada uma
        fica pequena -- foi o que motivou esta rota.

        `/imagem/restaurado/<nome>?w=1800`
        """
        partes = rota.strip("/").split("/")
        if len(partes) < 3:
            return self._erro("rota de imagem inválida", 400)
        tipo = partes[1]
        nome = unquote("/".join(partes[2:]))
        if tipo not in ("positivo", "restaurado"):
            return self._erro("tipo inválido: use positivo ou restaurado", 400)

        c = _cfg()
        base = Path(c.pasta_positivo if tipo == "positivo" else c.pasta_restaurada)
        if not base.is_dir():
            return self._erro("pasta não encontrada", 404)
        achados = sorted(base.glob(f"{nome}*.png"))
        if not achados:
            return self._erro("arquivo não encontrado", 404)
        caminho = achados[0]

        q = parse_qs(query)
        try:
            largura = int(q.get("w", ["0"])[0])
        except ValueError:
            largura = 0

        if largura <= 0:
            return self._bytes(caminho.read_bytes(), "image/png", cache=False)
        try:
            # cache=False: esta rota serve a imagem grande do visor, e o arquivo
            # é sobrescrito por rotação e recorte.
            return self._bytes(servidor.imagem_reduzida(caminho, largura),
                               "image/png", cache=False)
        except Exception as e:  # noqa: BLE001
            return self._erro(f"falha ao redimensionar: {e}", 500)

    def _listar_falhas(self, query: str) -> None:
        """
        Lista os negativos que não geraram positivo, para a aba de falhas.

        Junta o registro persistido com uma varredura da pasta de origem -- ver
        `servidor.falhas_e_pendentes`.
        """
        try:
            dados = servidor.falhas_e_pendentes(_recarregar_cfg())
        except Exception as e:  # noqa: BLE001
            return self._erro(f"falha ao listar: {type(e).__name__}: {e}", 500)
        return self._json(dados)

    def _diagnosticar_falha(self, dados: dict) -> None:
        """
        Tenta abrir UM negativo e registra o motivo real da falha.

        Roda na própria requisição: abrir um DNG de 14 MB leva alguns segundos, e
        o servidor é multi-thread, então isso não trava as outras telas. O
        navegador mostra "diagnosticando" enquanto espera.
        """
        nome = (dados.get("nome") or "").strip()
        if not nome:
            return self._erro("informe o nome do negativo")
        try:
            r = servidor.diagnosticar_negativo(_recarregar_cfg(), nome)
        except Exception as e:  # noqa: BLE001
            return self._erro(f"{type(e).__name__}: {e}", 500)
        return self._json(r)

    def _iniciar_regeneracao(self, dados: dict) -> None:
        """
        Refaz a restauração de UMA foto, apagando a atual.

        Serve para o ajuste de brilho da tela de comparação: o usuário olha o
        resultado, decide que está escuro, clareia e manda de novo. A foto
        antiga é apagada junto -- se ficasse, o usuário não saberia qual está
        vendo.
        """
        global _trabalho
        nome = (dados.get("nome") or "").strip()
        if not nome:
            return self._erro("informe o nome da foto")

        try:
            brilho = float(dados.get("brilho", 1.0))
        except (TypeError, ValueError):
            return self._erro("brilho inválido")
        if not 0.3 <= brilho <= 3.0:
            return self._erro("brilho fora da faixa aceita (0,3 a 3,0)")

        c = _cfg()
        if c.provedor == "openrouter" and not c.openrouter_api_key:
            return self._erro("falta a chave do OpenRouter no .env")
        if c.provedor == "gemini" and not c.gemini_api_key:
            return self._erro("falta a chave do Gemini no .env")

        positivo = Path(c.pasta_positivo) / f"{nome}_positivo.png"
        if not positivo.is_file():
            return self._erro(f"não existe positivo para {nome}", 404)

        with _trava:
            if _trabalho is not None and not _trabalho.terminado:
                return self._erro("já existe um trabalho em andamento", 409)
            _trabalho = servidor.Trabalho(tipo="restauracao", total=1)
            trabalho = _trabalho

        apagado = servidor.apagar_restaurado(c, nome)
        forcar = bool(dados.get("forcar"))

        def rodar():
            try:
                resumo = servidor.restaurar(
                    _cfg(), [nome], progresso=trabalho.alimentar,
                    parar=trabalho.parar, forcar=forcar, brilho=brilho,
                )
                resumo["apagado"] = apagado
                resumo["brilho"] = brilho
                trabalho.finalizar(resumo)
            except Exception as e:  # noqa: BLE001
                trabalho.erro = f"{type(e).__name__}: {e}"
                trabalho.terminado = True

        threading.Thread(target=rodar, daemon=True).start()
        return self._json({"iniciado": True, "nome": nome,
                           "brilho": brilho, "apagado": apagado})

    def _iniciar_conversao(self, dados: dict) -> None:
        global _trabalho
        with _trava:
            if _trabalho is not None and not _trabalho.terminado:
                return self._erro("já existe um trabalho em andamento", 409)
            nomes = dados.get("nomes") or None
            est = servidor.estado(_cfg())
            total = (len(nomes) if nomes else est["contagens"]["faltam_positivo"])
            _trabalho = servidor.Trabalho(tipo="conversao", total=total)
            trabalho = _trabalho

        def rodar():
            global _trabalho
            try:
                resumo = servidor.converter(
                    _cfg(), nomes, progresso=trabalho.alimentar, parar=trabalho.parar
                )
                trabalho.finalizar(resumo)
            except Exception as e:  # noqa: BLE001
                trabalho.erro = f"{type(e).__name__}: {e}"
                trabalho.terminado = True
        threading.Thread(target=rodar, daemon=True).start()
        self._json({"iniciado": True, "total": total})

    def _iniciar_restauracao(self, dados: dict) -> None:
        global _trabalho
        nomes = dados.get("nomes") or []
        if not nomes:
            return self._erro("nenhuma foto selecionada")
        c = _cfg()
        if c.provedor == "openrouter" and not c.openrouter_api_key:
            return self._erro("falta a chave do OpenRouter no .env")
        if c.provedor == "gemini" and not c.gemini_api_key:
            return self._erro("falta a chave do Gemini no .env")

        with _trava:
            if _trabalho is not None and not _trabalho.terminado:
                return self._erro("já existe um trabalho em andamento", 409)
            _trabalho = servidor.Trabalho(tipo="restauracao", total=len(nomes))
            trabalho = _trabalho
        forcar = bool(dados.get("forcar"))
        # Brilho opcional para o envio (multiplicador). Vem do controle da aba
        # de comparação, para o usuário poder pedir mais claro já na primeira
        # restauração -- sem precisar refazer depois.
        try:
            brilho = float(dados["brilho"]) if dados.get("brilho") is not None else None
        except (TypeError, ValueError):
            brilho = None
        if brilho is not None and not 0.3 <= brilho <= 3.0:
            return self._erro("brilho fora da faixa aceita (0,3 a 3,0)")

        def rodar():
            global _trabalho
            try:
                resumo = servidor.restaurar(
                    _cfg(), nomes, progresso=trabalho.alimentar,
                    parar=trabalho.parar, forcar=forcar, brilho=brilho,
                )
                trabalho.finalizar(resumo)
            except Exception as e:  # noqa: BLE001
                trabalho.erro = f"{type(e).__name__}: {e}"
                trabalho.terminado = True
        threading.Thread(target=rodar, daemon=True).start()
        self._json({"iniciado": True, "total": len(nomes), "brilho": brilho})

    def _usar_pastas_locais(self, dados: dict | None = None) -> None:
        """
        Aponta a SAÍDA para uma pasta que aceita escrita, mantendo a origem.

        `dados["caminho"]` é opcional: se vier, usamos essa pasta (e recusamos
        com mensagem clara se não gravar). Se não vier, escolhemos a primeira
        da lista testada que funciona.

        Por que isto existe: a pasta de saída precisa ser gravável, e qual é a
        pasta boa depende da máquina. Sugerir um caminho fixo seria um chute.
        """
        dados = dados or {}
        c = _recarregar_cfg()

        escolhida = (dados.get("caminho") or "").strip()
        if escolhida:
            base = Path(escolhida).expanduser()
            if not base.is_absolute():
                return self._erro("informe um caminho completo, "
                                  "por exemplo C:\\Fotos\\neg35")
            ok, erro = config.testar_escrita_simples(base)
            if not ok:
                return self._erro(f"{base}: {erro}", 400)
        else:
            base = config.pasta_local_gravavel()

        c.pasta_positivo = str(base / "positivo")
        c.pasta_restaurada = str(base / "restaurada")
        config.salvar(c, ENV_PADRAO)
        _recarregar_cfg()

        diag = servidor.verificar_pastas(_cfg())
        diag["candidatos"] = config.candidatos_de_saida()
        return self._json({"ok": True,
                           "pastas": {"positivo": c.pasta_positivo,
                                      "restaurada": c.pasta_restaurada},
                           "diagnostico": diag})

    def _salvar_config(self, dados: dict) -> None:
        c = _recarregar_cfg()
        campos_texto = ("pasta_origem", "pasta_positivo", "pasta_restaurada",
                        "provedor", "modelo", "filme", "pasta_cache_adobe")
        for k in campos_texto:
            if k in dados and isinstance(dados[k], str):
                setattr(c, k, dados[k].strip())
        for k in ("saturacao", "nitidez", "balanco", "curva_alvo",
                  "curva_gamma", "curva_preto", "exposicao_forca",
                  "recorte_margem"):
            if k in dados:
                try:
                    setattr(c, k, float(dados[k]))
                except (TypeError, ValueError):
                    pass
        for k in ("usar_curva", "usar_adobe", "converter_auto", "max_lado_envio",
                  "casar_exposicao", "dica_por_foto", "recortar_bordas",
                  "limpar_borda_no_prompt"):
            if k in dados:
                try:
                    setattr(c, k, int(dados[k]) if k == "max_lado_envio" else bool(dados[k]))
                except (TypeError, ValueError):
                    pass
        config.salvar(c, ENV_PADRAO)
        _recarregar_cfg()
        return self._json({"ok": True})


def _porta_livre(preferida: int) -> int:
    """Se a porta estiver ocupada, procura a próxima livre."""
    for p in range(preferida, preferida + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError(f"nenhuma porta livre entre {preferida} e {preferida + 40}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Interface web do neg35")
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--env", default=None, help="caminho do .env (padrão: raiz do projeto)")
    ap.add_argument("--abrir", action="store_true", help="abre o navegador")
    ap.add_argument("--sem-auto", action="store_true",
                    help="não converte automaticamente ao abrir a página")
    args = ap.parse_args()

    global ENV_PADRAO
    if args.env:
        ENV_PADRAO = Path(args.env).resolve()

    if not (WEB / "index.html").is_file():
        print(f"ERRO: não encontrei {WEB / 'index.html'}")
        return 1

    cfg = _recarregar_cfg()
    porta = _porta_livre(args.porta)
    url = f"http://{args.host}:{porta}/"

    print()
    print("=" * 68)
    print("  neg35 -- interface")
    print("=" * 68)
    # Mostra QUAL arquivo de configuração está sendo usado e quando foi
    # alterado. Sem isso, é impossível perceber que o servidor está com a
    # configuração antiga na memória -- já aconteceu de o .env estar correto
    # em disco e a tela continuar mostrando o caminho velho.
    try:
        mtime = ENV_PADRAO.stat().st_mtime
        marca = " (alterado " + datetime.datetime.fromtimestamp(mtime).strftime("%d/%m %H:%M") + ")"
    except OSError:
        marca = " (ainda não existe)"
    print(f"  config      : {ENV_PADRAO}{marca}")
    print(f"  origem      : {cfg.pasta_origem}")
    print(f"  positivos   : {cfg.pasta_positivo}")
    print(f"  restauradas : {cfg.pasta_restaurada}")
    print(f"  modelo      : {cfg.modelo}")

    # Avisa antes de começar se a saída não aceita escrita.
    diag = servidor.verificar_pastas(cfg)
    if not diag["tudo_ok"]:
        print()
        print("  ATENÇÃO:")
        for p in diag["problemas"]:
            print(f"    - {p}")
        if diag["dica_nuvem"]:
            print(f"    {diag['dica_nuvem']}")
    print()
    print(f"  Abra no navegador:  {url}")
    if args.sem_auto:
        print("  (conversão automática DESATIVADA por --sem-auto)")
    print()
    print("  Ctrl+C para encerrar.")
    print()

    httpd = ThreadingHTTPServer((args.host, porta), Handler)
    if args.abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  encerrando...")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
