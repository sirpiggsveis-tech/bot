/** Proxy /ping to Render for cold-start wake (used before login). */

const DEFAULT_UPSTREAM = "https://orbat-bot.onrender.com";

export async function onRequest(context) {
  const upstream = (context.env.RENDER_API_URL || DEFAULT_UPSTREAM).replace(/\/$/, "");
  const resp = await fetch(`${upstream}/ping`, { method: "GET" });
  return new Response(resp.body, {
    status: resp.status,
    headers: { "content-type": resp.headers.get("content-type") || "text/plain" },
  });
}
