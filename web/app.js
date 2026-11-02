/* neg35 -- interface. JavaScript sem dependências. */
'use strict';

/**
 * Recursos que ESTA versão da tela precisa que o servidor tenha.
 *
 * Se o servidor não tiver algum, é porque a janela foi aberta antes de uma
 * correção: o Python carrega os módulos uma vez e não recarrega. Sem este
 * aviso, o sintoma antigo reaparece e parece que a correção não funcionou --
 * já aconteceu mais de uma vez.
 */
const RECURSOS_ESPERADOS = [
  'mascara_medida_no_negativo',
  'cache_adobe_configuravel',
  'pastas_de_saida_testadas',
  'chave_do_env',
  'cor_no_envio',
  'abrir_pasta_no_explorer',
  'copiar_caminho',
  'dica_por_foto',
  'refazer_com_brilho',
  'zoom_so_restaurada',
  'recorte_de_borda',
  'aba_de_falhas',
  'aba_falha_restauro',
  'rotacionar_restaurada',
  'recortar_restaurada',
];

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

let estado = null;
let trabalho = null;
let timer = null;
let zoom = 1;
let automaticoFeito = false;
let mostrarRestauradas = false;
// item aberto no visor, para saber se há restaurada para comparar
let visorItem = null;
// Giro da imagem no visor, em graus (0, 90, 180, 270). Só visual: para valer no
// arquivo, use o botão "Salvar rotação".
let rotacaoVisor = 0;
// Cópia criada pela última alteração (recorte, giro, olhos). O botão Desfazer
// manda este nome, para voltar exatamente ao estado anterior a ESSA alteração --
// e não à mais recente da pasta, que poderia ser de outra operação.
let ultimoBackup = null;

/**
 * Desfaz a última alteração feita na restaurada.
 *
 * A correção de olhos vermelhos, o recorte e o giro já guardam uma cópia antes de
 * gravar; este botão usa a cópia da última operação. É o que permite "não gostei,
 * volta como estava" sem depender de abrir a pasta e copiar arquivo na mão.
 */
async function desfazerVisor() {
  if (!visorItem || !visorItem.nome) return;
  const botao = $('visor-desfazer');
  try {
    botao.disabled = true;
    botao.textContent = 'Desfazendo…';
    const r = await post('/api/desfazer-restaurado', {
      nome: visorItem.nome,
      backup: ultimoBackup || undefined,
    });
    toast(`Desfeito (${r.tamanho[0]}x${r.tamanho[1]})`, 'ok');
    ultimoBackup = null;
    sairModoRecorte();
    $('visor-img').src = urlImagemGrande('restaurado', visorItem.nome);
    compVersao += 1;
    if (!$('painel-comparar').hidden) renderComparar();
  } catch (e) {
    toast(e.message, 'erro');
  } finally {
    botao.disabled = false;
    botao.textContent = 'Desfazer';
  }
}

/* ---------------------------------------------------------------- util */
function toast(msg, tipo = '') {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast ' + tipo;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, tipo === 'erro' ? 9000 : 4200);
}

async function api(rota, opcoes) {
  const r = await fetch(rota, opcoes);
  const txt = await r.text();
  let dados = {};
  try { dados = txt ? JSON.parse(txt) : {}; } catch { dados = { erro: txt }; }
  if (!r.ok) throw new Error(dados.erro || `HTTP ${r.status}`);
  return dados;
}

const post = (rota, corpo) => api(rota, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(corpo || {}),
});

/* ---------------------------------------------------------------- estado */
async function carregarEstado() {
  estado = await api('/api/estado');
  conferirVersaoDoServidor();
  renderPastas();
  renderResumo();
  renderEtapas();
  return estado;
}

function renderPastas() {
  const p = estado.pastas;
  const marca = (ok) => ok ? '' : ' <span class="nao">(não existe)</span>';
  // Cada caminho tem duas ações: clicar abre a pasta no Explorer; o botão ao
  // lado copia o caminho. A cópia existe porque abrir o Explorer FALHA em
  // alguns ambientes (sessão restrita não deixa criar janelas), e nesses casos
  // copiar é o que resolve.
  const alvo = (qual, rotulo, caminho, existe) => `
    <span class="pasta-grupo">
      <span class="pasta-alvo" data-qual="${qual}"
            title="Abrir esta pasta no Explorer${existe ? '' : ' (ainda não existe)'}">
        ${rotulo} <b>${esc(caminho)}</b>${marca(existe)}
      </span>
      <button class="pasta-copiar" data-qual="${qual}"
              title="Copiar este caminho">&#10697;</button>
    </span>`;
  $('pastas').innerHTML =
    alvo('origem', 'origem', p.origem, p.origem_existe) +
    alvo('positivo', 'positivos', p.positivo, p.positivo_existe) +
    alvo('restaurado', 'restauradas', p.restaurada, p.restaurada_existe);

  document.querySelectorAll('.pasta-alvo').forEach((el) => {
    el.addEventListener('click', async () => {
      const qual = el.dataset.qual;
      try {
        const r = await api('/api/abrir-pasta?qual=' + encodeURIComponent(qual));
        toast(`Abrindo ${r.aberto}`, 'ok');
      } catch (e) {
        // Se não deu para abrir o Explorer, copia o caminho: é a saída
        // prática, e evita o usuário ficar sem nada.
        toast('Não consegui abrir o Explorer aqui — copiando o caminho.', 'erro');
        try {
          const c = await api('/api/copiar-caminho?qual=' + encodeURIComponent(qual));
          toast(`Caminho copiado: ${c.copiado}`, 'ok');
        } catch (e2) { toast(e2.message, 'erro'); }
      }
    });
  });

  document.querySelectorAll('.pasta-copiar').forEach((b) => {
    b.addEventListener('click', async (ev) => {
      ev.stopPropagation();
      const qual = b.dataset.qual;
      try {
        const r = await api('/api/copiar-caminho?qual=' + encodeURIComponent(qual));
        toast(`Caminho copiado: ${r.copiado}`, 'ok');
      } catch (e) { toast(e.message, 'erro'); }
    });
  });
}

function renderResumo() {
  const c = estado.contagens;
  const adobe = estado.adobe_disponivel ? 'ativo' : 'ausente';
  const cartoes = [
    ['total de fotos', c.total, ''],
    ['com positivo', c.com_positivo, ''],
    ['faltam converter', c.faltam_positivo, c.faltam_positivo ? 'destaque' : ''],
    ['faltam restaurar', c.faltam_restaurar, c.faltam_restaurar ? 'destaque' : ''],
    ['restauradas', c.com_restaurado, ''],
    ['Adobe', adobe, ''],
  ];
  $('resumo').innerHTML = cartoes.map(([rot, num, cls]) => `
    <div class="cartao ${cls}">
      <div class="num">${esc(num)}</div>
      <div class="rot">${esc(rot)}</div>
    </div>`).join('');
}

function renderEtapas() {
  const c = estado.contagens;
  const cfg = estado.config;

  // etapa 1
  const jaTem = c.com_positivo;
  $('cont-converter').textContent = `${jaTem} de ${c.total} prontos`;
  if (c.faltam_positivo > 0) {
    // Deixa explícito que os já feitos são pulados -- era a dúvida principal:
    // "ele vai refazer tudo?" Não: só os que faltam.
    const pulados = jaTem > 0
      ? ` Os <b>${jaTem}</b> que já têm positivo são pulados — só os <b>${c.faltam_positivo}</b> que faltam serão processados.`
      : '';
    $('ajuda-converter').innerHTML =
      `Faltam <b>${c.faltam_positivo}</b> foto(s).${pulados}` +
      (cfg.usar_adobe && estado.adobe_disponivel
        ? ' O Adobe DNG Converter está ativo para consertar DNG com bloco defeituoso.'
        : '');
    $('btn-converter').disabled = trabalhoAtivo();
    $('btn-converter').textContent = jaTem > 0
      ? `Converter as ${c.faltam_positivo} que faltam`
      : 'Converter pendentes';
  } else if (c.total > 0) {
    $('ajuda-converter').textContent = 'Tudo já tem positivo. Nada a fazer nesta etapa.';
    $('btn-converter').disabled = true;
    $('btn-converter').textContent = 'Converter pendentes';
  } else {
    $('ajuda-converter').textContent =
      'Nenhuma foto encontrada na pasta de origem. Confira o caminho na engrenagem.';
    $('btn-converter').disabled = true;
  }

  // etapa 2
  const pendentes = estado.pendentes_restaurar;
  const chaveOk = cfg.tem_chave;
  $('cont-restaurar').textContent = `${pendentes.length} para restaurar`;
  if (!pendentes.length) {
    $('ajuda-restaurar').textContent =
      c.total === 0 ? 'Nenhuma foto encontrada na pasta de origem.'
                    : 'Tudo já foi restaurado.';
    $('btn-restaurar').disabled = true;
  } else if (!chaveOk) {
    $('ajuda-restaurar').innerHTML =
      '<b>Falta a chave de API</b> no <span class="mono">.env</span>. ' +
      'Sem ela não dá para chamar a IA.';
    $('btn-restaurar').disabled = true;
  } else {
    $('ajuda-restaurar').innerHTML =
      `Marque as fotos que valem a pena. Cada uma custa cerca de ` +
      `<b>US$ ${precoUnit().toFixed(3)}</b> com <span class="mono">${esc(cfg.modelo)}</span>.`;
    $('btn-restaurar').disabled = selecionados().length === 0;
  }

  $('etapa-converter').classList.toggle('oculta', c.total === 0);
  renderGrade();
}

// preço por imagem. Buscado uma vez no início: precisa estar pronto quando
// renderEtapas roda, porque ela é SÍNCRONA (chamar await dentro dela deixaria
// um Promise onde se espera número).
let _precoUnit = null;

async function carregarPreco() {
  if (_precoUnit !== null) return _precoUnit;
  try {
    const r = await api('/api/custo?nomes=x');
    _precoUnit = r.usd || 0;
  } catch { _precoUnit = 0; }
  return _precoUnit;
}

function precoUnit() { return _precoUnit === null ? 0 : _precoUnit; }

/* ---------------------------------------------------------------- grade */
function selecionados() {
  return [...document.querySelectorAll('.celula input:checked')].map((i) => i.dataset.nome);
}

function renderGrade() {
  const porNome = Object.fromEntries(estado.itens.map((i) => [i.nome, i]));

  // A grade mostra os pendentes. Com "mostrar também as já restauradas"
  // marcado, inclui as prontas -- é o que permite abrir a comparação de uma
  // foto que já foi processada.
  const pendentes = estado.pendentes_restaurar;
  const prontas = estado.itens.filter((i) => i.tem_restaurado).map((i) => i.nome);
  const nomes = mostrarRestauradas ? [...pendentes, ...prontas] : pendentes;

  const grade = $('grade');
  const marcadosAntes = new Set(selecionados());

  if (!nomes.length) {
    grade.innerHTML = '';
    $('rodape').style.display = estado.contagens.total ? 'none' : 'flex';
    $('vazio').hidden = estado.contagens.total > 0;
    if (estado.contagens.total === 0) {
      $('vazio').innerHTML =
        'Nenhuma foto na pasta de origem.<br>' +
        'Abra as configurações (engrenagem) e confira o caminho.';
    }
    atualizarCusto();
    return;
  }
  $('vazio').hidden = true;
  $('rodape').style.display = 'flex';

  grade.innerHTML = nomes.map((nome) => {
    const it = porNome[nome] || {};
    const pronto = !!it.tem_restaurado;
    const marcado = marcadosAntes.has(nome) ? 'checked' : '';
    const selo = pronto
      ? '<span class="selo pronto">restaurada</span>'
      : (it.tipo === 'DNG' ? '<span class="selo dng">DNG</span>'
                           : '<span class="selo">JPG</span>');
    // A miniatura mostra a restaurada quando já existe -- é o resultado final.
    const origemMini = pronto ? 'restaurado' : 'positivo';
    const grande = pronto
      ? `/midia/restaurado/${encodeURIComponent(nome)}`
      : `/midia/positivo/${encodeURIComponent(nome)}`;
    return `
      <div class="celula ${marcado ? 'marcada' : ''}" data-nome="${esc(nome)}">
        <input class="marca-sel" type="checkbox" data-nome="${esc(nome)}" ${marcado}>
        ${pronto ? '<span class="selo-comp" title="Comparar lado a lado">&#8646;</span>' : ''}
        <img class="mini" src="/midia/${origemMini}/${encodeURIComponent(nome)}?thumb=1"
             alt="${esc(nome)}" loading="lazy"
             data-grande="${grande}"
             data-nome="${esc(nome)}" data-pronto="${pronto ? '1' : '0'}"
             data-positivo="/midia/positivo/${encodeURIComponent(nome)}"
             data-restaurado="${pronto ? `/midia/restaurado/${encodeURIComponent(nome)}` : ''}">
        <div class="rodape">
          <span class="nome" title="${esc(nome)}">${esc(nome)}</span>
          ${selo}
        </div>
      </div>`;
  }).join('');

  grade.querySelectorAll('.marca-sel').forEach((chk) => {
    chk.addEventListener('change', () => {
      chk.closest('.celula').classList.toggle('marcada', chk.checked);
      atualizarCusto();
    });
  });

  grade.querySelectorAll('.mini').forEach((img) => {
    img.addEventListener('click', () => abrirVisor(img));
  });

  // Atalho na grade: clicar no ícone ⇄ leva para a aba Comparar já com esta
  // foto marcada, em vez de abrir o modal antigo.
  grade.querySelectorAll('.selo-comp').forEach((b) => {
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      const nome = b.closest('.celula').dataset.nome;
      irParaComparar(nome);
    });
  });

  atualizarCusto();
}

