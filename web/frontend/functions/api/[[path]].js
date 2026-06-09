/** Proxy /api/* to the Render panel API (same-origin — no CORS, no stale URL in JS). */

const DEFAULT_UPSTREAM = "https://orbat-bot.onrender.com";

export async function onRequest(context) {
  const upstream = (context.env.RENDER_API_URL || DEFAULT_UPSTREAM).replace(/\/$/, "");
  const url = new URL(context.request.url);
  const target = `${upstream}${url.pathname}${url.search}`;

  const headers = new Headers(context.request.headers);
  headers.delete("host");

  const init = {
    method: context.request.method,
    headers,
    redirect: "manual",
  };
  if (context.request.method !== "GET" && context.request.method !== "HEAD") {
    init.body = await context.request.arrayBuffer();
  }

  const resp = await fetch(target, init);
  const out = new Headers(resp.headers);
  out.delete("transfer-encoding");
  return new Response(resp.body, { status: resp.status, headers: out });
}
