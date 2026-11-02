/**
 * Executa o iniciar() do app.js contra um DOM simulado.
 *
 * Por que isto existe: se o JavaScript estourar numa exceção na abertura, o
 * modal de configuração NUNCA é escondido e a tela aparece sozinha, com os
 * campos vazios (porque abrirConfig não chegou a rodar). Foi o sintoma
 * relatado, e nenhum teste de texto pega isso.
 *
 * Não substitui um navegador, mas executa o código real e mostra a exceção.
 */

const fs = require('fs');
const vm = require('vm');

const js = fs.readFileSync('web/app.js', 'utf8');

// --- DOM simulado -----------------------------------------------------------
const elementos = new Map();

function criarElemento(id, tag = 'div') {
  const el = {
    id, tagName: tag.toUpperCase(),
    _attrs: {}, _classes: new Set(), _filhos: [],
    value: '', textContent: '', innerHTML: '', checked: false,
    hidden: false, disabled: false, src: '', alt: '', style: {}, dataset: {},
    classList: {
      add: (...c) => c.forEach((x) => el._classes.add(x)),
      remove: (...c) => c.forEach((x) => el._classes.delete(x)),
      toggle: (c, on) => (on ? el._classes.add(c) : el._classes.delete(c)),
      contains: (c) => el._classes.has(c),
    },
    addEventListener: (tipo, fn) => { el._ev = el._ev || {}; (el._ev[tipo] = el._ev[tipo] || []).push(fn); },
    appendChild: (f) => { el._filhos.push(f); return f; },
    closest: () => el,
    querySelector: () => null,
    querySelectorAll: () => [],
    getAttribute: (k) => el._attrs[k],
    setAttribute: (k, v) => { el._attrs[k] = v; },
  };
  Object.defineProperty(el, 'parentElement', {
    get: () => criarElemento(id + '-pai'),
  });
  return el;
}

// ids que o app.js busca
const idsNecessarios = [...js.matchAll(/\$\('([^']+)'\)/g)].map((m) => m[1]);
for (const id of [...new Set(idsNecessarios)]) {
  elementos.set(id, criarElemento(id));
}

const documento = {
  getElementById: (id) => elementos.get(id) || null,
  querySelectorAll: (sel) => (sel === '.marca-sel' ? [] : []),
  createElement: (tag) => criarElemento('novo', tag),
  addEventListener: () => {},
};

// --- respostas simuladas da API --------------------------------------------
const RESPOSTAS = {
  '/api/progresso': { tipo: null, terminado: true },
  '/api/custo?nomes=x': { quantos: 1, usd: 0.039, fonte: 'teste' },
  '/api/verificar-pastas': {
    origem: { caminho: 'E:\\RAW', existe: true, imagens: 27, na_nuvem: true },
    positivo: { caminho: 'C:\\Users\\x\\neg35\\positivo', existe: false, gravavel: false,
                erro: 'sem permissão de escrita (Acesso negado).', na_nuvem: false },
    restaurada: { caminho: 'C:\\Users\\x\\neg35\\restaurada', existe: false, gravavel: false,
                  erro: 'sem permissão de escrita (Acesso negado).', na_nuvem: false },
    tudo_ok: false, pode_converter: false, pode_restaurar: false,
    problemas: ['Positivos: sem permissão de escrita (Acesso negado).'],
    dica_nuvem: '', sugestao_local: 'C:\\Users\\x\\neg35',
  },
  '/api/estado': {
    pastas: { origem: 'E:\\RAW', positivo: 'C:\\p', restaurada: 'C:\\r',
              origem_existe: true, positivo_existe: false, restaurada_existe: false },
    config: { modelo: 'google/gemini-2.5-flash-image', provedor: 'openrouter',
              filme: 'generico', saturacao: 1.15, nitidez: 0.4, balanco: 0.9,
              usar_curva: true, curva_alvo: 0.5, usar_adobe: true,
              max_lado_envio: 1536, tem_chave: true },
    adobe_disponivel: true,
    contagens: { total: 27, com_positivo: 0, com_restaurado: 0,
                 faltam_positivo: 27, faltam_restaurar: 0 },
    itens: [], pendentes_positivo: [], pendentes_restaurar: [],
  },
};

async function buscar(url) {
  const chave = Object.keys(RESPOSTAS).find((k) => url === k || url.startsWith(k));
  if (!chave) throw new Error(`rota não simulada: ${url}`);
  const dados = RESPOSTAS[chave];
  return {
    ok: true, status: 200,
    text: async () => JSON.stringify(dados),
  };
}

// --- executa ----------------------------------------------------------------
const contexto = {
  document: documento,
  window: { addEventListener: () => {} },
  fetch: buscar,
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (t) => clearTimeout(t),
  setInterval: (fn, ms) => setInterval(fn, ms),
  clearInterval: (t) => clearInterval(t),
  console, JSON, Math, Object, Array, String, Number, Promise, Date, RegExp,
  encodeURIComponent, parseFloat, parseInt, isNaN,
};

let erroFatal = null;
process.on('unhandledRejection', (e) => { erroFatal = e; });

(async () => {
  try {
    vm.createContext(contexto);
    vm.runInContext(js, contexto, { filename: 'app.js' });
    // deixa as promessas do iniciar() assentarem
    await new Promise((r) => setTimeout(r, 600));
  } catch (e) {
    erroFatal = e;
  }

  console.log('=== resultado ===');
  if (erroFatal) {
    console.log('  EXCEÇÃO NA ABERTURA:', erroFatal && erroFatal.message);
    console.log(erroFatal && erroFatal.stack ? erroFatal.stack.split('\n').slice(0, 6).join('\n') : '');
    process.exit(1);
  }

  const modal = elementos.get('modal');
  console.log(`  modal.hidden  = ${modal.hidden}   (esperado: true)`);
  console.log(`  visor.hidden  = ${elementos.get('visor').hidden}`);
  const diag = elementos.get('diagnostico');
  console.log(`  diagnostico.hidden = ${diag.hidden}   (esperado: false, há problema)`);
  console.log(`  diagnostico.innerHTML preenchido = ${diag.innerHTML.length > 0}`);
  const et = elementos.get('etapa-converter');
  console.log(`  cont-converter = "${elementos.get('cont-converter').textContent}"`);

  const problemas = [];
  if (modal.hidden !== true) problemas.push('modal NÃO foi escondido');
  if (diag.innerHTML.length === 0) problemas.push('banner de diagnóstico vazio');

  console.log();
  if (problemas.length) {
    console.log('  PROBLEMAS: ' + problemas.join('; '));
    process.exit(1);
  }
  console.log('  iniciar() rodou sem exceção e escondeu o modal.');
})();