async function atualizarCusto() {
  const sel = selecionados();
  $('sel-info').textContent = sel.length === 1
    ? '1 selecionada' : `${sel.length} selecionadas`;
  if (sel.length === 0) {
    $('btn-restaurar').disabled = true;
  } else if (diagnostico && !diagnostico.pode_restaurar) {
    // Gravar o resultado é pré-requisito: sem isso, o dinheiro da IA se perde.
    $('btn-restaurar').disabled = true;
    $('custo-info').textContent = 'pasta de restauradas sem escrita — veja o aviso no topo';
    return;
  } else {
    $('btn-restaurar').disabled = !estado.config.tem_chave || trabalhoAtivo();
  }
  if (!sel.length) {
    $('custo-info').textContent = '';
    return;
  }
  try {
    const r = await api('/api/custo?nomes=' + encodeURIComponent(sel.join(',')));
    $('custo-info').textContent =
      `custo estimado US$ ${r.usd.toFixed(3)} (${r.fonte})`;
  } catch {
    $('custo-info').textContent = '';
  }
}

/* ------------------------------------------------- servidor velho? */
/**
 * Confere se o servidor tem os recursos que esta tela espera.
 *
 * O Python carrega os módulos uma vez, ao iniciar. Uma janela aberta antes de
 * uma correção continua rodando o código velho, e o sintoma antigo reaparece
 * como se nada tivesse sido corrigido. Avisar é melhor que deixar o usuário
 * refazer o diagnóstico.
 */
function conferirVersaoDoServidor() {
  if (!estado || !estado.recursos) {
    // Servidor antigo a ponto de não devolver a lista.
    mostrarAvisoServidorVelho(['(o servidor não informa seus recursos)']);
    return;
  }
  const tem = new Set(estado.recursos);
  const faltando = RECURSOS_ESPERADOS.filter((r) => !tem.has(r));
  if (faltando.length) {
    mostrarAvisoServidorVelho(faltando);
  }
}

function mostrarAvisoServidorVelho(faltando) {
  const caixa = $('servidor-velho');
  if (!caixa) return;
  caixa.innerHTML = `
    <div class="velho-topo"><b>A janela do programa está desatualizada</b></div>
    <p class="velho-texto">
      Esta tela é mais nova que o programa que está rodando. O Python carrega o
      código uma vez, ao iniciar, e não recarrega sozinho — então correções
      recentes não estão valendo nesta janela.
      <br><br>
      <b>Feche a janela do <span class="mono">run.cmd</span> e abra de novo.</b>
    </p>
    <div class="velho-falta mono">faltando: ${faltando.map(esc).join(', ')}</div>`;
  caixa.hidden = false;
}

/* ======================================================== aba comparar */
// Estado da aba de comparação.
let compBusca = '';
let compSoRestauradas = true;
// Quantos cartões desenhar de uma vez. Cada cartão é uma imagem montada no
// servidor; 12 mantém a página leve mesmo com dezenas de fotos.
const COMP_LOTE = 12;
let compMostrando = COMP_LOTE;
// Nome da foto que está sendo refeita, para a aba de comparação se atualizar
// sozinha quando o trabalho terminar.
let compRefazendo = null;
//
// Sem ele o navegador serve a imagem do cache: a URL da comparação é a mesma, e
// o usuário refazia com brilho diferente e continuava vendo a foto antiga --
// parecia que a regeneração não tinha efeito.
let compVersao = 0;
// Estado da aba de falhas: a última lista recebida do servidor.
let falhasDados = null;
// Estado da aba de falhas de restauração.
let falhasRestauro = null;
// Quais fotos da aba de restauração estão marcadas para forçar.
// Set de nomes: marcar/desmarcar é O(1) e não duplica.
let restauroMarcados = new Set();
// Estado da aba Renomear.
let renomearDados = null;
let renomearMarcados = new Set();

function trocarAba(nome) {
  document.querySelectorAll('.aba').forEach((b) => {
    b.classList.toggle('ativa', b.dataset.aba === nome);
  });
  $('painel-trabalho').hidden = nome !== 'trabalho';
  $('painel-comparar').hidden = nome !== 'comparar';
  $('painel-falhas').hidden = nome !== 'falhas';
  $('painel-falhas-restauro').hidden = nome !== 'falhas-restauro';
  $('painel-renomear').hidden = nome !== 'renomear';
  if (nome === 'comparar') {
    // Renova a versão a cada abertura da aba. As imagens de comparação são
    // montadas no servidor a partir de DOIS arquivos que mudam (positivo e
    // restaurado); sem isso, apagar e refazer uma foto deixava a comparação
    // mostrando a versão antiga -- parece que o refazer não funcionou.
    compVersao += 1;
    renderComparar();
  }
  if (nome === 'falhas') carregarFalhas();
  if (nome === 'falhas-restauro') carregarFalhasRestauro();
  if (nome === 'renomear') carregarRenomear();
}

/** Itens que podem ser comparados: precisam de positivo. */
function itensComparaveis() {
  if (!estado) return [];
  return estado.itens.filter((i) => i.tem_positivo);
}

// ============================ falhas na conversão ============================

/**
 * Busca a lista de negativos que não geraram positivo.
 *
 * O servidor junta duas fontes: o registro com o motivo (gravado quando uma
 * conversão falha) e uma varredura ao vivo da pasta de origem. A varredura é o
 * que pega as falhas anteriores ao registro existir.
 */
async function carregarFalhas() {
  const caixa = $('falhas-lista');
  const resumo = $('falhas-resumo');
  caixa.innerHTML = '<p class="dica">Lendo a pasta de origem…</p>';
  try {
    const d = await api('/api/falhas');
    falhasDados = d;
    desenharFalhas();
  } catch (e) {
    caixa.innerHTML = `<p class="erro">Não consegui listar: ${esc(e.message)}</p>`;
    resumo.textContent = '';
  }
}

function desenharFalhas() {
  const caixa = $('falhas-lista');
  const resumo = $('falhas-resumo');
  const contador = $('aba-conta-falhas');
  const d = falhasDados;
  if (!d) return;

  const n = d.total || 0;
  // Contador na aba, para o problema aparecer sem precisar abrir a aba.
  if (contador) {
    contador.textContent = String(n);
    contador.hidden = n === 0;
  }

  if (n === 0) {
    resumo.innerHTML = 'Nenhum negativo pendente: todos geraram positivo. ';
    caixa.innerHTML = '<section class="cartao"><p class="dica">'
      + 'Nada a mostrar. Se uma conversão falhar, ela aparece aqui.</p></section>';
    return;
  }

  const semMotivo = d.falhas.filter((f) => f.sem_motivo).length;
  resumo.innerHTML = `<b>${n}</b> negativo(s) sem positivo. `
    + (semMotivo ? `${semMotivo} sem motivo registrado — use <b>Diagnosticar</b>. ` : '')
    + `<span class="mono">${esc(d.origem || '')}</span>`;

  caixa.innerHTML = d.falhas.map((f, i) => {
    const mb = f.tamanho ? (f.tamanho / 1024 / 1024).toFixed(1) + ' MB' : '—';
    return `
    <section class="cartao falha" data-nome="${esc(f.nome)}">
      <div class="falha-topo">
        <div>
          <b>${esc(f.nome)}</b>
          <div class="mono dica">${esc(f.arquivo || '')} · ${mb}</div>
        </div>
        <div class="falha-acoes">
          <button class="btn pequeno falha-diag" data-nome="${esc(f.nome)}">
            Diagnosticar
          </button>
        </div>
      </div>
      <p class="falha-motivo ${f.sem_motivo ? 'vazio' : ''}">
        ${f.sem_motivo
          ? 'Motivo não registrado. Clique em <b>Diagnosticar</b> para o programa tentar abrir e dizer o que aconteceu.'
          : esc(f.motivo)}
      </p>
      ${f.quando ? `<p class="dica mono">registrado em ${esc(f.quando)}</p>` : ''}
    </section>`;
  }).join('');

  caixa.querySelectorAll('.falha-diag').forEach((b) => {
    b.addEventListener('click', () => diagnosticarFalha(b.dataset.nome, b));
  });
}

/**
 * Pede ao servidor para tentar abrir UM negativo e registrar o motivo.
 *
 * É sob demanda porque abrir um DNG de 14 MB leva segundos; fazer isso na
 * abertura da aba travaria a tela.
 */
async function diagnosticarFalha(nome, botao) {
  const cartao = botao.closest('.cartao');
  const alvo = cartao.querySelector('.falha-motivo');
  const original = alvo.innerHTML;
  try {
    botao.disabled = true;
    alvo.classList.remove('vazio');
    alvo.innerHTML = '<span class="pulsando">abrindo o arquivo…</span>';
    const r = await post('/api/diagnosticar-falha', { nome });
    alvo.innerHTML = esc(r.motivo || '(sem motivo)');
    alvo.classList.toggle('ok', !!r.ok);
    if (r.ok) {
      toast(`${nome}: converteu agora`, 'ok');
      await carregarEstado();
    } else {
      toast(`${nome}: continua falhando`, 'erro');
    }
    await carregarFalhas();
  } catch (e) {
    alvo.innerHTML = original;
    toast(e.message, 'erro');
    botao.disabled = false;
  }
}

/** Diagnostica todos, um por vez. */
async function diagnosticarTodasFalhas(botao) {
  if (!falhasDados || !falhasDados.falhas.length) return;
  const nomes = falhasDados.falhas.map((f) => f.nome);
  try {
    botao.disabled = true;
    for (let i = 0; i < nomes.length; i++) {
      botao.textContent = `Diagnosticando ${i + 1} de ${nomes.length}…`;
      const cartao = document.querySelector(
        `.cartao.falha[data-nome="${CSS.escape(nomes[i])}"]`);
      const b = cartao && cartao.querySelector('.falha-diag');
      if (b) await diagnosticarFalha(nomes[i], b);
    }
  } finally {
    botao.disabled = false;
    botao.textContent = 'Diagnosticar todas';
    await carregarFalhas();
  }
}

// ============================== renomear ==============================

/**
 * Busca os negativos que ainda não receberam prefixo.
 *
 * "Não renomeado" vem do registro do servidor, não do formato do nome: o nome
 * original já tem underscores (`20261012_133746`), então adivinhar pelo padrão
 * daria erro.
 */
async function carregarRenomear() {
  const caixa = $('renomear-lista');
  caixa.innerHTML = '<p class="dica">Lendo a pasta de origem…</p>';
  try {
    renomearDados = await api('/api/renomear');
    // Descarta marcações de fotos que não estão mais na lista.
    const atuais = new Set(renomearDados.itens.map((i) => i.nome));
    for (const n of [...renomearMarcados]) {
      if (!atuais.has(n)) renomearMarcados.delete(n);
    }
    desenharRenomear();
  } catch (e) {
    caixa.innerHTML = `<p class="erro">Não consegui listar: ${esc(e.message)}</p>`;
    $('renomear-resumo').textContent = '';
  }
}

/** Prefixo como o servidor vai gravar (mesma limpeza: espaço vira hífen). */
function prefixoLimpo() {
  return ($('renomear-prefixo').value || '')
    .trim()
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, '')
    .replace(/ /g, '-')
    .replace(/__+/g, '_')
    .replace(/^[-_.]+|[-_.]+$/g, '');
}

function desenharRenomear() {
  const caixa = $('renomear-lista');
  const resumo = $('renomear-resumo');
  const contador = $('aba-conta-renomear');
  const d = renomearDados;
  if (!d) return;

  const n = d.itens.length;
  if (contador) {
    contador.textContent = String(n);
    contador.hidden = n === 0;
  }
  if ($('renomear-resumo')) {
    $('renomear-resumo').innerHTML = n === 0
      ? 'Todas as fotos desta pasta já receberam prefixo.'
      : `<b>${n}</b> foto(s) ainda sem prefixo · `
        + `<span class="mono">${esc(d.origem || '')}</span>`;
  }

  if (n === 0) {
    caixa.innerHTML = '<section class="cartao"><p class="dica">'
      + 'Nada a renomear. Fotos novas na pasta de origem aparecem aqui.'
      + '</p></section>';
    atualizarBotaoRenomear();
    return;
  }

  const p = prefixoLimpo();
  caixa.innerHTML = d.itens.map((i) => {
    const marcado = renomearMarcados.has(i.nome);
    const partes = [];
    if (i.tem_positivo) partes.push('positivo');
    if (i.tem_restaurado) partes.push('restaurada');
    const acompanha = partes.length
      ? ` <span class="selo-fraco">também renomeia: ${partes.join(' + ')}</span>`
      : '';
    const novo = p ? `${esc(p)}_${esc(i.nome)}` : `${esc(i.nome)}`;
    return `
    <section class="cartao falha${marcado ? ' marcada' : ''}"
             data-nome="${esc(i.nome)}">
      <div class="falha-topo">
        <label class="restauro-marca">
          <input type="checkbox" class="renomear-sel" data-nome="${esc(i.nome)}"
                 ${marcado ? 'checked' : ''}>
          <span>
            <b>${esc(i.nome)}</b>${acompanha}
            <div class="dica mono">${i.arquivos.map(esc).join(' · ')}</div>
          </span>
        </label>
      </div>
      <p class="renomear-previa">vai ficar: <b>${novo}</b></p>
    </section>`;
  }).join('');

  caixa.querySelectorAll('.renomear-sel').forEach((c) => {
    c.addEventListener('change', () => {
      const nome = c.dataset.nome;
      if (c.checked) renomearMarcados.add(nome);
      else renomearMarcados.delete(nome);
      const cartao = c.closest('.cartao');
      if (cartao) cartao.classList.toggle('marcada', c.checked);
      atualizarBotaoRenomear();
    });
  });

  atualizarBotaoRenomear();
}

