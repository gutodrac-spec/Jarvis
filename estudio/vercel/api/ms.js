// Função da Vercel (Edge): repassa /ms/v1/* para a API do ModelScope no mesmo domínio da página.
// Não guarda nada: o token de cada visitante vem no cabeçalho Authorization e só é repassado.
export const config = { runtime: "edge" };

const DESTINO = "https://api-inference.modelscope.cn";
const REPASSAR = ["authorization", "content-type", "x-modelscope-async-mode", "x-modelscope-task-type"];

export default async function handler(pedido) {
  const url = new URL(pedido.url);
  const caminho = (url.searchParams.get("path") || "").replace(/^\/+/, "");

  if (caminho === "ping") return new Response("ok", { headers: { "cache-control": "no-store" } });
  if (!/^v1\/(images\/generations|videos\/generations|tasks\/[\w-]+|chat\/completions)$/.test(caminho)) {
    return new Response("caminho não permitido", { status: 404 });
  }
  if (pedido.method !== "GET" && pedido.method !== "POST") {
    return new Response("método não permitido", { status: 405 });
  }

  const cabecalhos = new Headers();
  for (const nome of REPASSAR) {
    const valor = pedido.headers.get(nome);
    if (valor) cabecalhos.set(nome, valor);
  }
  const resposta = await fetch(`${DESTINO}/${caminho}`, {
    method: pedido.method,
    headers: cabecalhos,
    body: pedido.method === "POST" ? await pedido.text() : undefined,
  });
  const saida = new Response(resposta.body, { status: resposta.status });
  saida.headers.set("content-type", resposta.headers.get("content-type") || "application/json");
  saida.headers.set("cache-control", "no-store");
  return saida;
}
