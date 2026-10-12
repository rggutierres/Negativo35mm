const fs = require('fs');
(async () => {
  const r = await fetch('https://openrouter.ai/api/v1/models');
  const j = await r.json();
  const imgs = j.data.filter(m => (m.architecture.output_modalities||[]).includes('image'));
  console.log('=== OpenRouter: modelos com saida de imagem ===');
  for (const m of imgs) {
    console.log(m.id + ' | img_out=$' + m.pricing.image_output + ' | prompt=$' + m.pricing.prompt + ' | completion=$' + m.pricing.completion + ' | ctx=' + m.context_length);
  }
  // preco do nano banana
  const nb = j.data.filter(m => /banana/i.test(m.id));
  console.log('\n=== Todos os Nano Banana ===');
  for (const m of nb) console.log(JSON.stringify({id:m.id, name:m.name, pricing:m.pricing, modality:m.architecture.modality}, null, 1));

  // pagina de precos do Google
  const g = await fetch('https://ai.google.dev/gemini-api/docs/pricing?hl=en');
  let html = await g.text();
  const text = html.replace(/<script[\s\S]*?<\/script>/g,' ').replace(/<style[\s\S]*?<\/style>/g,' ').replace(/<[^>]+>/g,' ').replace(/&nbsp;/g,' ').replace(/&amp;/g,'&').replace(/\s+/g,' ');
  fs.writeFileSync('tools/gemini-pricing.txt', text);
  console.log('\n=== Google: trechos com "Nano Banana" ===');
  let i = 0, n = 0;
  while ((i = text.indexOf('Nano Banana', i)) >= 0 && n < 12) {
    console.log('--- @' + i + ' ---');
    console.log(text.slice(Math.max(0,i-120), i+900));
    i += 11; n++;
  }
})();