/** Mantém o botão coerente: precisa de prefixo E de pelo menos uma marcada. */
function atualizarBotaoRenomear() {
  const botao = $('renomear-aplicar');
  if (!botao) return;
  const n = renomearMarcados.size;
  const p = prefixoLimpo();
  botao.disabled = n === 0 || !p;
  botao.textContent = n === 0
    ? 'Renomear selecionadas'
    : `Renomear ${n} selecionada(s)`;
  const aviso = $('renomear-aviso');
  if (aviso) {
    aviso.textContent = p
      ? `O nome ficará: ${p}_<nome atual>`
      : 'Digite o prefixo (o que está escrito na etiqueta da tira).';
  }
  const marcar = $('renomear-marcar-todas');
  if (marcar && renomearDados) {
    const total = renomearDados.itens.length;
    marcar.textContent = (total > 0 && n === total)
      ? 'Desmarcar todas' : 'Marcar todas';
  }
}

function alternarMarcarTodasRenomear() {
  if (!renomearDados) return;
  const nomes = renomearDados.itens.map((i) => i.nome);
  const todas = nomes.length > 0 && renomearMarcados.size === nomes.length;
  renomearMarcados = todas ? new Set() : new Set(nomes);
  desenharRenomear();
}

/** Aplica o prefixo nas fotos marcadas. */
async function aplicarRenomear() {
  const p = prefixoLimpo();
  const nomes = [...renomearMarcados];
  if (!p) return toast('digite o prefixo da tira', 'erro');
  if (!nomes.length) return toast('marque ao menos uma foto', 'erro');

  // Renomear move arquivos: confirma, porque desfazer não é um clique.
  if (!window.confirm(
    `Renomear ${nomes.length} foto(s) para começar com "${p}_"?\n\n`
    + `Serão renomeados os arquivos da origem E o positivo/restaurada de cada `
    + `uma. Nada é sobrescrito: se o nome já existir, aquela foto é pulada.`)) {
    return;
  }

  const botao = $('renomear-aplicar');
  try {
    botao.disabled = true;
    botao.textContent = 'Renomeando…';
    const r = await post('/api/renomear-fotos', { nomes, prefixo: p });
    const falhas = r.falhas || 0;
    if (falhas) {
      const detalhe = r.resultados
        .filter((x) => !x.ok)
        .map((x) => `${x.nome}: ${x.msg}`)
        .join('\n');
      toast(`${r.ok} renomeada(s), ${falhas} falha(s). ${detalhe}`,
            falhas === r.total ? 'erro' : '');
    } else {
      toast(`${r.ok} foto(s) renomeada(s) com "${r.prefixo}_"`, 'ok');
    }
    renomearMarcados.clear();
    await carregarEstado();     // a lista de fotos mudou de nome
    await carregarRenomear();
  } catch (e) {
    toast(e.message, 'erro');
    botao.disabled = false;
  }
}



// ======================= falhas na restauração =======================

async function carregarFalhasRestauro() {
  const caixa = $('restauro-lista');
  const resumo = $('restauro-resumo');
  caixa.innerHTML = '<p class="dica">Lendo o registro…</p>';
  try {
    const d = await api('/api/falhas-restauro');
    falhasRestauro = d;
    desenharFalhasRestauro();
  } catch (e) {
    caixa.innerHTML =
      `<p class="erro">Não consegui listar: ${esc(e.message)}</p>`;
    resumo.textContent = '';
  }
}

function desenharFalhasRestauro() {
  const caixa = $('restauro-lista');
  const resumo = $('restauro-resumo');
  const contador = $('aba-conta-restauro');
  const d = falhasRestauro;
  if (!d) return;

  const n = d.total || 0;
  if (contador) {
    contador.textContent = String(n);
    contador.hidden = n === 0;
  }
  if ($('restauro-limite')) {
    $('restauro-limite').textContent = String(d.limite_mascara).replace('.', ',');
  }

  if (n === 0) {
    restauroMarcados.clear();
    resumo.innerHTML = 'Nenhuma falha de restauração registrada.';
    caixa.innerHTML = '<section class="cartao"><p class="dica">'
      + 'Se uma restauração falhar, ela aparece aqui.</p></section>';
    atualizarBotaoForcarSelecionadas();
    return;
  }

  // Descarta marcações de fotos que não estão mais na lista.
  const nomesAtuais = new Set(d.falhas.map((f) => f.nome));
  for (const nome of [...restauroMarcados]) {
    if (!nomesAtuais.has(nome)) restauroMarcados.delete(nome);
  }

  const fracas = d.falhas.filter((f) => f.mascara_fraca).length;
  resumo.innerHTML = `<b>${n}</b> foto(s) com falha na restauração`
    + (fracas ? `, sendo <b>${fracas}</b> por máscara fraca` : '')
    + '. Marque as que quiser e use <b>Forçar selecionadas</b>.';

  caixa.innerHTML = d.falhas.map((f) => {
    const rb = (f.r_b !== null && f.r_b !== undefined)
      ? `<span class="selo-fraco">R/B ${Number(f.r_b).toFixed(2)}</span>` : '';
    const marcado = restauroMarcados.has(f.nome);
    return `
    <section class="cartao falha${marcado ? ' marcada' : ''}"
             data-nome="${esc(f.nome)}">
      <div class="falha-topo">
        <label class="restauro-marca">
          <input type="checkbox" class="restauro-sel" data-nome="${esc(f.nome)}"
                 ${marcado ? 'checked' : ''}
                 ${f.tem_positivo ? '' : 'disabled title="sem positivo"'}>
          <span>
            <b>${esc(f.nome)}</b> ${rb}
            <div class="dica mono">${esc(f.motivo || '')}</div>
          </span>
        </label>
        <div class="falha-acoes">
          <button class="btn pequeno restauro-forcar"
                  data-nome="${esc(f.nome)}"
                  ${f.tem_positivo ? '' : 'disabled title="sem positivo"'}>
            Forçar só esta
          </button>
        </div>
      </div>
      ${f.mascara_fraca ? `
      <p class="falha-motivo vazio">
        <b>Máscara fraca:</b> o negativo perdeu a correção de cor laranja
        (R/B abaixo de ${d.limite_mascara}). A IA <b>não recupera</b> esses
        casos — ela inventa detalhes e o resultado engana. Forçar é pago.
      </p>` : (f.detalhe ? `<p class="falha-motivo vazio">${esc(f.detalhe)}</p>` : '')}
      ${f.quando ? `<p class="dica mono">registrado em ${esc(f.quando)}</p>` : ''}
    </section>`;
  }).join('');

  caixa.querySelectorAll('.restauro-forcar').forEach((b) => {
    b.addEventListener('click', () => forcarRestauro(b.dataset.nome, b));
  });
  caixa.querySelectorAll('.restauro-sel').forEach((c) => {
    c.addEventListener('change', () => {
      const nome = c.dataset.nome;
      if (c.checked) restauroMarcados.add(nome);
      else restauroMarcados.delete(nome);
      const cartao = c.closest('.cartao');
      if (cartao) cartao.classList.toggle('marcada', c.checked);
      atualizarBotaoForcarSelecionadas();
    });
  });

  atualizarBotaoForcarSelecionadas();
}

/** Mantém o rótulo do botão com a contagem de marcadas. */
function atualizarBotaoForcarSelecionadas() {
  const botao = $('restauro-forcar-selecionadas');
  if (!botao) return;
  const n = restauroMarcados.size;
  botao.disabled = n === 0;
  botao.textContent = n === 0 ? 'Forçar selecionadas'
    : `Forçar selecionadas (${n})`;
  const marcar = $('restauro-marcar-todas');
  if (marcar) {
    const total = falhasRestauro ? falhasRestauro.falhas.length : 0;
    const todas = total > 0 && n === total;
    marcar.textContent = todas ? 'Desmarcar todas' : 'Marcar todas';
  }
}

/** Marca ou desmarca todas as fotos da lista. */
function alternarMarcarTodasRestauro() {
  if (!falhasRestauro) return;
  const nomes = falhasRestauro.falhas
    .filter((f) => f.tem_positivo).map((f) => f.nome);
  const todas = nomes.length > 0 && restauroMarcados.size === nomes.length;
  restauroMarcados = todas ? new Set() : new Set(nomes);
  desenharFalhasRestauro();
}

/**
 * Força a restauração de UMA foto, ignorando a checagem de máscara.
 *
 * Reusa `/api/restaurar` com `forcar: true` -- é o mesmo caminho da caixa
 * "Forçar mesmo com máscara fraca" da tela principal, então não há lógica nova
 * para manter em dois lugares.
 */
async function forcarRestauro(nome, botao) {
  if (trabalhoAtivo()) return avisarOcupado('restaurar');
  try {
    botao.disabled = true;
    botao.textContent = 'Forçando…';
    await post('/api/restaurar', { nomes: [nome], forcar: true });
    toast(`Restaurando ${nome} mesmo com máscara fraca…`);
    trabalho = { tipo: 'restauracao', terminado: false, total: 1,
                 feitos: 0, progresso: 0 };
    renderProgresso(trabalho);
    irParaOProgresso();
    comecarPolling();
  } catch (e) {
    toast(e.message, 'erro');
    botao.disabled = false;
    botao.textContent = 'Forçar restauração';
  }
}

/**
 * Força a restauração das fotos MARCADAS, uma por vez.
 *
 * Cada foto é uma chamada paga, então pedimos confirmação mostrando o custo
 * estimado e o aviso de que máscara fraca tende a produzir detalhe inventado.
 */
async function forcarSelecionadasRestauro(botao) {
  const nomes = [...restauroMarcados];
  if (!nomes.length) return toast('marque ao menos uma foto');
  const custo = (nomes.length * 0.04).toFixed(2);
  if (!window.confirm(
    `Forçar a restauração de ${nomes.length} foto(s)?\n\n`
    + `Isso é PAGO (cerca de US$ ${custo}) e, em casos de máscara fraca, `
    + `a IA tende a inventar detalhes.`)) {
    return;
  }
  if (trabalhoAtivo()) return avisarOcupado('restaurar');
  try {
    botao.disabled = true;
    await post('/api/restaurar', { nomes, forcar: true });
    toast(`Restaurando ${nomes.length} foto(s) à força…`);
    trabalho = { tipo: 'restauracao', terminado: false, total: nomes.length,
                 feitos: 0, progresso: 0 };
    renderProgresso(trabalho);
    irParaOProgresso();
    comecarPolling();
    restauroMarcados.clear();
    atualizarBotaoForcarSelecionadas();
  } catch (e) {
    toast(e.message, 'erro');
    botao.disabled = false;
  }
}

/**
 * URL única da imagem grande de uma foto.
 *
 * SEMPRE com um token novo. O servidor já manda `no-store`, mas isso não apaga o
 * que o navegador guardou ANTES de a regra existir: uma URL fixa continua
 * servindo a cópia velha até ela expirar. Foi exatamente o que aconteceu — a
 * comparação (que tem `s=`) atualizou, e o zoom (sem `s=`) continuou mostrando a
 * foto recortada antiga.
 *
 * Fica no NÍVEL DO MÓDULO, e não dentro de `renderComparar`. Já esteve lá dentro
 * por engano: assim só existia durante aquela função, e salvar o recorte (que
 * roda fora dela) falhava com "urlImagemGrande is not defined" — o recorte era
 * gravado no arquivo, mas a tela não conseguia recarregar a imagem nova.
 */
function urlImagemGrande(tipo, nome) {
  return `/imagem/${tipo}/${encodeURIComponent(nome)}?w=2600&s=${Date.now()}`;
}

/** URL da comparação lado a lado, com a versão da tela. */
function urlComparacao(nome, largura) {
  return `/midia/comparar/${encodeURIComponent(nome)}`
    + `?w=${largura || 2200}&s=${compVersao}`;
}

