/**
 * Proxy /api/* to Render. Rewrites Set-Cookie so sessions work on *.pages.dev.
 */
const API_ORIGIN = "https://bot-wf8x.onrender.com";
const UPSTREAM_TIMEOUT_MS = 55_000;

function rewriteSetCookie(raw) {
  return raw
    .replace(/;\s*Domain=[^;]*/gi, "")
    .replace(/;\s*Secure/gi, "; Secure")
    .replace(/;\s*SameSite=[^;]*/gi, "; SameSite=Lax");
}

export async function onRequest(context) {
  const incoming = new URL(context.request.url);
  const target = new URL(incoming.pathname + incoming.search, API_ORIGIN);

  const headers = new Headers(context.request.headers);
  headers.delete("host");

  const init = {
    method: context.request.method,
    headers,
    redirect: "manual",
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  };
  if (context.request.method !== "GET" && context.request.method !== "HEAD") {
    init.body = await context.request.arrayBuffer();
  }

  let upstream;
  try {
    upstream = await fetch(target.toString(), init);
  } catch {
    return new Response(
      JSON.stringify({
        detail:
          "Backend is waking up or unreachable. Wait a minute and try again.",
      }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
  const outHeaders = new Headers(upstream.headers);

  outHeaders.delete("set-cookie");
  const cookies =
    typeof upstream.headers.getSetCookie === "function"
      ? upstream.headers.getSetCookie()
      : [];
  if (cookies.length === 0) {
    const single = upstream.headers.get("set-cookie");
    if (single) cookies.push(single);
  }
  for (const c of cookies) {
    outHeaders.append("set-cookie", rewriteSetCookie(c));
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: outHeaders,
  });
}
