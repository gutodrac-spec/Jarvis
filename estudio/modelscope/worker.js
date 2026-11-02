// Proxy CORS grátis para a API do ModelScope (Cloudflare Workers, plano grátis).
// Só use se o navegador bloquear as chamadas diretas (erro de CORS na página).
//
// Como criar (5 min, sem cartão):
//   1. dash.cloudflare.com → Workers & Pages → Create → "Hello World" → Deploy
//   2. Edit code → apague tudo, cole este arquivo → Deploy
//   3. Copie o endereço (https://xxx.workers.dev) e cole em ⚙️ Configurações → Proxy, na página.
//
// Ele só repassa para api-inference.modelscope.cn e não guarda nada.
// O token continua vindo de cada visitante (cabeçalho Authorization).

const DESTINO = "https://api-inference.modelscope.cn";
// Troque "*" pelo endereço do seu site para só ele poder usar o proxy,
// ex.: "https://luismurer-video-generaton.static.hf.space"
const ORIGEM_PERMITIDA = "*";

const CORS = {
  "Access-Control-Allow-Origin": ORIGEM_PERMITIDA,
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type, X-ModelScope-Async-Mode, X-ModelScope-Task-Type",
  "Access-Control-Max-Age": "86400",
};

export default {
  async fetch(pedido) {
    if (pedido.method === "OPTIONS") return new Response(null, { headers: CORS });

    const url = new URL(pedido.url);
    if (!url.pathname.startsWith("/v1/")) return new Response("só /v1/*", { status: 404, headers: CORS });

    const cabecalhos = new Headers();
    for (const nome of ["authorization", "content-type", "x-modelscope-async-mode", "x-modelscope-task-type"]) {
      const valor = pedido.headers.get(nome);
      if (valor) cabecalhos.set(nome, valor);
    }
    const resposta = await fetch(DESTINO + url.pathname + url.search, {
      method: pedido.method,
      headers: cabecalhos,
      body: pedido.method === "POST" ? await pedido.text() : undefined,
    });
    const saida = new Response(resposta.body, resposta);
    for (const [k, v] of Object.entries(CORS)) saida.headers.set(k, v);
    return saida;
  },
};