function renderComparar() {
  if (!estado) return;
  const todos = itensComparaveis();
  const comRestaurada = todos.filter((i) => i.tem_restaurado);
  const base = compSoRestauradas ? comRestaurada : todos;

  const termo = compBusca.trim().toLowerCase();
  const filtrados = termo
    ? base.filter((i) => i.nome.toLowerCase().includes(termo))
    : base;

  $('comp-contador').textContent =
    termo
      ? `${filtrados.length} de ${base.length}`
      : `${base.length} foto(s)`;
  $('comp-dica').textContent = compSoRestauradas
    ? `${comRestaurada.length} com restaurada · ${todos.length - comRestaurada.length} sem`
    : `${todos.length} com positivo`;

  const lista = $('comp-lista');
  if (!filtrados.length) {
    lista.innerHTML = '<div class="comp-vazio">' +
      (todos.length
        ? 'Nenhuma foto corresponde à busca.'
        : 'Nenhum positivo gerado ainda. Converta primeiro na outra aba.') +
      '</div>';
    $('comp-resultado').innerHTML = '';
    return;
  }

  // Mantém o que já estava marcado, para a busca não desmarcar nada.
  const marcados = new Set(
    [...document.querySelectorAll('.comp-item input:checked')].map((i) => i.nome || i.dataset.nome)
  );

  lista.innerHTML = filtrados.map((i) => {
    const marcado = marcados.has(i.nome) ? 'checked' : '';
    const falta = i.tem_restaurado
      ? ''
      : '<span class="faltando">sem restaurada</span>';
    return `<label class="comp-item">
        <input type="checkbox" data-nome="${esc(i.nome)}" ${marcado}>
        <span class="nome">${esc(i.nome)}</span>
        ${falta}
      </label>`;
  }).join('');

  // Cartões do que estiver marcado
  const escolhidos = filtrados.filter((i) => marcados.has(i.nome));
  desenharCartoes(escolhidos);
}

function desenharCartoes(escolhidos) {
  const caixa = $('comp-resultado');
  const viaveis = escolhidos.filter((i) => i.tem_restaurado);
  if (!viaveis.length) {
    caixa.innerHTML = escolhidos.length
      ? '<div class="comp-vazio">As fotos marcadas ainda não têm restaurada. ' +
        'Restaure na outra aba para poder comparar.</div>'
      : '';
    return;
  }

  const mostrar = viaveis.slice(0, compMostrando);
  let html = mostrar.map((i) => `
    <div class="comp-cartao" data-nome="${esc(i.nome)}">
      <div class="comp-cartao-topo">
        <b>${esc(i.nome)}</b>
        <span class="comp-modo">
          <button class="btn pequeno comp-ver ativo" data-nome="${esc(i.nome)}"
                  data-tipo="restaurado">Restaurada</button>
          <button class="btn pequeno comp-ver" data-nome="${esc(i.nome)}"
                  data-tipo="positivo">Positivo</button>
          <button class="btn pequeno comp-ver" data-nome="${esc(i.nome)}"
                  data-tipo="comparar">Lado a lado</button>
        </span>
      </div>
      <div class="comp-figura">
        <img class="comp-imagem"
             src="/midia/comparar/${encodeURIComponent(i.nome)}?w=2200&s=${compVersao}"
             alt="positivo e restaurado lado a lado: ${esc(i.nome)}"
             loading="lazy"
             data-nome="${esc(i.nome)}"
             data-grande="/midia/comparar/${encodeURIComponent(i.nome)}?w=2600&s=${compVersao}">
        <div class="comp-gerando" hidden>
          <span class="comp-gerando-texto">Gerando novamente com IA…</span>
          <span class="comp-gerando-sub">a foto atual foi apagada e está sendo refeita</span>
        </div>
      </div>
      <div class="comp-ajuste">
        <span class="comp-legenda">
          esquerda: positivo &nbsp;·&nbsp; direita: restaurado pela IA
        </span>
        <label class="comp-brilho">
          <span>Escuro</span>
          <input type="range" min="0.4" max="2" step="0.05" value="1"
                 class="comp-slider" data-nome="${esc(i.nome)}">
          <span>Claro</span>
          <output class="mono comp-valor">1.00</output>
        </label>
        <button class="btn pequeno primario comp-refazer" data-nome="${esc(i.nome)}">
          Refazer com este ajuste
        </button>
      </div>
      <p class="comp-aviso" hidden>
        Refazendo: a foto restaurada atual será <b>apagada</b> e enviada de novo
        à IA.
      </p>
    </div>`).join('');

  if (viaveis.length > mostrar.length) {
    html += `<div style="text-align:center;margin:18px 0">
        <button class="btn" id="comp-mais">
          Mostrar mais ${Math.min(COMP_LOTE, viaveis.length - mostrar.length)}
          (${mostrar.length} de ${viaveis.length})
        </button>
      </div>`;
  }
  caixa.innerHTML = html;

  // Clicar na imagem abre SÓ a metade restaurada, grande.
  //
  // Antes abria a comparação inteira, e as duas metades ficavam pequenas --
  // "praticamente não tem zoom". Abrindo só a restaurada, ela ocupa a largura
  // toda e fica ~2,5x maior na tela.
  caixa.querySelectorAll('.comp-imagem').forEach((img) => {
    img.addEventListener('click', () => abrirVisor({
      dataset: {
        grande: urlImagemGrande('restaurado', img.dataset.nome),
        nome: img.dataset.nome,
        pronto: '0',
        so_restaurada: '1',
      },
      alt: img.dataset.nome,
    }));
  });

  // Os botões trocam o que a imagem mostra no PRÓPRIO cartão.
  caixa.querySelectorAll('.comp-ver').forEach((b) => {
    b.addEventListener('click', () => {
      const nome = b.dataset.nome;
      const tipo = b.dataset.tipo;
      const cartao = b.closest('.comp-cartao');
      const img = cartao.querySelector('.comp-imagem');
      cartao.querySelectorAll('.comp-ver').forEach((o) => {
        o.classList.toggle('ativo', o === b);
      });
      if (tipo === 'comparar') {
        img.src = urlComparacao(nome, 2200);
        img.dataset.grande = urlComparacao(nome, 2600);
      } else {
        img.src = `/imagem/${tipo}/${encodeURIComponent(nome)}`
          + `?w=2200&s=${compVersao}`;
        // Sempre com token novo: o botão do cartão também abre o zoom, e URL
        // fixa traria a versão antiga do cache.
        img.dataset.grande = urlImagemGrande(tipo, nome);
      }
      img.dataset.mostrando = tipo;
    });
  });

  // controle de brilho: atualiza o número enquanto arrasta, e refaz no botão
  caixa.querySelectorAll('.comp-slider').forEach((s) => {
    const cartao = s.closest('.comp-cartao');
    const saida = cartao.querySelector('.comp-valor');
    const atualizar = () => { saida.textContent = Number(s.value).toFixed(2); };
    s.addEventListener('input', atualizar);
    atualizar();
  });
  caixa.querySelectorAll('.comp-refazer').forEach((b) => {
    b.addEventListener('click', async () => {
      const cartao = b.closest('.comp-cartao');
      const nome = b.dataset.nome;
      const brilho = Number(cartao.querySelector('.comp-slider').value);
      const aviso = cartao.querySelector('.comp-aviso');
      const figura = cartao.querySelector('.comp-figura');
      const gerando = cartao.querySelector('.comp-gerando');
      try {
        b.disabled = true;
        aviso.hidden = false;
        // Troca a imagem pelo aviso: mostrar a foto antiga enquanto ela está
        // sendo refeita confunde -- parece que nada aconteceu.
        figura.classList.add('refazendo');
        gerando.hidden = false;
        await post('/api/regenerar', { nome, brilho, forcar: true });
        toast(`Refazendo ${nome} com brilho ${brilho.toFixed(2)}…`);
        trabalho = { tipo: 'restauracao', terminado: false, total: 1,
                     feitos: 0, progresso: 0 };
        compRefazendo = nome;
        renderProgresso(trabalho);
        // Mesmo motivo do botão Restaurar: a barra fica no topo da página, e
        // quem está no meio da lista de comparações não veria nada acontecendo.
        irParaOProgresso();
        comecarPolling();
      } catch (e) {
        toast(e.message, 'erro');
        b.disabled = false;
        aviso.hidden = true;
        figura.classList.remove('refazendo');
        gerando.hidden = true;
      }
    });
  });

  const mais = $('comp-mais');
  if (mais) {
    mais.addEventListener('click', () => {
      compMostrando += COMP_LOTE;
      renderComparar();
    });
  }
}

/**
 * Vai para a aba Comparar já com uma foto marcada.
 *
 * Usado pelo atalho ⇄ da grade: o usuário está olhando a lista de trabalho e
 * quer ver aquela foto comparada, sem trocar de contexto na mão.
 */
