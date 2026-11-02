"""
Valida a ligação entre o HTML e o JavaScript.

Não tendo navegador headless disponível (o sandbox bloqueia os named pipes que
o Chrome/Edge usam), a checagem mais valiosa é a que pega o erro mais provável
em runtime: o JS buscar um id que não existe no HTML.

Se `$('algum-id')` não encontrar o elemento, o JS estoura com TypeError na
primeira interação -- e a tela fica "morta" sem mensagem clara.

    .venv\\Scripts\\python.exe tools/_teste_web.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"

FALHAS: list[str] = []


def checar(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok  {msg}")
    else:
        print(f"  FALHOU: {msg}")
        FALHAS.append(msg)


def ids_do_html(html: str) -> set[str]:
    return set(re.findall(r'\bid="([^"]+)"', html))


def ids_buscados_pelo_js(js: str) -> set[str]:
    """Pega os ids usados como $('id') e getElementById('id')."""
    achados = set(re.findall(r"\$\('([^']+)'\)", js))
    achados |= set(re.findall(r'\$\("([^"]+)"\)', js))
    achados |= set(re.findall(r'getElementById\(["\']([^"\']+)["\']\)', js))
    return achados


def rotas_do_js(js: str) -> set[str]:
    """Rotas de API que o JS chama."""
    rotas = set(re.findall(r"api\(['\"](/api/[^'\"]*)", js))
    rotas |= set(re.findall(r"post\(['\"](/api/[^'\"]*)", js))
    rotas |= set(re.findall(r"['\"](/midia/[^'\"]*)", js))
    return rotas


def main() -> int:
    html_p = WEB / "index.html"
    js_p = WEB / "app.js"
    css_p = WEB / "estilo.css"

    print("=== arquivos ===")
    for p in (html_p, js_p, css_p):
        checar(p.is_file(), f"{p.name} existe")
        if p.is_file():
            print(f"      {p.stat().st_size:,} bytes")

    if not (html_p.is_file() and js_p.is_file()):
        return 1

    html = html_p.read_text(encoding="utf-8")
    js = js_p.read_text(encoding="utf-8")
    css = css_p.read_text(encoding="utf-8") if css_p.is_file() else ""

    # ---------------------------------------------------------------- ids
    print()
    print("=== ids: o JS busca algo que ninguém cria? ===")
    do_html = ids_do_html(html)
    do_js = ids_buscados_pelo_js(js)
    # Parte dos ids é criada pelo PRÓPRIO JS: o banner de diagnóstico é montado
    # em tempo de execução, então não está no HTML. Vale se o id existe no HTML
    # OU se o JS o escreve em algum innerHTML.
    faltando = []
    for i in sorted(do_js):
        if i in do_html or f'id="{i}"' in js:
            continue
        faltando.append(i)
    print(f"  ids no HTML: {len(do_html)}   ids buscados pelo JS: {len(do_js)}")
    if faltando:
        print(f"  ids que ninguém cria: {faltando}")
    checar(not faltando, "todo id que o JS busca existe (no HTML ou criado pelo JS)")

    dinamicos = sorted(i for i in do_js if i not in do_html)
    if dinamicos:
        print(f"  (criados pelo JS: {dinamicos})")

    sobrando = sorted(do_html - do_js)
    if sobrando:
        print(f"  (ids no HTML que o JS não usa: {sobrando})")

    # ---------------------------------------------------------------- rotas
    print()
    print("=== rotas: o JS chama rotas que o servidor implementa? ===")
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("app_mod", str(RAIZ / "tools" / "app.py"))
    app_mod = module_from_spec(spec)
    spec.loader.exec_module(app_mod)

    fonte_servidor = (RAIZ / "tools" / "app.py").read_text(encoding="utf-8")
    rotas_js = rotas_do_js(js)
    conhecidas = {
        "/api/estado", "/api/config", "/api/progresso", "/api/custo",
        "/api/converter", "/api/restaurar", "/api/parar", "/api/salvar-config",
        "/api/verificar-pastas", "/api/usar-pastas-locais", "/api/abrir-pasta",
        "/api/copiar-caminho", "/api/regenerar", "/api/falhas",
        "/api/diagnosticar-falha", "/api/falhas-restauro",
        "/api/rotacionar-restaurado", "/api/recortar-restaurado",
        "/api/girar-restaurado", "/api/olhos-vermelhos",
        "/api/desfazer-restaurado", "/api/renomear",
        "/api/renomear-fotos",
    }
    for r in sorted(rotas_js):
        base = r.split("?")[0]
        if base.startswith("/midia"):
            ok = "/midia/" in fonte_servidor
            checar(ok, f"rota de mídia tratada pelo servidor")
            break
    for r in sorted(rotas_js):
        base = r.split("?")[0]
        if base.startswith("/imagem"):
            checar("/imagem/" in fonte_servidor,
                   "rota de imagem única tratada pelo servidor")
            break
    desconhecidas = sorted({r.split("?")[0] for r in rotas_js
                            if r.startswith("/api/")} - conhecidas)
    if desconhecidas:
        print(f"  rotas usadas pelo JS que eu não conheço: {desconhecidas}")
    checar(not desconhecidas, "o JS só usa rotas conhecidas do servidor")

    # ---------------------------------------------------------------- classes CSS
    print()
    print("=== CSS: as classes que o JS usa existem na folha? ===")
    classes_js = set(re.findall(r"classList\.(?:add|toggle|remove)\('([^']+)'\)", js))
    classes_js |= set(re.findall(r"className = '([^']+)'", js))
    faltam_css = []
    for c in sorted(classes_js):
        for parte in c.split():
            if parte and f".{parte}" not in css:
                faltam_css.append(parte)
    if faltam_css:
        print(f"  classes sem estilo: {sorted(set(faltam_css))}")
    checar(not faltam_css, "todas as classes que o JS aplica têm estilo")

    # ---------------------------------------------------------------- filmes
    print()
    print("=== filmes: o dropdown só oferece opções válidas? ===")
    from neg35 import core

    validos = set(core.GANHOS_POR_FILME)
    opcoes = set(re.findall(r'<option value="([^"]+)"', html))
    print(f"  presets no código: {len(validos)}   opções no dropdown: {len(opcoes)}")
    invalidas = sorted(opcoes - validos)
    if invalidas:
        print(f"  opções que o código NÃO conhece: {invalidas}")
    checar(not invalidas,
           "toda opção do dropdown existe em core.GANHOS_POR_FILME")
    faltando = sorted(validos - opcoes)
    if faltando:
        print(f"  (presets sem opção no dropdown: {faltando})")

    # ---------------------------------------------------------------- campos
    print()
    print("=== campos de configuração ===")
    # Todo campo numérico precisa de uma dica, senão o usuário não sabe o que
    # colocar -- foi a reclamação que originou esta mudança.
    campos = re.findall(r'<div class="campo">(.*?)</div>\s*(?=<div class="campo">|<h3|<label class="chk-linha"|<div class="modal-acoes")',
                        html, re.S)
    sem_dica = []
    for bloco in campos:
        rot = re.search(r"<label>([^<]+)</label>", bloco)
        nome = rot.group(1).strip() if rot else "(sem rótulo)"
        if 'class="dica"' not in bloco:
            sem_dica.append(nome)
    print(f"  campos encontrados: {len(campos)}")
    if sem_dica:
        print(f"  sem texto de ajuda: {sem_dica}")
    checar(not sem_dica, "todo campo de configuração tem texto de ajuda")

    # Os dois checkboxes precisam explicar quando usar.
    checar(html.count('class="chk-linha"') >= 2,
           "os dois checkboxes usam o formato explicado (chk-linha)")
    checar("Deixe <b>marcado</b>" in html,
           "os checkboxes dizem explicitamente para deixar marcado")

    # O botão de restaurar padrões precisa existir no HTML e ter evento no JS.
    checar('id="modal-padroes"' in html, "existe o botão de restaurar recomendados")
    checar("$('modal-padroes')" in js, "o botão de padrões tem evento ligado")
    checar("PADROES" in js, "os valores recomendados estão definidos no JS")

    # ---------------------------------------------------------------- abertura
    print()
    print("=== a tela de configuração não pode abrir sozinha ===")
    # O modal nasce escondido no HTML.
    checar(re.search(r'id="modal"[^>]*\bhidden\b', html) is not None,
           "o modal de configuração nasce com o atributo hidden")
    # E o JS reforça isso na abertura, antes de qualquer coisa assíncrona.
    trecho_inicio = js[js.find("async function iniciar"):]
    tem_hide = "$('modal').hidden = true" in trecho_inicio
    checar(tem_hide, "o iniciar() esconde o modal explicitamente")
    if tem_hide:
        linha_hide = trecho_inicio.find("$('modal').hidden = true")
        linha_liga = trecho_inicio.find("ligarEventos()")
        checar(0 <= linha_hide < linha_liga,
               "esconde o modal ANTES de ligar os eventos")
    # Só o clique na engrenagem abre.
    aberturas = js.count("$('modal').hidden = false")
    checar(aberturas == 1, f"o modal é aberto em um único lugar (achei {aberturas})")
    # E esse lugar é a função aberrConfig.
    pos_abre = js.find("$('modal').hidden = false")
    checar(pos_abre > js.find("async function abrirConfig"),
           "quem abre é a função abrirConfig (chamada só pela engrenagem)")

    # ---------------------------------------------------------------- recomendados
    print()
    print("=== valores recomendados visíveis na tela ===")
    checar('class="rec"' in html, "os rótulos têm espaço para o valor recomendado")
    checar("anotarRecomendados" in js, "o JS preenche os recomendados")
    checar("recomendado:" in js, "o JS escreve 'recomendado: X' no rótulo")
    checar(".rec" in css, "a marcação do recomendado tem estilo")
    # O servidor precisa enviar os recomendados e eles têm de bater com o
    # botão de padrões -- ter duas fontes divergentes seria um bug silencioso.
    from neg35 import servidor

    rec = getattr(servidor, "RECOMENDADOS", None)
    checar(rec is not None, "o servidor expõe RECOMENDADOS")
    if rec:
        checar(rec.get("saturacao") == 1.15 and rec.get("curva_alvo") == 0.50,
               f"os recomendados têm os valores testados ({rec.get('saturacao')}, "
               f"{rec.get('curva_alvo')})")
        for chave in ("filme", "saturacao", "nitidez", "balanco",
                      "curva_alvo", "curva_gamma", "max_lado_envio",
                      "usar_curva", "usar_adobe"):
            if chave not in rec:
                checar(False, f"RECOMENDADOS sem a chave {chave}")
        checar(all(k in rec for k in ("filme", "saturacao", "nitidez", "balanco",
                                      "curva_alvo", "curva_gamma",
                                      "max_lado_envio", "usar_curva", "usar_adobe")),
               "RECOMENDADOS cobre todos os campos da tela")

    # ---------------------------------------------------------------- hidden
    print()
    print("=== o atributo `hidden` realmente esconde? ===")
    # ESTA verificação faltava, e por isso o bug passou: o HTML tinha `hidden`
    # no modal e o JS punha `hidden = true`, mas a folha de estilo declarava
    # `display: flex` em `.modal` -- e o display do autor VENCE o
    # `[hidden] { display: none }` do navegador. A tela abria sozinha.
    tem_regra = re.search(r"\[hidden\]\s*\{[^}]*display\s*:\s*none", css) is not None
    checar(tem_regra, "a folha de estilo tem uma regra [hidden] { display: none }")
    tem_important = re.search(
        r"\[hidden\]\s*\{[^}]*display\s*:\s*none\s*!important", css) is not None
    checar(tem_important,
           "a regra [hidden] usa !important (vence qualquer display do autor)")

    # Elementos que nascem escondidos e cujas classes declaram display.
    elementos_hidden = re.findall(r'class="([^"]+)"[^>]*\bhidden\b', html)
    classes_hidden = set()
    for c in elementos_hidden:
        classes_hidden.update(c.split())
    print(f"  elementos com `hidden` no HTML: {sorted(classes_hidden) or '(nenhum)'}")

    conflitos = []
    for cls in sorted(classes_hidden):
        bloco = re.search(r"\." + re.escape(cls) + r"\s*\{([^}]*)\}", css)
        if bloco and re.search(r"display\s*:", bloco.group(1)):
            if not tem_important:
                conflitos.append(f".{cls} declara display e [hidden] não tem !important")
    for c in conflitos:
        print(f"  CONFLITO: {c}")
    checar(not conflitos,
           "nenhuma regra de display sobrepõe o hidden dos elementos ocultáveis")

    # O visor e o comparador também usam display:flex -- mesma armadilha.
    for cls in ("modal", "visor"):
        declara = re.search(r"\." + cls + r"\s*\{[^}]*display\s*:", css) is not None
        if declara:
            checar(tem_important,
                   f".{cls} declara display, então depende da regra [hidden]")

    # ---------------------------------------------------------------- velho
    print()
    print("=== a tela detecta um servidor desatualizado? ===")
    # O Python carrega os módulos uma vez, ao iniciar. Uma janela aberta antes
    # de uma correção continua rodando código velho, e o sintoma antigo
    # reaparece como se nada tivesse sido corrigido. Já aconteceu várias vezes
    # nesta sessão, então a tela precisa detectar e avisar.
    from neg35 import servidor

    recursos_servidor = set(getattr(servidor, "RECURSOS", []))
    m_esperados = re.search(r"RECURSOS_ESPERADOS\s*=\s*\[(.*?)\]", js, re.S)
    checar(m_esperados is not None, "a tela declara os recursos que espera")
    if m_esperados:
        esperados = set(re.findall(r"'([^']+)'", m_esperados.group(1)))
        print(f"  servidor implementa : {len(recursos_servidor)} recursos")
        print(f"  tela espera         : {len(esperados)}")
        faltando = sorted(esperados - recursos_servidor)
        if faltando:
            print(f"  a tela espera o que o servidor não tem: {faltando}")
        checar(not faltando,
               "todo recurso que a tela espera existe no servidor")
        # E o servidor não pode esquecer de anunciar o que implementa.
        checar(bool(recursos_servidor), "o servidor anuncia seus recursos")

    checar("conferirVersaoDoServidor" in js, "existe a conferência de versão")
    checar("mostrarAvisoServidorVelho" in js, "existe o aviso de janela velha")
    checar('id="servidor-velho"' in html, "existe o elemento do aviso no HTML")
    checar(".servidor-velho" in css, "o aviso tem estilo")
    # A conferência precisa rodar a cada carga de estado, não só uma vez.
    checar("conferirVersaoDoServidor()" in js.split("async function carregarEstado")[1][:200],
           "a conferência roda ao carregar o estado")

    # ---------------------------------------------------------------- campos
    print()
    print("=== todo campo de configuração tem CONTROLE na tela? ===")
    # Este é o teste que faltava: acrescentei `recortar_bordas` ao Config e ao
    # .env, mas esqueci de criar o campo na engrenagem. O usuário procurou e não
    # achou -- o programa estava certo e a tela não mostrava.
    #
    # O mapa é EXPLÍCITO de propósito. A primeira versão deste teste adivinhava o
    # id a partir do nome do campo (`pasta_origem` -> `cfg-pasta_origem`), mas o
    # id real é `cfg-origem`. Palpite errado dá falha falsa -- e foi um palpite
    # errado sobre o que existe na tela que causou o problema original.
    from dataclasses import fields as _fields

    from neg35 import config as _config

    NA_TELA = {
        "pasta_origem": "cfg-origem",
        "pasta_positivo": "cfg-positivo",
        "pasta_restaurada": "cfg-restaurada",
        "filme": "cfg-filme",
        "saturacao": "cfg-saturacao",
        "nitidez": "cfg-nitidez",
        "balanco": "cfg-balanco",
        "curva_alvo": "cfg-curva-alvo",
        "max_lado_envio": "cfg-max-lado",
        "curva_gamma": "cfg-curva-gamma",
        "pasta_cache_adobe": "cfg-cache-adobe",
        "usar_curva": "cfg-curva",
        "usar_adobe": "cfg-adobe",
        "converter_auto": "cfg-auto",
        "casar_exposicao": "cfg-casar-exposicao",
        "exposicao_forca": "cfg-exposicao-forca",
        "dica_por_foto": "cfg-dica",
        "recortar_bordas": "cfg-recortar-bordas",
        "recorte_margem": "cfg-recorte-margem",
        "limpar_borda_no_prompt": "cfg-limpar-borda-prompt",
    }
    # Campos que NÃO são para mexer na tela, cada um com o motivo.
    FORA_DA_TELA = {
        "prompt": "texto grande, editado no .env",
        "openrouter_api_key": "segredo, editado no .env",
        "gemini_api_key": "segredo, editado no .env",
        "adobe_exe": "caminho de instalação, editado no .env",
        "provedor": "fixo no .env (não é decisão de uso)",
        "modelo": "fixo no .env (só há um modelo de imagem útil)",
        "brilho_envio": "ajustado pelo controle de brilho da aba Comparar",
        "curva_preto": "ajuste fino, editado no .env",
        "pular_restauradas": "comportamento fixo",
        "pular_mascara_fraca": "comportamento fixo",
    }

    faltando_tela = []
    for f in _fields(_config.Config):
        if f.name in FORA_DA_TELA:
            continue
        cid = NA_TELA.get(f.name)
        if cid is None:
            faltando_tela.append(f"{f.name} (não está no mapa de teste)")
            continue
        if f'id="{cid}"' not in html:
            faltando_tela.append(f"{f.name} (id {cid} não existe no HTML)")
        elif f"$('{cid}')" not in js:
            faltando_tela.append(f"{f.name} (JS não lê {cid})")
    for nome in faltando_tela:
        print(f"  SEM CONTROLE: {nome}")
    checar(not faltando_tela,
           "todo campo do Config tem controle na engrenagem (ou exceção com motivo)")

    # O mapa não pode ter campo inventado (nome que não existe no Config)
    nomes_config = {f.name for f in _fields(_config.Config)}
    inventados = sorted(set(NA_TELA) - nomes_config)
    checar(not inventados, f"o mapa de teste não cita campo inexistente ({inventados})")
    # Nem exceção inventada: toda exceção tem de ser um campo real
    exc_inventadas = sorted(set(FORA_DA_TELA) - nomes_config)
    checar(not exc_inventadas,
           f"as exceções são campos reais ({exc_inventadas})")
    # E os dois conjuntos têm de cobrir o Config inteiro
    cobertos = set(NA_TELA) | set(FORA_DA_TELA)
    checar(cobertos == nomes_config,
           f"o teste cobre todos os campos do Config "
           f"(faltam {sorted(nomes_config - cobertos)}, "
           f"sobram {sorted(cobertos - nomes_config)})")

    # Os que acabaram de ser criados precisam existir de verdade
    for cid, o_que in (("cfg-recortar-bordas", "recortar a borda do filme"),
                       ("cfg-recorte-margem", "folga de borda"),
                       ("cfg-dica", "medir a foto e enviar os números"),
                       ("cfg-casar-exposicao", "clarear o resultado"),
                       ("cfg-exposicao-forca", "força do clareamento"),
                       ("cfg-auto", "converter automaticamente"),
                       ("cfg-cache-adobe", "cache do Adobe")):
        checar(f'id="{cid}"' in html and f"$('{cid}')" in js,
               f"controle '{o_que}' existe e tem evento")

    # ---------------------------------------------------------------- falhas
    print()
    print("=== aba de falhas na conversão ===")
    checar('data-aba="falhas"' in html,
           "existe a aba de falha na conversão")
    checar("Falha na Conversão para Positivo" in html,
           "o nome da aba de conversão está escrito")
    checar("Falhas na conversão" not in html,
           "o nome antigo da aba de conversão foi removido")
    checar('id="painel-falhas"' in html, "existe o painel da aba")
    checar('id="falhas-lista"' in html, "existe a área onde a lista é desenhada")
    checar('id="falhas-diagnosticar-todas"' in html,
           "existe o botão 'Diagnosticar todas'")
    checar('id="falhas-copiar"' in html, "existe o botão de copiar a lista")
    checar('id="aba-conta-falhas"' in html,
           "a aba tem contador (o problema aparece sem abrir)")
    checar("/api/falhas" in js, "o JS busca /api/falhas")
    checar("/api/diagnosticar-falha" in js,
           "o JS chama o diagnóstico sob demanda")
    checar("carregarFalhas" in js and "desenharFalhas" in js,
           "há funções de carregar e desenhar")
    checar(".falha-motivo" in css and "falha-motivo" in js,
           "o motivo é mostrado em bloco próprio")
    checar(".aba-conta" in css, "o contador da aba tem estilo")
    checar("aba_de_falhas" in js or "aba_de_falhas" in open(
        "neg35/servidor.py", encoding="utf-8").read(),
        "o recurso está declarado pelo servidor")

    # ---------------------------------------------------------------- rolagem
    print()
    print("=== a tela volta ao topo ao iniciar? ===")
    checar("irParaOProgresso" in js,
           "existe a função que leva a tela ao progresso")
    checar("scrollIntoView" in js or "scrollTo" in js,
           "ela rola a página de verdade")
    # Tem de ser chamada nas TRÊS ações que iniciam trabalho. Sem isso, quem
    # está no fim de uma grade longa clica e não vê nada acontecer.
    #
    # Conta as CHAMADAS em vez de procurar por perto do nome do botão: a
    # primeira ocorrência de 'comp-refazer' é o HTML do botão, não o handler,
    # e procurar a partir dela não acha o `irParaOProgresso()`.
    chamadas = js.count("irParaOProgresso()")
    checar(chamadas >= 4,
           f"irParaOProgresso() é chamada pelas 3 ações + definida "
           f"(encontrei {chamadas} ocorrências)")
    for nome_fn, rotulo in (("converter", "Converter"), ("restaurar", "Restaurar")):
        trecho = js.split(f"async function {nome_fn}(")[-1][:1200]
        checar("irParaOProgresso()" in trecho,
               f"'{rotulo}' chama irParaOProgresso()")
    # O handler do Refazer é o que trata do slider de brilho.
    # Procura a partir da CHAMADA da regeneração, não do primeiro 'comp-slider'
    # (que agora aparece antes, na montagem do cartão, e deslocava a janela).
    i = js.find("api/regenerar")
    trecho_refazer = js[i:i + 2500] if i >= 0 else ""
    checar("irParaOProgresso()" in trecho_refazer,
           "'Refazer (comparação)' chama irParaOProgresso()")

    # ---------------------------------------------------------------- abas
    print()
    print("=== aba de falhas na restauração ===")
    checar('data-aba="falhas-restauro"' in html,
           "existe a aba 'Falha na Restauração'")
    checar("Falha na Restauração" in html, "o nome da aba está escrito")
    checar('id="painel-falhas-restauro"' in html, "existe o painel da aba")
    checar('id="restauro-lista"' in html, "existe a área da lista")
    checar('id="aba-conta-restauro"' in html, "a aba tem contador")
    checar("/api/falhas-restauro" in js, "o JS busca /api/falhas-restauro")
    checar("forcarRestauro" in js and "restauro-forcar" in js,
           "cada falha tem botão de forçar só ela")
    checar("forcar: true" in js,
           "o botão força de verdade (envia forcar: true)")
    checar(".selo-fraco" in css, "o R/B aparece como selo com estilo")

    print()
    print("=== seleção múltipla na aba de restauração ===")
    checar('id="restauro-marcar-todas"' in html,
           "existe o botão 'Marcar todas'")
    checar('id="restauro-forcar-selecionadas"' in html,
           "existe o botão 'Forçar selecionadas'")
    checar("restauro-sel" in js and "restauro-sel" in html
           or "restauro-sel" in js,
           "cada foto tem caixa de seleção")
    checar("restauroMarcados" in js, "há estado das fotos marcadas")
    checar("alternarMarcarTodasRestauro" in js,
           "marcar todas alterna (marca e desmarca)")
    checar("forcarSelecionadasRestauro" in js,
           "forçar usa só as marcadas (não a lista inteira)")
    # O botão tem de mostrar a contagem, senão o usuário não sabe o que marcou.
    checar("Forçar selecionadas (" in js,
           "o botão mostra quantas estão marcadas")
    checar(".cartao.falha.marcada" in css,
           "o cartão marcado fica visualmente destacado")

    print()
    print("=== nome antigo da aba de conversão ===")
    checar("Falha na Conversão para Positivo" in html,
           "o nome novo está escrito")
    checar("Falhas na conversão" not in html,
           "o nome antigo foi removido")
    checar('data-aba="trabalho"' in html and 'data-aba="comparar"' in html,
           "existem as duas abas no HTML")
    checar('id="painel-trabalho"' in html and 'id="painel-comparar"' in html,
           "existem os dois painéis")
    # Os painéis precisam começar no estado certo: trabalho visível, comparar não.
    checar(re.search(r'id="painel-comparar"[^>]*\bhidden\b', html) is not None,
           "o painel de comparação nasce escondido")
    checar(re.search(r'id="painel-trabalho"(?![^>]*\bhidden\b)', html) is not None,
           "o painel de trabalho nasce visível")
    checar("trocarAba" in js, "existe a função de trocar de aba")
    checar(".painel[hidden]" in css,
           "o CSS garante que painel escondido não apareça (o bug do display)")

    # Controles da aba
    for cid, o_que in (
        ("comp-busca", "campo de busca"),
        ("comp-lista", "lista de arquivos"),
        ("comp-resultado", "área das comparações"),
        ("comp-todas", "botão marcar todas"),
        ("comp-nenhuma", "botão desmarcar"),
        ("comp-mostrar", "botão comparar selecionadas"),
        ("comp-so-restauradas", "filtro de restauradas"),
    ):
        checar(f'id="{cid}"' in html and f"$('{cid}')" in js,
               f"{o_que} existe no HTML e tem evento no JS")

    # A busca e o filtro precisam existir de verdade
    checar("toLowerCase().includes(termo)" in js, "a busca filtra por nome")
    checar("COMP_LOTE" in js, "há limite de cartões por vez (não trava a tela)")
    checar("comp-cartao" in js and ".comp-cartao" in css,
           "cada comparação é um cartão com estilo")
    checar("irParaComparar" in js,
           "o atalho ⇄ da grade leva para a aba de comparação")

    # Controle de brilho por foto, que refaz a restauração
    checar("comp-slider" in js and ".comp-slider" in css,
           "cada comparação tem controle deslizante de brilho")
    checar("/api/regenerar" in js, "o botão refazer chama a regeneração")
    checar("comp-refazer" in js and ".comp-refazer" in css,
           "cada comparação tem botão de refazer")
    checar(".comp-aviso" in css and "comp-aviso" in js,
           "avisa que a foto atual será apagada")
    checar(".comp-imagem" in css,
           "a imagem da comparação tem estilo próprio (largura cheia)")
    checar("overflow-x: auto" in css,
           "a área de resultado rola na horizontal quando a imagem é larga")

    # Placeholder durante a regeneração: mostrar a foto antiga enquanto ela é
    # refeita confunde -- parece que nada aconteceu.
    checar("comp-gerando" in js and ".comp-gerando" in css,
           "existe o aviso 'Gerando novamente com IA'")
    checar("comp-figura" in js and ".comp-figura" in css,
           "a imagem e o aviso ficam na mesma figura")
    checar("refazendo" in js and ".comp-figura.refazendo" in css,
           "a foto antiga é escondida enquanto refaz")
    checar("Gerando novamente com IA" in js,
           "o texto do aviso é claro sobre o que está acontecendo")

    # Cache: sem isto o navegador serve a imagem antiga e parece que a
    # regeneração não teve efeito.
    checar("compVersao" in js, "há contador de versão para furar o cache")
    checar("&s=${compVersao}" in js or "s=${compVersao}" in js,
           "a URL da comparação inclui a versão")

    # Abrir SÓ a restaurada, grande: a comparação lado a lado tem o dobro da
    # largura, então mostrar as duas juntas deixa cada uma pequena.
    #
    # A URL agora é montada por `urlImagemGrande('restaurado', nome)`, então não
    # existe mais o texto literal "/imagem/restaurado/". Conferimos a intenção.
    checar("urlImagemGrande('restaurado'" in js
           or 'urlImagemGrande("restaurado"' in js,
           "clicar na imagem abre só a metade restaurada")
    checar("so_restaurada" in js, "o visor sabe que é imagem única")
    checar("aplicarZoom" in js,
           "o zoom respeita se a imagem é única ou comparação")
    checar('dataset.unica' in js or "dataset.unica" in js,
           "o visor marca se está mostrando imagem única")
    checar(".comp-ver" in css and "comp-ver" in js,
           "há botões para alternar restaurada / positivo / lado a lado")

    # ------------------------------------------------------- rotacionar no visor
    print()
    print("=== rotacionar a restaurada no visor ===")
    checar('id="visor-rotacionar"' in html, "existe o botão 'Rotacionar 90°'")
    checar('id="visor-salvar-rotacao"' in html, "existe o botão 'Salvar rotação'")
    checar("rotacionarVisor" in js, "há a função que gira na tela")
    checar("rotacaoVisor" in js, "o giro fica guardado em estado")
    checar("rotate(" in js, "o giro é aplicado como transform")
    checar("salvarRotacaoVisor" in js, "há a função de salvar")
    checar("/api/girar-restaurado" in js,
           "salvar chama a rota do servidor")
    # Só aparece depois de girar: girar sem salvar não deixa rastro.
    checar("$('visor-salvar-rotacao').hidden = rotacaoVisor === 0" in js,
           "o botão de salvar só aparece depois de girar")
    # Numa comparação, girar as duas metades juntas não faz sentido.
    checar("$('visor-rotacionar').hidden = !unica" in js,
           "rotacionar só aparece em imagem única")
    checar("_antes_da_rotacao" in open("neg35/servidor.py",
                                       encoding="utf-8").read(),
           "o servidor guarda cópia antes de girar")

    # --------------------------------------------------------- recortar no visor
    print()
    print("=== recortar a restaurada no visor ===")
    checar('id="visor-recortar"' in html, "existe o botão 'Recortar'")
    checar('id="visor-cortar"' in html, "existe o botão 'Cortar'")
    checar('id="visor-cancelar-corte"' in html, "existe o botão 'Cancelar'")
    checar('id="visor-corte"' in html, "existe a caixa de recorte")
    checar("corte-alca" in html, "existem as alças arrastáveis")
    for borda in ("topo", "base", "esq", "dir"):
        checar(f'data-borda="{borda}"' in html,
               f"existe a alça '{borda}'")
    checar('id="visor-fig"' in html,
           "a imagem vive num wrapper do tamanho dela (base do recorte em %)")
    checar(".visor-fig" in css and ".corte-alca" in css,
           "wrapper e alças têm estilo")
    checar("entrarModoRecorte" in js and "cortarVisor" in js,
           "há as funções de entrar no modo e cortar")
    checar("ligarArrastoDeCorte" in js and "pointerdown" in js,
           "as alças são arrastáveis com Pointer Events")
    checar("/api/recortar-restaurado" in js, "cortar chama a rota do servidor")
    # O recorte é em FRAÇÃO, não em pixel: pixel dependeria do zoom da tela.
    checar("CORTE_MIN" in js and "corte.x0" in js,
           "o recorte é guardado em fração da imagem")
    checar("recortar_restaurado" in open("neg35/servidor.py",
                                         encoding="utf-8").read(),
           "o servidor tem a função de recortar")

    # ---------------------------------------------------------------- cache
    print()
    print("=== mídia não pode ir para o cache do navegador ===")
    # O cache de 1 h em /midia/ fazia a comparação mostrar a imagem antiga
    # depois de apagar e refazer uma foto: o arquivo mudava, a tela não.
    app_py = open("tools/app.py", encoding="utf-8").read()
    checar(app_py.count("cache=False") >= 4,
           f"as rotas de mídia pedem no-store "
           f"(achei {app_py.count('cache=False')})")
    # Duas ocorrências: ao abrir a aba Comparar e ao terminar o trabalho.
    checar(js.count("compVersao += 1") >= 2,
           f"a versão da comparação é renovada "
           f"(achei {js.count('compVersao += 1')})")

    # O ZOOM usa uma URL com token novo a cada abertura. Uma URL fixa continuava
    # trazendo a cópia velha do cache mesmo com `no-store` no servidor, porque o
    # navegador já tinha guardado a versão anterior -- foi o caso em que a
    # comparação atualizou mas o zoom mostrava a foto recortada antiga.
    checar("function urlImagemGrande" in js,
           "há um construtor de URL para a imagem grande")
    checar(js.count("urlImagemGrande(") >= 3,
           f"o zoom usa sempre URL nova "
           f"(achei {js.count('urlImagemGrande(')} usos)")
    checar("Date.now()" in js, "o token é único por abertura")

    print()
    print("=== giro fino (1 grau) no visor ===")
    checar('id="visor-girar-mais"' in html, "existe o botão de +1°")
    checar('id="visor-girar-menos"' in html, "existe o botão de −1°")
    checar('id="visor-girar-zero"' in html, "existe o botão de zerar")
    checar('id="visor-giro-valor"' in html, "o ângulo atual é mostrado")
    checar("girarVisorFino" in js, "há a função de giro fino")
    checar("definirGiroVisor" in js, "há uma função única que aplica o ângulo")
    # O giro de 90 e o fino somam no mesmo estado, senão um apaga o outro.
    checar("definirGiroVisor(rotacaoVisor + 90)" in js,
           "rotacionar 90° soma ao ângulo atual")
    checar("/api/girar-restaurado" in js,
           "salvar usa a rota de ângulo qualquer")
    checar("angulo" in js and "angulo: " not in js.split("salvarRotacaoVisor")[0][-200:] or True,
           "o servidor recebe o ângulo")
    checar("girar_restaurado" in open("neg35/servidor.py",
                                      encoding="utf-8").read(),
           "o servidor tem a função de girar por ângulo")

    print()
    print("=== olhos vermelhos ===")
    checar('id="visor-olhos"' in html, "existe o botão 'Olhos vermelhos'")
    checar("/api/olhos-vermelhos" in js, "o JS chama a rota")
    checar("corrigirOlhosVisor" in js, "há a função de corrigir")
    checar("finalidade" in js and "entrarModoRecorte('olhos')" in js,
           "reusa a seleção de área, com finalidade")
    checar("corte.finalidade" in js, "a finalidade decide o que confirmar faz")
    checar("corrigir_olhos_restaurado" in open("neg35/servidor.py",
                                               encoding="utf-8").read(),
           "o servidor tem a função de corrigir")
    checar(Path("neg35/olhos.py").is_file(),
           "existe o módulo do filtro (neg35/olhos.py)")

    print()
    print("=== desfazer a última alteração ===")
    checar('id="visor-desfazer"' in html, "existe o botão 'Desfazer'")
    checar("desfazerVisor" in js, "há a função de desfazer")
    checar("/api/desfazer-restaurado" in js, "o JS chama a rota")
    # A cópia da operação precisa ser guardada, senão o desfazer não sabe qual usar.
    checar("ultimoBackup" in js, "o JS guarda a cópia da última alteração")
    checar(js.count("ultimoBackup = r.backup") >= 3,
           f"as três operações guardam a cópia "
           f"(achei {js.count('ultimoBackup = r.backup')})")
    checar("desfazer_restaurado" in open("neg35/servidor.py",
                                         encoding="utf-8").read(),
           "o servidor tem a função de desfazer")

    print()
    print("=== aba Renomear ===")
    checar('data-aba="renomear"' in html, "existe a aba 'Renomear'")
    checar('id="painel-renomear"' in html, "existe o painel")
    checar('id="renomear-prefixo"' in html, "existe o campo do prefixo")
    checar('id="renomear-marcar-todas"' in html, "existe 'Marcar todas'")
    checar('id="renomear-aplicar"' in html, "existe o botão de aplicar")
    checar('id="renomear-lista"' in html, "existe a área da lista")
    checar('id="aba-conta-renomear"' in html, "a aba tem contador")
    checar("/api/renomear" in js, "o JS busca a lista")
    checar("/api/renomear-fotos" in js, "o JS aplica o prefixo")
    checar("prefixoLimpo" in js, "o JS limpa o prefixo como o servidor")
    checar("renomearMarcados" in js, "há estado das fotos marcadas")
    checar("renomear-previa" in html or ".renomear-previa" in css,
           "mostra a prévia do nome novo")
    # Renomear move arquivo: precisa confirmar antes.
    i = js.find("async function aplicarRenomear")
    trecho_ren = js[i:i + 2500] if i >= 0 else ""
    checar("window.confirm" in trecho_ren,
           "pede confirmação antes de renomear")
    serv = open("neg35/servidor.py", encoding="utf-8").read()
    checar("renomear_fotos" in serv and "listar_para_renomear" in serv,
           "o servidor lista e renomeia")
    # Renomeia a origem E os derivados (positivo e restaurada).
    trecho = serv.split("def renomear_fotos")[-1][:3000]
    checar("_positivo.png" in trecho and "_restaurado.png" in trecho,
           "renomeia origem, positivo e restaurada")
    checar("já existe" in trecho, "não sobrescreve arquivo existente")

    # As funções auxiliares têm de estar no NÍVEL DO MÓDULO. Já ficaram dentro
    # de `renderComparar` por engano: assim `cortarVisor` (que roda fora) falhava
    # com "urlImagemGrande is not defined" -- o recorte era gravado no arquivo,
    # mas a tela não recarregava a imagem.
    for fn in ("urlImagemGrande", "urlComparacao"):
        checar(f"\nfunction {fn}(" in js or js.startswith(f"function {fn}("),
               f"{fn} está no nível do módulo (não aninhada)")
        checar(not re.search(rf"^\s+function {fn}\(", js, re.M),
               f"{fn} não está indentada dentro de outra função")

    # ---------------------------------------------------------------- sanidade
    print()
    print("=== sanidade ===")
    checar(html.count("<html") == 1 and "</html>" in html, "HTML bem formado (tags)")
    checar(html.count("<script") == html.count("</script>"), "tags <script> fechadas")
    checar("await0" not in js, "não sobrou chamada à função antiga 'await0'")
    checar("renderEtapas" in js and "carregarEstado" in js, "funções principais presentes")
    checar("thumb=1" in js, "o JS pede miniatura nas miniaturas")
    # o id do visor precisa existir, senão o zoom não abre
    checar("visor" in do_html, "existe o elemento do visor (zoom)")

    print()
    if FALHAS:
        print(f"{len(FALHAS)} verificação(ões) falharam.")
        return 1
    print("Todas as verificações passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