function irParaComparar(nome) {
  compBusca = '';
  const campo = $('comp-busca');
  if (campo) campo.value = '';
  compSoRestauradas = false;            // garante que a foto apareça na lista
  const chk = $('comp-so-restauradas');
  if (chk) chk.checked = false;
  trocarAba('comparar');
  // Marca a foto e desenha só ela.
  document.querySelectorAll('.comp-item input').forEach((c) => {
    c.checked = c.dataset.nome === nome;
  });
  const item = itensComparaveis().find((i) => i.nome === nome);
  if (item) desenharCartoes([item]);
  const alvo = $('comp-resultado');
  if (alvo) alvo.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ------------------------------------------------- diagnóstico das pastas */
// Guarda o último diagnóstico, para o resto do código saber se pode converter.
let diagnostico = null;

/**
 * Mostra o estado das pastas ao abrir.
 *
 * Existe porque a unidade que o Google Drive cria no Windows recusa escrita
 * por programa. Sem isto, o usuário só descobria o problema no meio da
 * conversão -- ou pior, depois de pagar a IA.
 */
async function verificarPastas() {
  let d;
  try {
    d = await api('/api/verificar-pastas');
  } catch (e) {
    return;   // sem diagnóstico: a tela segue, o erro real aparece no uso
  }
  diagnostico = d;

  const caixa = $('diagnostico');
  if (d.tudo_ok) {
    caixa.hidden = true;
    caixa.innerHTML = '';
    return;
  }

  const linha = (rot, info, exigirGravavel) => {
    const ok = info.existe && (!exigirGravavel || info.gravavel);
    const icone = ok ? '&#10003;' : '&#10007;';
    const cls = ok ? 'ok' : 'ruim';
    let detalhe = '';
    if (exigirGravavel && !info.gravavel) detalhe = esc(info.erro || 'sem escrita');
    else if (!info.existe && exigirGravavel) detalhe = 'será criada';
    else if (!info.existe) detalhe = 'não existe';
    else if (info.imagens !== undefined) detalhe = `${info.imagens} imagem(ns)`;
    const nuvem = info.na_nuvem ? ' <span class="marca-nuvem">nuvem</span>' : '';
    return `<div class="diag-linha ${cls}">
        <span class="diag-icone">${icone}</span>
        <b>${esc(rot)}</b>
        <span class="mono diag-caminho">${esc(info.caminho)}</span>${nuvem}
        <span class="diag-detalhe">${detalhe}</span>
      </div>`;
  };

  let html = '<div class="diag-topo"><b>Antes de começar</b>' +
    '<button class="btn pequeno" id="diag-fechar">Fechar</button></div>' +
    '<div class="diag-linhas">' +
    linha('Origem', d.origem, false) +
    linha('Positivos', d.positivo, true) +
    linha('Restauradas', d.restaurada, true) +
    '</div>';

  const semEscrita = !d.positivo.gravavel || !d.restaurada.gravavel;
  if (semEscrita) {
    // Só sugerimos nuvem quando o caminho realmente parece de nuvem; senão
    // mostramos os problemas observados, sem chutar a causa.
    html += '<p class="diag-ajuda">' +
      (d.dica_nuvem ? esc(d.dica_nuvem) : d.problemas.map(esc).join('<br>')) +
      '<br>Escolha abaixo onde guardar os resultados — os originais continuam onde estão.</p>';

    // Locais já testados pelo programa: só os que gravam vêm habilitados.
    const cands = d.candidatos || [];
    if (cands.length) {
      html += '<div class="locais">' + cands.map((c, i) => `
        <label class="local ${c.gravavel ? '' : 'indisponivel'}">
          <input type="radio" name="local-saida" value="${esc(c.caminho)}"
                 data-gravavel="${c.gravavel ? '1' : '0'}"
                 ${c.gravavel ? '' : 'disabled'}
                 ${i === 0 && c.gravavel ? 'checked' : ''}>
          <span class="local-texto">
            <b>${esc(c.rotulo)}</b>
            <span class="mono local-caminho">${esc(c.caminho)}</span>
            ${c.gravavel
              ? (c.ja_tem ? `<span class="local-nota">já tem ${c.ja_tem} arquivo(s)</span>` : '')
              : `<span class="local-nota ruim">${esc(c.erro)}</span>`}
          </span>
        </label>`).join('') + '</div>';
    }

    html += `<div class="local-outro">
        <label for="diag-caminho">Ou digite outro caminho completo:</label>
        <input id="diag-caminho" spellcheck="false" placeholder="C:\\Fotos\\neg35">
      </div>
      <button class="btn primario" id="diag-local">Usar esta pasta para a saída</button>
      <div class="diag-sugestao" id="diag-sugestao"></div>`;
  } else if (d.problemas.length) {
    html += '<p class="diag-ajuda">' + d.problemas.map(esc).join('<br>') + '</p>';
  }
  html += '</div>';

  caixa.innerHTML = html;
  caixa.hidden = false;

  const bf = $('diag-fechar');
  if (bf) bf.addEventListener('click', () => { caixa.hidden = true; });

  const bl = $('diag-local');
  if (bl) {
    bl.addEventListener('click', async () => {
      const digitado = ($('diag-caminho').value || '').trim();
      const marcado = document.querySelector('input[name="local-saida"]:checked');
      const caminho = digitado || (marcado ? marcado.value : '');
      try {
        bl.disabled = true;
        toast('Testando a pasta…');
        const r = await post('/api/usar-pastas-locais', { caminho });
        toast(`Saída agora em ${r.pastas.positivo}`, 'ok');
        automaticoFeito = false;
        await carregarEstado();
        await verificarPastas();
        await talvezAutomatico();
      } catch (e) {
        toast(e.message, 'erro');
      } finally {
        bl.disabled = false;
      }
    });
  }
}

/* ---------------------------------------------------------------- progresso */
const trabalhoAtivo = () => !!trabalho && !trabalho.terminado;

/**
 * Nomes legíveis das etapas, e o quanto pesam na barra.
 *
 * Para a RESTAURAÇÃO o progresso não pode ser só "arquivos concluídos": cada
 * foto passa por etapas demoradas (a IA leva de 10 a 60 s), e sem isso o
 * usuário não sabe se está travado ou trabalhando. Então mostramos a etapa e
 * avançamos a barra dentro do arquivo.
 */
const ETAPAS = {
  preparando: { rotulo: 'Preparando o positivo', frac: 0.15 },
  enviando: { rotulo: 'Enviando para a IA', frac: 0.30 },
  aguardando: { rotulo: 'Aguardando a IA responder', frac: 0.65 },
  recebendo: { rotulo: 'Recebendo e gravando', frac: 0.90 },
  abrindo: { rotulo: 'Abrindo o arquivo', frac: 0.10 },
  adobe: { rotulo: 'Convertendo com o Adobe', frac: 0.30 },
  invertendo: { rotulo: 'Invertendo o negativo', frac: 0.50 },
  pulado: { rotulo: 'Pulada', frac: 1.0 },
  pronto: { rotulo: 'Concluído', frac: 1.0 },
  erro: { rotulo: 'Erro', frac: 1.0 },
};

/**
 * Tempo decorrido na etapa atual, em segundos.
 *
 * O servidor manda `marco` (quando a etapa começou, no relógio dele) e `agora`.
 * Ao receber a primeira resposta, fixamos a diferença entre o relógio local e o
 * do servidor; depois disso o tempo anda sozinho, sem depender de novas
 * consultas nem acumular erro.
 */
let _deslocamentoRelogio = null;

function segundosDecorridos(t) {
  if (!t.marco) return 0;
  if (_deslocamentoRelogio === null && t.agora) {
    _deslocamentoRelogio = Date.now() / 1000 - t.agora;
  }
  const agora = Date.now() / 1000 - (_deslocamentoRelogio || 0);
  return Math.max(0, agora - t.marco);
}

function formatarTempo(s) {
  if (s < 60) return `${s.toFixed(0)}s`;
  const m = Math.floor(s / 60);
  return `${m}min ${Math.round(s - m * 60)}s`;
}

function renderProgresso(t) {
  const caixa = $('progresso');
  if (!t || !t.tipo) { caixa.hidden = true; return; }
  caixa.hidden = false;

  const ehRestauro = t.tipo === 'restauracao';
  const titulo = ehRestauro ? 'Restaurando com IA' : 'Convertendo para positivo';
  $('prog-titulo').textContent = t.terminado ? `${titulo} — concluído` : `${titulo}…`;
  $('prog-contagem').textContent = `${t.feitos} de ${t.total}`;

  // A barra avança por arquivo E dentro do arquivo, pela etapa atual.
  const info = ETAPAS[t.etapa] || { rotulo: t.etapa || '', frac: 0.5 };
  const base = t.total ? (t.feitos / t.total) : 0;
  const passo = t.total ? (1 / t.total) : 0;
  const dentro = t.terminado ? 1 : info.frac;
  const fracao = Math.min(1, base + passo * dentro);
  $('prog-barra').style.width = `${Math.round(fracao * 100)}%`;

  const decorrido = segundosDecorridos(t);
  const tempo = decorrido >= 1 && !t.terminado
    ? ` · ${formatarTempo(decorrido)}` : '';

  if (t.terminado) {
    $('prog-arquivo').textContent =
      `${t.ok} ok, ${t.falhas} falha(s)` +
      (t.custo ? `, US$ ${t.custo.toFixed(3)}` : '') +
      (t.segundos ? ` em ${formatarTempo(t.segundos)}` : '');
  } else {
    const rotulo = info.rotulo || t.etapa || '';
    const nome = t.arquivo_atual || '';
    const msg = t.mensagem && t.mensagem !== rotulo ? ` — ${t.mensagem}` : '';
    $('prog-arquivo').textContent = [rotulo, nome].filter(Boolean).join(': ') + msg + tempo;
  }

  // Rótulo da etapa em destaque, para o envio à IA ficar visível.
  const selo = $('prog-etapa');
  if (selo) {
    selo.textContent = t.terminado ? '' : (info.rotulo || '');
    selo.hidden = t.terminado || !info.rotulo;
  }
  // Listras animadas na barra enquanto há trabalho: sinal de que está vivo
  // mesmo quando a etapa demora (a IA leva de 10 a 60 s por foto).
  const barra = $('prog-barra');
  if (barra) barra.classList.toggle('ativo', !t.terminado);
  $('btn-parar').hidden = t.terminado;
}

// Tique separado do polling: mantém o tempo decorrido andando na tela mesmo
// entre consultas, para o usuário ver que o programa está vivo.
let tique = null;

function pararTique() {
  if (tique) { clearInterval(tique); tique = null; }
}

function comecarTique() {
  pararTique();
  tique = setInterval(() => {
    if (!trabalho || trabalho.terminado) { pararTique(); return; }
    // Redesenha para o tempo decorrido andar. O cálculo é feito a partir do
    // relógio local (ver segundosDecorridos), então não depende deste tique
    // para estar certo -- ele só evita a tela parecer parada.
    renderProgresso(trabalho);
  }, 1000);
}

function pararPolling() {
  if (timer) { clearInterval(timer); timer = null; }
  pararTique();
}

function comecarPolling() {
  pararPolling();
  comecarTique();
  timer = setInterval(async () => {
    try {
      const t = await api('/api/progresso');
      trabalho = t;
      renderProgresso(t);
      if (t.terminado) {
        pararPolling();
        mostrarResumo(t);
        // Trabalho acabou: algum arquivo pode ter sido regravado (restauração,
        // recorte, rotação). Renovar a versão força a comparação a ser buscada
        // de novo em vez de vir do cache do navegador.
        compVersao += 1;
        if (estado && !$('painel-comparar').hidden) renderComparar();
      }
    } catch { /* rede instável: tenta no próximo ciclo */ }
  }, 700);
}

/**
 * Mostra o resultado de um trabalho concluído.
 *
 * Antes, quando havia falhas, a tela dizia só "N falha(s). Veja o console
 * (F12)" -- o que obrigava o usuário a abrir o console para saber o motivo.
 * Agora o motivo aparece na própria tela, agrupado (o mesmo motivo costuma
 * valer para todas as fotos), e o resumo fica registrado na página para poder
 * ser relido depois que o aviso desaparece.
 */
function mostrarResumo(t) {
  const eraConversao = t.tipo === 'conversao';
  const acao = eraConversao ? 'positivo(s) gerado(s)' : 'restaurada(s)';
  const resultados = t.resultados || [];
  const ruins = resultados.filter((r) => !r.ok);
  const pulados = ruins.filter((r) => r.pulado);
  const falhas = ruins.filter((r) => !r.pulado);

  if (t.erro) { toast('Erro: ' + t.erro, 'erro'); return; }

  // Aviso principal: quantos deram certo.
  if (t.total) {
    const partes = [`${t.ok} ${acao}`];
    if (pulados.length) partes.push(`${pulados.length} pulada(s)`);
    if (falhas.length) partes.push(`${falhas.length} falha(s)`);
    if (!eraConversao && t.custo) partes.push(`US$ ${t.custo.toFixed(3)}`);
    const teveProblema = pulados.length || falhas.length;
    toast(partes.join(', ') + (eraConversao && t.segundos ? ` em ${t.segundos}s` : ''),
          teveProblema ? '' : 'ok');
  }

  // Detalhe: agrupa os motivos, porque o mesmo motivo vale para várias fotos.
  const porMotivo = new Map();
  for (const r of ruins) {
    const chave = r.pulado ? 'máscara fraca' : (r.msg || 'motivo desconhecido');
    if (!porMotivo.has(chave)) porMotivo.set(chave, []);
    porMotivo.get(chave).push(r.nome);
  }
  if (porMotivo.size) {
    const linhas = [];
    for (const [motivo, nomes] of porMotivo) {
      const amostra = nomes.slice(0, 3).join(', ');
      const resto = nomes.length > 3 ? ` e mais ${nomes.length - 3}` : '';
      linhas.push({ motivo, texto: `${motivo} — ${amostra}${resto}` });
    }
    registrarResultados(t, linhas, pulados.length > 0 && falhas.length === 0);
  }

  carregarEstado();
  // Se estávamos refazendo uma foto na aba de comparação, redesenha os cartões
  // para mostrar o resultado novo. O contador de versão muda a URL, forçando o
  // navegador a baixar a imagem nova em vez de servir a do cache.
  if (compRefazendo) {
    compRefazendo = null;
    compVersao += 1;
    if (estado && !$('painel-comparar').hidden) renderComparar();
  }
}

/** Guarda o resumo do último trabalho numa faixa fixa da página. */
function registrarResultados(t, linhas, soPulados) {
  const caixa = $('resultado');
  const titulo = t.tipo === 'conversao' ? 'Conversão' : 'Restauração';
  let html = `<div class="res-topo"><b>${titulo}: ${t.ok} de ${t.total} ok</b>` +
             `<button class="btn pequeno" id="res-fechar">Fechar</button></div>` +
             '<div class="res-linhas">' +
             linhas.map((l) => `<div class="res-linha ${soPulados ? 'aviso' : 'ruim'}">
                 <span class="res-motivo">${esc(l.texto)}</span>
               </div>`).join('') + '</div>';

  if (soPulados) {
    html += `<p class="res-ajuda">"Máscara fraca" significa que o negativo perdeu a
      correção de cor laranja (R/B abaixo de 2,5). A IA <b>não recupera</b> esses
      casos — ela inventa detalhes, e o resultado engana. Marque
      "Forçar mesmo com máscara fraca" se quiser tentar mesmo assim (é pago).</p>`;
  }
  caixa.innerHTML = html;
  caixa.hidden = false;
  const b = $('res-fechar');
  if (b) b.addEventListener('click', () => { caixa.hidden = true; });
}

/* ---------------------------------------------------------------- ações */
/**
 * Avisa quando já existe trabalho em andamento.
 *
 * O servidor recusa com 409 (um trabalho por vez, para o progresso não virar
 * sopa). Antes, esse 409 virava um toast com o texto cru do servidor; agora a
 * tela explica e mostra a barra, para o usuário ver o que está rodando.
 */
function avisarOcupado(qual) {
  toast(`Já existe um trabalho em andamento. Espere ele terminar ` +
        `para ${qual}.`, 'erro');
  $('progresso').hidden = false;
  if (!timer) comecarPolling();
}

/**
 * Leva a tela para o topo, onde está a barra de progresso.
 *
 * Por que: com muitas fotos a grade fica longa, e quem está embaixo na seleção
 * clica em Restaurar e não vê nada acontecer -- a barra está lá em cima, fora da
 * tela, e a impressão é que o clique não funcionou.
 *
 * Usa `scrollTo` com `block: 'start'` no painel; se o navegador não suportar o
 * comportamento suave, o `scrollTo(0, 0)` ainda funciona.
 */
function irParaOProgresso() {
  const alvo = $('progresso');
  try {
    if (alvo && !alvo.hidden && alvo.scrollIntoView) {
      alvo.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } catch {
    window.scrollTo(0, 0);
  }
}

async function converter() {
  if (trabalhoAtivo()) { avisarOcupado('converter'); return; }
  try {
    await post('/api/converter', {});
    trabalho = { tipo: 'conversao', terminado: false, total: 0, feitos: 0, progresso: 0 };
    renderProgresso(trabalho);
    irParaOProgresso();
    comecarPolling();
  } catch (e) {
    if (/andamento|409/i.test(e.message)) avisarOcupado('converter');
    else toast(e.message, 'erro');
  }
}

async function restaurar() {
  const nomes = selecionados();
  if (!nomes.length) return;

  // Não deixa chamar a IA (que é paga) se não dá para gravar o resultado.
  if (diagnostico && !diagnostico.pode_restaurar) {
    toast('Resolva o problema das pastas antes: a pasta de restauradas não aceita escrita.', 'erro');
    $('diagnostico').hidden = false;
    return;
  }

  if (trabalhoAtivo()) { avisarOcupado('restaurar'); return; }

  const forcar = $('chk-forcar').checked;
  try {
    await post('/api/restaurar', { nomes, forcar });
    trabalho = { tipo: 'restauracao', terminado: false, total: nomes.length, feitos: 0, progresso: 0 };
    renderProgresso(trabalho);
    irParaOProgresso();
    comecarPolling();
  } catch (e) {
    if (/andamento|409/i.test(e.message)) avisarOcupado('restaurar');
    else toast(e.message, 'erro');
  }
}

/* ---------------------------------------------------------------- visor */
/**
 * Abre o visor de zoom.
 *
 * Recebe o elemento <img> clicado, porque ele carrega os dados necessários:
 * qual imagem mostrar, o nome, e se existe restaurada para comparar.
 *
 * `so_restaurada=1` ajusta o visor para uma imagem ÚNICA: ela ocupa a altura
 * toda da área, em vez de caber na largura. É o que dá zoom de verdade -- a
 * comparação lado a lado tem o dobro da largura, então mostrar as duas juntas
 * deixa cada uma pequena.
 */
function abrirVisor(img) {
  const nome = img.dataset.nome || img.alt || '';
  const temRestaurado = img.dataset.pronto === '1';
  const unica = img.dataset.so_restaurada === '1';
  visorItem = { nome, temRestaurado, positivo: img.dataset.positivo,
                unica };

  zoom = 1;
  rotacaoVisor = 0;
  const alvo = $('visor-img');
  alvo.src = img.dataset.grande;
  alvo.style.width = unica ? 'auto' : '100%';
  alvo.style.height = unica ? '100%' : 'auto';
  alvo.style.maxHeight = unica ? '100%' : '';
  alvo.style.maxWidth = '100%';
  alvo.style.transform = '';
  alvo.dataset.unica = unica ? '1' : '0';
  $('visor-nome').textContent = nome;
  // O botão só faz sentido quando existe restaurada.
  $('visor-comparar').hidden = !temRestaurado;
  // Rotacionar só faz sentido numa imagem só: numa comparação, girar as duas
  // metades juntas não é o que o usuário quer.
  $('visor-rotacionar').hidden = !unica;
  $('visor-salvar-rotacao').hidden = true;   // só aparece depois de girar
  $('visor-giro-fino').hidden = !unica;
  if ($('visor-giro-valor')) $('visor-giro-valor').textContent = '0,0°';
  // Recorte e olhos vermelhos: só em imagem única e só quando existe restaurada
  // (é o arquivo que essas ações alteram).
  $('visor-recortar').hidden = !unica;
  $('visor-olhos').hidden = !unica;
  $('visor-desfazer').hidden = !unica;
  ultimoBackup = null;                       // nova foto: nada a desfazer ainda
  $('visor-cortar').hidden = true;
  $('visor-cancelar-corte').hidden = true;
  sairModoRecorte();
  $('visor').hidden = false;
}

/**
 * Gira a imagem na TELA em 90 graus (sentido horário).
 *
 * Só a visualização muda aqui. Para valer no arquivo existe o botão de salvar --
 * e é por isso que ele aparece depois de um giro: girar sem salvar não deixa
 * rastro nenhum.
 */
function rotacionarVisor() {
  definirGiroVisor(rotacaoVisor + 90);
}

/**
 * Giro FINO, de 1 grau por toque.
 *
 * Serve para negativo fotografado meio torto: 1 ou 2 graus endireitam o quadro,
 * coisa que o giro de 90 não resolve. O valor é somado ao giro de 90, então os
 * dois controles trabalham juntos.
 */
function girarVisorFino(delta) {
  definirGiroVisor(rotacaoVisor + delta);
}

/** Aplica um ângulo qualquer (graus, horário) na visualização. */
function definirGiroVisor(angulo) {
  // Normaliza para a faixa (-180, 180]: girar 370 é o mesmo que girar 10, e
  // assim o número mostrado não cresce sem parar.
  let a = angulo % 360;
  if (a > 180) a -= 360;
  if (a <= -180) a += 360;
  // Arredonda para 1 casa: o botão anda de 1 em 1, mas 90+1 pode virar 91.
  rotacaoVisor = Math.round(a * 10) / 10;

  const alvo = $('visor-img');
  alvo.style.transform = rotacaoVisor ? `rotate(${rotacaoVisor}deg)` : '';
  // Ao girar, a imagem pode passar da área visível.
  alvo.style.maxHeight = Math.abs(rotacaoVisor) > 1 ? '100vw' : '100%';

  const valor = $('visor-giro-valor');
  if (valor) {
    const sinal = rotacaoVisor > 0 ? '+' : '';
    valor.textContent = `${sinal}${rotacaoVisor.toFixed(1).replace('.', ',')}°`;
  }
  $('visor-salvar-rotacao').hidden = rotacaoVisor === 0;
  $('visor-salvar-rotacao').textContent = rotacaoVisor === 0
    ? 'Salvar rotação' : `Salvar rotação (${rotacaoVisor.toFixed(1)}°)`;
}

/* ============================ recorte no visor ============================ */

/**
 * Estado do modo de recorte, em FRAÇÃO da imagem (0..1).
 *
 * Fracao, e nao pixel, de proposito: o mesmo valor serve para a tela (qualquer
 * zoom, qualquer tamanho de janela) e para o servidor, que corta o arquivo. Se
 * fosse em pixel, o recorte dependeria do zoom em que o usuario estava.
 */
const corte = { ativo: false, x0: 0.05, y0: 0.05, x1: 0.95, y1: 0.95,
                finalidade: 'cortar' };
const CORTE_MIN = 0.05;      // 5% minimo por lado

/**
 * Entra no modo de seleção de área.
 *
 * `finalidade` decide o que o botão de confirmar faz:
 *   'cortar' -> corta o arquivo nesse retângulo;
 *   'olhos'  -> aplica a correção de olhos vermelhos só dentro do retângulo.
 *
 * A caixa de seleção é a mesma; muda o rótulo e o destino.
 */
function entrarModoRecorte(finalidade = 'cortar') {
  if (!visorItem || !visorItem.unica) return;
  corte.finalidade = finalidade;
  // O giro visual desalinha a caixa de recorte da imagem real. Como girar já
  // tem botão próprio para salvar, aqui o giro e descartado -- e avisamos.
  if (rotacaoVisor) {
    rotacaoVisor = 0;
    $('visor-img').style.transform = '';
    $('visor-img').style.maxHeight = '100%';
    toast('A seleção trabalha na imagem sem giro; o giro não salvo foi descartado.');
  }
  corte.ativo = true;
  // Comeca com folga pequena: 4% deixa a caixa visivel sem tirar quase nada
  // do alcance do arrasto (antes eram 5%, e sobrava pouco para puxar).
  const folga = finalidade === 'olhos' ? 0.25 : 0.04;
  corte.x0 = folga;
  corte.y0 = folga;
  corte.x1 = 1 - folga;
  corte.y1 = 1 - folga;
  $('visor-corte').hidden = false;
  $('visor-recortar').hidden = true;
  $('visor-olhos').hidden = true;
  $('visor-cortar').hidden = false;
  $('visor-cortar').textContent =
    finalidade === 'olhos' ? 'Corrigir olhos' : 'Cortar';
  $('visor-cancelar-corte').hidden = false;
  $('visor-rotacionar').hidden = true;
  $('visor-salvar-rotacao').hidden = true;
  // Fixa o wrapper no tamanho EXATO da imagem exibida.
  //
  // Sem isto, a caixa em % era calculada sobre um wrapper cuja altura podia
  // diferir da imagem (a imagem usa height:100% com pai de altura automática),
  // e o arrasto saía deslocado -- a borda de baixo parecia não responder.
  fixarFiguraNoTamanhoDaImagem();

  // Se a imagem ainda estiver carregando (acontece logo depois de girar, porque
  // salvar a rotação recarrega o arquivo), medir agora usaria o tamanho ANTIGO.
  // Aí a caixa apareceria num lugar e o recorte sairia em outro. Espera o load.
  const img = $('visor-img');
  if (img && !img.complete) {
    img.addEventListener('load', () => {
      if (!corte.ativo) return;
      fixarFiguraNoTamanhoDaImagem();
      desenharCorte();
    }, { once: true });
  }
  desenharCorte();
}

/**
 * Dá ao wrapper `#visor-fig` exatamente o tamanho renderizado da imagem.
 *
 * É o que garante que uma porcentagem da caixa de recorte corresponda à mesma
 * porcentagem da imagem. Sem isso, a conta do arrasto pode não bater com o que
 * o servidor corta.
 */
function fixarFiguraNoTamanhoDaImagem() {
  const fig = $('visor-fig');
  const img = $('visor-img');
  if (!fig || !img) return;
  const r = img.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return;
  fig.style.width = `${r.width}px`;
  fig.style.height = `${r.height}px`;
}

/** Solta o wrapper, para a imagem voltar a se ajustar sozinha. */
function soltarFigura() {
  const fig = $('visor-fig');
  if (!fig) return;
  fig.style.width = '';
  fig.style.height = '';
}

function sairModoRecorte() {
  corte.ativo = false;
  $('visor-corte').hidden = true;
  $('visor-recortar').hidden = !(visorItem && visorItem.unica);
  $('visor-olhos').hidden = !(visorItem && visorItem.unica);
  $('visor-cortar').hidden = true;
  $('visor-cortar').textContent = 'Cortar';
  $('visor-cancelar-corte').hidden = true;
  $('visor-rotacionar').hidden = !(visorItem && visorItem.unica);
  soltarFigura();
  // A imagem precisa voltar ao tamanho de ajuste depois de sair do recorte,
  // senão o wrapper fica preso no tamanho que tinha durante a seleção.
  aplicarZoom();
}

/**
 * Posiciona a caixa de recorte em PIXELS, medindo a IMAGEM.
 *
 * POR QUE NÃO EM PORCENTAGEM DO WRAPPER -- este foi um bug real:
 *
 * A caixa era posicionada em `%` do `#visor-fig`, mas as frações do arrasto e do
 * recorte são calculadas sobre o retângulo da `#visor-img`. Quando os dois não
 * coincidem exatamente (a imagem é dimensionada por `height:100%` dentro de um
 * pai de altura automática, e muda de tamanho ao carregar), o que aparecia na
 * tela era uma caixa em uma posição e o servidor recortava outra -- o usuário
 * via o quadro certo e o arquivo saía cortado no meio.
 *
 * Agora desenho e cálculo usam a MESMA referência: o retângulo da imagem. O que
 * está na tela é exatamente o que vai ser recortado.
 */
function desenharCorte() {
  const cx = $('visor-corte');
  const fig = $('visor-fig');
  const img = $('visor-img');
  if (!cx || cx.hidden || !fig || !img) return;

  const fr = fig.getBoundingClientRect();
  const r = img.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return;

  // Deslocamento da imagem dentro do wrapper (normalmente zero, mas não confio).
  const ox = r.left - fr.left;
  const oy = r.top - fr.top;

  cx.style.left = `${ox + r.width * corte.x0}px`;
  cx.style.top = `${oy + r.height * corte.y0}px`;
  cx.style.width = `${r.width * (corte.x1 - corte.x0)}px`;
  cx.style.height = `${r.height * (corte.y1 - corte.y0)}px`;
}

/**
 * Redesenha a caixa quando a imagem muda de tamanho ou a tela rola.
 *
 * Sem isto, um recarregamento da imagem (depois de girar) ou a rolagem do
 * visualizador deixavam a caixa parada no lugar antigo -- e a seleção visual
 * deixava de corresponder às frações.
 */
function ligarRedesenhoDoCorte() {
  const img = $('visor-img');
  const corpo = $('visor-corpo');
  const redesenhar = () => { if (corte.ativo) desenharCorte(); };
  if (img) img.addEventListener('load', redesenhar);
  window.addEventListener('resize', redesenhar);
  if (corpo) corpo.addEventListener('scroll', redesenhar, { passive: true });
}

/** Arrasta UMA borda -- versão antiga, mantida só se algo externo chamar.
 *  O arrasto real agora usa deslocamento (ver `ligarArrastoDeCorte`), porque a
 *  posição absoluta fazia a borda saltar até o ponteiro ao começar o gesto. */
function arrastarBorda(borda, frac) {
  const f = Math.min(1, Math.max(0, frac));
  if (borda === 'topo') {
    corte.y0 = Math.min(f, corte.y1 - CORTE_MIN);
  } else if (borda === 'base') {
    corte.y1 = Math.max(f, corte.y0 + CORTE_MIN);
  } else if (borda === 'esq') {
    corte.x0 = Math.min(f, corte.x1 - CORTE_MIN);
  } else {
    corte.x1 = Math.max(f, corte.x0 + CORTE_MIN);
  }
  desenharCorte();
}

/**
 * Liga o arrasto das alças e o arrasto da caixa inteira.
 *
 * Usa Pointer Events, que cobrem mouse e toque com o mesmo código.
 *
 * ARRASTA POR DESLOCAMENTO, não por posição absoluta. Foi um bug real: com a
 * alça DENTRO da caixa, a posição absoluta fazia a borda saltar até o ponteiro
 * ao começar o arrasto (a alça tem 16 px de espessura, então a borda "pulava"
 * até 16 px). Guardando a posição inicial e somando a diferença, a borda anda
 * exatamente o que o dedo andou.
 */
function ligarArrastoDeCorte() {
  const fig = $('visor-fig');
  if (!fig) return;

  const fracaoDoPonto = (ev) => {
    const r = $('visor-img').getBoundingClientRect();
    return {
      x: r.width ? (ev.clientX - r.left) / r.width : 0,
      y: r.height ? (ev.clientY - r.top) / r.height : 0,
    };
  };

  const ajustar = (borda, valor) => {
    const f = Math.min(1, Math.max(0, valor));
    if (borda === 'topo') {
      corte.y0 = Math.min(f, corte.y1 - CORTE_MIN);
    } else if (borda === 'base') {
      corte.y1 = Math.max(f, corte.y0 + CORTE_MIN);
    } else if (borda === 'esq') {
      corte.x0 = Math.min(f, corte.x1 - CORTE_MIN);
    } else {
      corte.x1 = Math.max(f, corte.x0 + CORTE_MIN);
    }
    desenharCorte();
  };

  /** Arrasta uma borda: mantém a diferença entre o ponteiro e a borda. */
  const ligarBorda = (el, borda) => {
    el.addEventListener('pointerdown', (ev) => {
      if (!corte.ativo) return;
      ev.preventDefault();
      ev.stopPropagation();
      el.setPointerCapture(ev.pointerId);

      const p0 = fracaoDoPonto(ev);
      const inicial = borda === 'topo' ? corte.y0
        : borda === 'base' ? corte.y1
          : borda === 'esq' ? corte.x0 : corte.x1;

      const mover = (e2) => {
        const p = fracaoDoPonto(e2);
        const delta = borda === 'topo' || borda === 'base'
          ? p.y - p0.y : p.x - p0.x;
        ajustar(borda, inicial + delta);
      };
      const soltar = (e2) => {
        el.removeEventListener('pointermove', mover);
        el.removeEventListener('pointerup', soltar);
        el.removeEventListener('pointercancel', soltar);
        try { el.releasePointerCapture(e2.pointerId); } catch { /* ok */ }
      };
      el.addEventListener('pointermove', mover);
      el.addEventListener('pointerup', soltar);
      el.addEventListener('pointercancel', soltar);
    });
  };

  document.querySelectorAll('.corte-alca').forEach((alca) => {
    ligarBorda(alca, alca.dataset.borda || alca.dataset.borda);
    // BUG ANTES: `alca.dataset.borda` era lido de `data-borda`, mas o seletor
    // acima procura `.corte-alca`; se o atributo viesse vazio a alça não fazia
    // nada. Aqui garantimos a leitura por data-attribute.
  });

  // Arrastar o INTERIOR move a caixa inteira (o cursor 'move' já sugeria isso).
  const caixa = $('visor-corte');
  if (caixa) {
    caixa.addEventListener('pointerdown', (ev) => {
      if (!corte.ativo) return;
      // Só quando o alvo é a própria caixa ou a grade, não uma alça.
      if (ev.target !== caixa && !ev.target.classList.contains('corte-grade')) {
        return;
      }
      ev.preventDefault();
      caixa.setPointerCapture(ev.pointerId);
      const p0 = fracaoDoPonto(ev);
      const ini = { x0: corte.x0, y0: corte.y0, x1: corte.x1, y1: corte.y1 };
      const larg = ini.x1 - ini.x0;
      const alt = ini.y1 - ini.y0;

      const mover = (e2) => {
        const p = fracaoDoPonto(e2);
        let nx0 = ini.x0 + (p.x - p0.x);
        let ny0 = ini.y0 + (p.y - p0.y);
        nx0 = Math.min(Math.max(nx0, 0), 1 - larg);
        ny0 = Math.min(Math.max(ny0, 0), 1 - alt);
        corte.x0 = nx0;
        corte.y0 = ny0;
        corte.x1 = nx0 + larg;
        corte.y1 = ny0 + alt;
        desenharCorte();
      };
      const soltar = (e2) => {
        caixa.removeEventListener('pointermove', mover);
        caixa.removeEventListener('pointerup', soltar);
        caixa.removeEventListener('pointercancel', soltar);
        try { caixa.releasePointerCapture(e2.pointerId); } catch { /* ok */ }
      };
      caixa.addEventListener('pointermove', mover);
      caixa.addEventListener('pointerup', soltar);
      caixa.addEventListener('pointercancel', soltar);
    });
  }
}

/** Grava o recorte no arquivo da restaurada, com cópia de segurança. */
/**
 * Confirma a seleção: corta ou corrige olhos vermelhos, conforme a finalidade.
 *
 * As duas usam a MESMA caixa porque as duas precisam de uma área da imagem. O
 * que muda é o que o servidor faz com ela.
 */
async function cortarVisor() {
  if (!visorItem || !visorItem.unica) return;
  if (corte.finalidade === 'olhos') return corrigirOlhosVisor();

  const botao = $('visor-cortar');
  const w = corte.x1 - corte.x0;
  const h = corte.y1 - corte.y0;
  if (w < CORTE_MIN || h < CORTE_MIN) {
    return toast('recorte pequeno demais', 'erro');
  }
  if (w > 0.995 && h > 0.995) {
    return toast('a caixa está na imagem inteira: ajuste as bordas antes');
  }
  try {
    botao.disabled = true;
    botao.textContent = 'Cortando…';
    const r = await post('/api/recortar-restaurado', {
      nome: visorItem.nome,
      x0: corte.x0, y0: corte.y0, x1: corte.x1, y1: corte.y1,
    });
    toast(`Recorte salvo: ${r.tamanho[0]}x${r.tamanho[1]}`, 'ok');
    ultimoBackup = r.backup || null;      // habilita o Desfazer desta alteração
    sairModoRecorte();
    $('visor-img').src = urlImagemGrande('restaurado', visorItem.nome);
    compVersao += 1;
    if (!$('painel-comparar').hidden) renderComparar();
  } catch (e) {
    toast(e.message, 'erro');
  } finally {
    botao.disabled = false;
    botao.textContent = 'Cortar';
  }
}

/**
 * Aplica a correção de olhos vermelhos DENTRO da área marcada.
 *
 * A área é obrigatória porque o detector sozinho acha 17 a 37 regiões por foto
 * (tons de pele, objetos avermelhados, ruído) -- aplicar na foto inteira
 * neutralizaria vermelhos legítimos. Marcando o rosto, só ali ele trabalha.
 */
async function corrigirOlhosVisor() {
  const botao = $('visor-cortar');
  const w = corte.x1 - corte.x0;
  const h = corte.y1 - corte.y0;
  if (w < 0.02 || h < 0.02) {
    return toast('marque uma área em volta dos olhos', 'erro');
  }
  try {
    botao.disabled = true;
    botao.textContent = 'Corrigindo…';
    const r = await post('/api/olhos-vermelhos', {
      nome: visorItem.nome,
      x0: corte.x0, y0: corte.y0, x1: corte.x1, y1: corte.y1,
      forca: 0.85,
    });
    if (!r.gravado) {
      toast(`Nenhum olho vermelho encontrado nesta área `
            + `(${r.regioes} região(ões) descartada(s)).`, 'erro');
      botao.disabled = false;
      botao.textContent = 'Corrigir olhos';
      return;
    }
    toast(`Olhos corrigidos: ${r.regioes} região(ões), ${r.pixels} pixels`, 'ok');
    ultimoBackup = r.backup || null;      // habilita o Desfazer
    sairModoRecorte();
    $('visor-img').src = urlImagemGrande('restaurado', visorItem.nome);
    compVersao += 1;
    if (!$('painel-comparar').hidden) renderComparar();
  } catch (e) {
    toast(e.message, 'erro');
    botao.disabled = false;
    botao.textContent = 'Corrigir olhos';
  }
}

/** Grava a rotação no arquivo da restaurada (com cópia de segurança). */
async function salvarRotacaoVisor() {
  if (!visorItem || !visorItem.nome) return;
  const botao = $('visor-salvar-rotacao');
  const angulo = rotacaoVisor;
  if (!angulo) return;
  try {
    botao.disabled = true;
    botao.textContent = 'Salvando…';
    // Envia o ÂNGULO, não o número de giros: assim 90, 1 ou 1,5 graus usam o
    // mesmo caminho no servidor.
    const r = await post('/api/girar-restaurado',
                         { nome: visorItem.nome, angulo });
    toast(`Rotação salva: ${r.tamanho[0]}x${r.tamanho[1]}`, 'ok');
    ultimoBackup = r.backup || null;      // habilita o Desfazer
    rotacaoVisor = 0;
    const alvo = $('visor-img');
    alvo.style.transform = '';
    alvo.src = urlImagemGrande('restaurado', visorItem.nome);
    $('visor-salvar-rotacao').hidden = true;
    const valor = $('visor-giro-valor');
    if (valor) valor.textContent = '0,0°';
    compVersao += 1;
    if (!$('painel-comparar').hidden) renderComparar();
  } catch (e) {
    toast(e.message, 'erro');
  } finally {
    botao.disabled = false;
    botao.textContent = 'Salvar rotação';
  }
}

function ajustarZoom(delta) {
  zoom = Math.min(6, Math.max(0.5, zoom + delta));
  aplicarZoom();
}

/** Aplica o zoom respeitando se a imagem é única ou uma comparação. */
function aplicarZoom() {
  const alvo = $('visor-img');
  if (alvo.dataset.unica === '1') {
    // Imagem única: parte da altura toda e cresce a partir daí.
    alvo.style.width = 'auto';
    alvo.style.height = `${zoom * 100}%`;
  } else {
    alvo.style.height = 'auto';
    alvo.style.width = `${zoom * 100}%`;
  }
}

function fecharVisor() { $('visor').hidden = true; $('visor-img').src = ''; visorItem = null; }

/* ------------------------------------------------------- comparador */
let zoomComp = 1;

function abrirComparacao(nome) {
  if (!nome) return;
  zoomComp = 1;
  const img = $('comp-img');
  // A comparação é montada no servidor: o navegador baixa UM arquivo
  // reduzido em vez de duas imagens de ~7 MB.
  //
  // Token novo a cada abertura: sem ele, esta comparação também viria do cache
  // com a versão antiga do positivo/restaurado.
  img.src = `/midia/comparar/${encodeURIComponent(nome)}?w=1500&s=${Date.now()}`;
  img.style.width = '100%';
  img.alt = `positivo e restaurado lado a lado: ${nome}`;
  $('comp-nome').textContent = nome;
  $('comparador').hidden = false;
}

function ajustarZoomComp(delta) {
  zoomComp = Math.min(6, Math.max(0.5, zoomComp + delta));
  $('comp-img').style.width = (zoomComp * 100) + '%';
}

function fecharComparacao() {
  $('comparador').hidden = true;
  $('comp-img').src = '';
}

/* ---------------------------------------------------------------- config */
/**
 * Preenche os rótulos com o valor recomendado e marca quando o campo está
 * fora dele.
 *
 * O objetivo é o usuário abrir a tela e saber, sem perguntar, o que é normal:
 * "Saturação (recomendado: 1.15)". Se ele mudou algo, o rótulo fica em
 * destaque, para ele perceber que saiu do padrão.
 */
function anotarRecomendados(rec) {
  const campos = [
    ['cfg-saturacao', rec.saturacao],
    ['cfg-nitidez', rec.nitidez],
    ['cfg-balanco', rec.balanco],
    ['cfg-curva-alvo', rec.curva_alvo],
    ['cfg-max-lado', rec.max_lado_envio],
    ['cfg-curva-gamma', rec.curva_gamma],
  ];
  for (const [id, recomendado] of campos) {
    const campo = $(id);
    if (!campo) continue;
    const rotulo = campo.parentElement.querySelector('label');
    let tag = rotulo.querySelector('.rec');
    if (!tag) {
      tag = document.createElement('span');
      tag.className = 'rec';
      rotulo.appendChild(tag);
    }
    const atual = parseFloat(campo.value);
    const difere = Math.abs(atual - recomendado) > 1e-9;
    tag.textContent = `recomendado: ${recomendado}`;
    tag.classList.toggle('diferente', difere);
    tag.title = difere
      ? `Você está usando ${atual}, que difere do recomendado (${recomendado})`
      : 'Você está no valor recomendado';
  }

  // O botão de padrões usa os valores do servidor, não uma cópia local --
  // assim não há como os dois divergirem.
  PADROES = rec;
}
let PADROES = {
  filme: 'generico', saturacao: 1.15, nitidez: 0.40, balanco: 0.90,
  curva_alvo: 0.50, curva_gamma: 0.0, max_lado_envio: 1536,
  usar_curva: true, usar_adobe: true, converter_auto: false,
};

async function abrirConfig() {
  const c = await api('/api/config');
  $('cfg-origem').value = c.pastas.origem;
  $('cfg-positivo').value = c.pastas.positivo;
  $('cfg-restaurada').value = c.pastas.restaurada;
  $('cfg-filme').value = c.filme || PADROES.filme;
  $('cfg-saturacao').value = c.saturacao;
  $('cfg-nitidez').value = c.nitidez;
  $('cfg-balanco').value = c.balanco;
  $('cfg-curva-alvo').value = c.curva_alvo;
  $('cfg-curva-gamma').value = c.curva_gamma || 0;
  $('cfg-max-lado').value = c.max_lado_envio;
  $('cfg-cache-adobe').value = c.pasta_cache_adobe || '';
  $('cfg-curva').checked = !!c.usar_curva;
  $('cfg-adobe').checked = !!c.usar_adobe;
  $('cfg-auto').checked = !!c.converter_auto;
  $('cfg-casar-exposicao').checked = !!c.casar_exposicao;
  $('cfg-exposicao-forca').value = c.exposicao_forca;
  $('cfg-dica').checked = !!c.dica_por_foto;
  $('cfg-recortar-bordas').checked = !!c.recortar_bordas;
  $('cfg-recorte-margem').value = c.recorte_margem;
  $('cfg-limpar-borda-prompt').checked = !!c.limpar_borda_no_prompt;
  if (c.recomendados) anotarRecomendados(c.recomendados);
  $('cfg-nota').innerHTML =
    `Modelo de IA: <b>${esc(c.modelo)}</b> (${esc(c.provedor)}). ` +
    (c.tem_chave
      ? 'Chave de API configurada ✓'
      : '<span style="color:var(--erro)">SEM chave de API — a restauração não vai funcionar.</span>');
  $('modal').hidden = false;
}

function aplicarPadroes() {
  $('cfg-filme').value = PADROES.filme || 'generico';
  $('cfg-saturacao').value = PADROES.saturacao;
  $('cfg-nitidez').value = PADROES.nitidez;
  $('cfg-balanco').value = PADROES.balanco;
  $('cfg-curva-alvo').value = PADROES.curva_alvo;
  $('cfg-curva-gamma').value = PADROES.curva_gamma;
  $('cfg-max-lado').value = PADROES.max_lado_envio;
  $('cfg-curva').checked = !!PADROES.usar_curva;
  $('cfg-adobe').checked = !!PADROES.usar_adobe;
  // Cuidado com a semântica: os recomendados são SIM para curva e Adobe, e
  // NÃO para a conversão automática. Escrever `!!PADROES.converter_auto` nos
  // três seria errado e desmarcaria os que devem ficar marcados.
  $('cfg-auto').checked = false;
  $('cfg-casar-exposicao').checked = true;
  $('cfg-exposicao-forca').value = 0.85;
  $('cfg-dica').checked = true;
  $('cfg-recortar-bordas').checked = true;
  $('cfg-recorte-margem').value = 0;
  $('cfg-limpar-borda-prompt').checked = true;
  anotarRecomendados(PADROES);
  toast('Valores recomendados preenchidos. Clique em Salvar.', 'ok');
}

async function salvarConfig() {
  try {
    await post('/api/salvar-config', {
      pasta_origem: $('cfg-origem').value,
      pasta_positivo: $('cfg-positivo').value,
      pasta_restaurada: $('cfg-restaurada').value,
      filme: $('cfg-filme').value,
      saturacao: $('cfg-saturacao').value,
      nitidez: $('cfg-nitidez').value,
      balanco: $('cfg-balanco').value,
      curva_alvo: $('cfg-curva-alvo').value,
      curva_gamma: $('cfg-curva-gamma').value,
      max_lado_envio: $('cfg-max-lado').value,
      pasta_cache_adobe: $('cfg-cache-adobe').value.trim(),
      usar_curva: $('cfg-curva').checked,
      usar_adobe: $('cfg-adobe').checked,
      converter_auto: $('cfg-auto').checked,
      casar_exposicao: $('cfg-casar-exposicao').checked,
      exposicao_forca: $('cfg-exposicao-forca').value,
      dica_por_foto: $('cfg-dica').checked,
      recortar_bordas: $('cfg-recortar-bordas').checked,
      recorte_margem: $('cfg-recorte-margem').value,
      limpar_borda_no_prompt: $('cfg-limpar-borda-prompt').checked,
    });
    $('modal').hidden = true;
    _precoUnit = null;
    automaticoFeito = false;
    toast('Configurações salvas', 'ok');
    await carregarEstado();
    await talvezAutomatico();
  } catch (e) { toast(e.message, 'erro'); }
}

/* ---------------------------------------------------------------- auto */
/**
 * Conversão automática ao abrir.
 *
 * Desligada por padrão: disparar sozinho a cada abertura fazia parecer que a
 * conversão "recomeçava do zero" -- mesmo com os positivos já prontos, que o
 * programa pula corretamente. Agora quem decide é o botão "Converter
 * pendentes"; quem preferir o automático liga em `converter_auto` no .env.
 */
async function talvezAutomatico() {
  if (automaticoFeito) return;
  automaticoFeito = true;
  if (trabalhoAtivo()) return;

  if (!estado || !estado.config || !estado.config.converter_auto) return;

  // Não tenta converter se as pastas não permitem: antes, a conversão
  // automática disparava e enchia a tela de erros de permissão.
  if (diagnostico && !diagnostico.pode_converter) return;

  const c = estado.contagens;
  if (c.faltam_positivo > 0 && c.total > 0) {
    toast(`Convertendo ${c.faltam_positivo} foto(s) (automático ligado no .env)…`);
    await converter();
  }
}

/* ---------------------------------------------------------------- init */
function ligarEventos() {
  $('btn-converter').addEventListener('click', converter);
  $('btn-restaurar').addEventListener('click', restaurar);

  // --- aba de falhas na conversão
  // (a troca de abas já é ligada mais abaixo, em um laço só)
  $('falhas-atualizar').addEventListener('click', carregarFalhas);

  // --- aba de falhas na restauração
  $('restauro-atualizar').addEventListener('click', carregarFalhasRestauro);
  $('restauro-marcar-todas').addEventListener('click',
    alternarMarcarTodasRestauro);
  $('restauro-forcar-selecionadas').addEventListener('click', (ev) => {
    forcarSelecionadasRestauro(ev.currentTarget);
  });

  // --- aba renomear
  $('renomear-atualizar').addEventListener('click', carregarRenomear);
  $('renomear-marcar-todas').addEventListener('click',
    alternarMarcarTodasRenomear);
  $('renomear-aplicar').addEventListener('click', aplicarRenomear);
  // O prefixo muda a prévia de cada foto: redesenha ao digitar.
  $('renomear-prefixo').addEventListener('input', () => {
    if (renomearDados) desenharRenomear();
    else atualizarBotaoRenomear();
  });
  $('restauro-copiar').addEventListener('click', async () => {
    if (!falhasRestauro || !falhasRestauro.falhas.length) {
      return toast('nada para copiar');
    }
    const texto = falhasRestauro.falhas
      .map((f) => `${f.nome}\t${f.motivo || ''}`)
      .join('\n');
    try {
      await navigator.clipboard.writeText(texto);
      toast('Lista copiada', 'ok');
    } catch {
      toast('o navegador não deixou copiar', 'erro');
    }
  });
  $('falhas-diagnosticar-todas').addEventListener('click', (ev) => {
    diagnosticarTodasFalhas(ev.currentTarget);
  });
  $('falhas-copiar').addEventListener('click', async () => {
    if (!falhasDados || !falhasDados.falhas.length) {
      return toast('nada para copiar');
    }
    const texto = falhasDados.falhas
      .map((f) => `${f.nome}\t${f.arquivo}\t${f.motivo || '(sem motivo)'}`)
      .join('\n');
    try {
      await navigator.clipboard.writeText(texto);
      toast('Lista copiada', 'ok');
    } catch {
      toast('o navegador não deixou copiar', 'erro');
    }
  });

  $('btn-parar').addEventListener('click', async () => {
    try { await post('/api/parar', {}); toast('Parando…'); } catch (e) { toast(e.message, 'erro'); }
  });
  $('btn-todos').addEventListener('click', () => {
    document.querySelectorAll('.marca-sel').forEach((c) => {
      c.checked = true; c.closest('.celula').classList.add('marcada');
    });
    atualizarCusto();
  });
  $('btn-nenhum').addEventListener('click', () => {
    document.querySelectorAll('.marca-sel').forEach((c) => {
      c.checked = false; c.closest('.celula').classList.remove('marcada');
    });
    atualizarCusto();
  });
  $('visor-fechar').addEventListener('click', fecharVisor);
  $('visor').addEventListener('click', (e) => { if (e.target.id === 'visor') fecharVisor(); });
  $('visor-mais').addEventListener('click', () => ajustarZoom(0.25));
  $('visor-menos').addEventListener('click', () => ajustarZoom(-0.25));
  $('visor-100').addEventListener('click', () => { zoom = 1; aplicarZoom(); });
  $('visor-rotacionar').addEventListener('click', rotacionarVisor);
  $('visor-girar-menos').addEventListener('click', () => girarVisorFino(-1));
  $('visor-girar-mais').addEventListener('click', () => girarVisorFino(1));
  $('visor-girar-zero').addEventListener('click', () => definirGiroVisor(0));
  $('visor-salvar-rotacao').addEventListener('click', salvarRotacaoVisor);
  $('visor-recortar').addEventListener('click', () => entrarModoRecorte('cortar'));
  $('visor-olhos').addEventListener('click', () => entrarModoRecorte('olhos'));
  $('visor-desfazer').addEventListener('click', desfazerVisor);
  $('visor-cortar').addEventListener('click', cortarVisor);
  $('visor-cancelar-corte').addEventListener('click', sairModoRecorte);
  ligarArrastoDeCorte();
  ligarRedesenhoDoCorte();
  $('visor-comparar').addEventListener('click', () => {
    if (visorItem && visorItem.temRestaurado) abrirComparacao(visorItem.nome);
  });

  // comparador
  $('comp-fechar').addEventListener('click', fecharComparacao);
  $('comparador').addEventListener('click', (e) => {
    if (e.target.id === 'comparador') fecharComparacao();
  });
  $('comp-mais').addEventListener('click', () => ajustarZoomComp(0.25));
  $('comp-menos').addEventListener('click', () => ajustarZoomComp(-0.25));
  $('comp-100').addEventListener('click', () => {
    zoomComp = 1; $('comp-img').style.width = '100%';
  });

  $('chk-restauradas').addEventListener('change', (e) => {
    mostrarRestauradas = e.target.checked;
    renderGrade();
  });

  // abas
  document.querySelectorAll('.aba').forEach((b) => {
    b.addEventListener('click', () => trocarAba(b.dataset.aba));
  });

  // aba comparar
  $('comp-busca').addEventListener('input', (e) => {
    compBusca = e.target.value;
    compMostrando = COMP_LOTE;      // busca nova, lista do começo
    renderComparar();
  });
  $('comp-so-restauradas').addEventListener('change', (e) => {
    compSoRestauradas = e.target.checked;
    compMostrando = COMP_LOTE;
    renderComparar();
  });
  $('comp-todas').addEventListener('click', () => {
    document.querySelectorAll('.comp-item input').forEach((c) => { c.checked = true; });
    renderComparar();
  });
  $('comp-nenhuma').addEventListener('click', () => {
    document.querySelectorAll('.comp-item input').forEach((c) => { c.checked = false; });
    renderComparar();
  });
  $('comp-mostrar').addEventListener('click', () => {
    const marcados = new Set(
      [...document.querySelectorAll('.comp-item input:checked')].map((c) => c.dataset.nome)
    );
    const escolhidos = itensComparaveis().filter((i) => marcados.has(i.nome));
    if (!escolhidos.length) { toast('Marque pelo menos uma foto.', 'erro'); return; }
    compMostrando = COMP_LOTE;
    desenharCartoes(escolhidos);
    const alvo = $('comp-resultado');
    if (alvo) alvo.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  $('btn-config').addEventListener('click', abrirConfig);
  $('modal-cancelar').addEventListener('click', () => { $('modal').hidden = true; });
  $('modal-padroes').addEventListener('click', aplicarPadroes);
  $('modal-salvar').addEventListener('click', salvarConfig);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { fecharVisor(); fecharComparacao(); $('modal').hidden = true; }
    if (!$('comparador').hidden) {
      if (e.key === '+' || e.key === '=') ajustarZoomComp(0.25);
      if (e.key === '-') ajustarZoomComp(-0.25);
    } else if (!$('visor').hidden) {
      if (e.key === '+' || e.key === '=') ajustarZoom(0.25);
      if (e.key === '-') ajustarZoom(-0.25);
    }
  });
}

(async function iniciar() {
  // Garante que NADA sobreposto apareça na abertura. O HTML já traz estes
  // elementos com `hidden`, mas reforçamos aqui: se uma versão anterior
  // deixou algo visível, isto fecha na primeira linha, antes de qualquer
  // coisa assíncrona rodar.
  $('modal').hidden = true;
  $('visor').hidden = true;
  $('comparador').hidden = true;
  $('progresso').hidden = true;
  $('toast').hidden = true;

  ligarEventos();
  try {    // Se já houver um trabalho rodando (ex.: recarregou a página), retoma o
    // acompanhamento em vez de começar outro.
    const t = await api('/api/progresso');
    if (t && t.tipo && !t.terminado) {
      trabalho = t;
      renderProgresso(t);
      comecarPolling();
    }
    await carregarPreco();
    await verificarPastas();
    await carregarEstado();
    await talvezAutomatico();
  } catch (e) {
    toast('Falha ao carregar: ' + e.message, 'erro');
  }
})();
