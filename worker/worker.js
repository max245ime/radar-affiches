// Radar Affiches — serveur de notifications push (Cloudflare Workers + KV).
// Routes : POST /subscribe, POST /unsubscribe, GET /last, POST /notify (protégée par PUSH_SECRET).
// Les pushes sont envoyés SANS contenu (simple « réveil ») : le service worker de l'app va lire /last pour afficher le texte.
const enc = new TextEncoder();
const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const MAX_SUBS = 25;

const cors = (env) => ({
  "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
});
const json = (env, obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...cors(env) } });

async function hash(s) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)))].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 40);
}

export async function vapidHeader(endpoint, env) {
  const jwk = JSON.parse(env.VAPID_PRIVATE_JWK);
  const key = await crypto.subtle.importKey("jwk", jwk, { name: "ECDSA", namedCurve: "P-256" }, false, ["sign"]);
  const head = b64u(enc.encode(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const claims = b64u(enc.encode(JSON.stringify({
    aud: new URL(endpoint).origin,
    exp: Math.floor(Date.now() / 1000) + 12 * 3600,
    sub: env.VAPID_SUBJECT || "mailto:radar-affiches@users.noreply.github.com",
  })));
  const sig = await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, enc.encode(`${head}.${claims}`));
  return `vapid t=${head}.${claims}.${b64u(sig)}, k=${env.VAPID_PUBLIC}`;
}

async function pushOne(sub, env) {
  const r = await fetch(sub.endpoint, {
    method: "POST",
    headers: { Authorization: await vapidHeader(sub.endpoint, env), TTL: "86400", Urgency: "high" },
  });
  return r.status;
}

export async function broadcast(env, m) {
  await env.KV.put("last", JSON.stringify({ title: String(m.title || "🎬 Radar Affiches").slice(0, 120), body: String(m.message || "").slice(0, 600), url: m.click || "./", ts: Date.now() }));
  const keys = (await env.KV.list({ prefix: "sub:" })).keys;
  let sent = 0, removed = 0, failed = 0;
  for (const k of keys) {
    const sub = JSON.parse(await env.KV.get(k.name));
    try {
      const st = await pushOne(sub, env);
      if (st === 404 || st === 410) { await env.KV.delete(k.name); removed++; }
      else if (st >= 200 && st < 300) sent++; else failed++;
    } catch { failed++; }
  }
  return { sent, removed, failed, subscribers: keys.length };
}

// Veilleur : indépendant de GitHub. Lancé par un Cron Trigger Cloudflare.
export async function watchdog(env, now = Date.now()) {
  if (!env.DATA_URL) return "DATA_URL absent";
  const stale = (Number(env.STALE_HOURS) || 13) * 3600e3;
  let problem = "";
  try {
    const r = await fetch(env.DATA_URL + "?t=" + now, { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const d = await r.json();
    const times = (d.cinemas || []).map((c) => Date.parse(c.last_ok)).filter(Number.isFinite);
    const age = now - (times.length ? Math.min(...times) : Date.parse(d.updated));
    if (!Number.isFinite(age)) problem = "données illisibles";
    else if (age > stale) problem = `aucun relevé réussi depuis ${Math.round(age / 3600e3)} h`;
  } catch (e) { problem = `données injoignables (${e.message})`; }
  const st = JSON.parse((await env.KV.get("wd")) || '{"bad":false,"at":0}');
  const click = env.APP_URL || "./";
  if (problem) {
    if (!st.bad || now - st.at > 24 * 3600e3) {
      await broadcast(env, { title: "⚠️ Radar Affiches : surveillance en panne ?", click,
        message: `${problem}.\nLe scan automatique ne semble plus tourner : GitHub → Actions → Radar Affiches → Run workflow, et préviens-moi.` });
      await env.KV.put("wd", JSON.stringify({ bad: true, at: now }));
      return "alerte envoyée";
    }
    return "problème déjà signalé";
  }
  if (st.bad) {
    await broadcast(env, { title: "✅ Radar Affiches : surveillance rétablie", message: "Les relevés fonctionnent de nouveau.", click });
    await env.KV.put("wd", JSON.stringify({ bad: false, at: now }));
    return "rétabli";
  }
  return "ok";
}

export default {
  async scheduled(event, env, ctx) { ctx.waitUntil(watchdog(env)); },
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { headers: cors(env) });

    if (url.pathname === "/subscribe" && req.method === "POST") {
      let sub; try { sub = await req.json(); } catch { return json(env, { error: "json" }, 400); }
      if (!sub?.endpoint?.startsWith("https://") || !sub?.keys?.p256dh || !sub?.keys?.auth) return json(env, { error: "abonnement invalide" }, 400);
      const id = "sub:" + await hash(sub.endpoint);
      if (!(await env.KV.get(id))) {
        const n = (await env.KV.list({ prefix: "sub:" })).keys.length;
        if (n >= MAX_SUBS) return json(env, { error: "trop d'abonnés" }, 429);
      }
      await env.KV.put(id, JSON.stringify({ endpoint: sub.endpoint, keys: sub.keys }));
      return json(env, { ok: true });
    }
    if (url.pathname === "/unsubscribe" && req.method === "POST") {
      let sub; try { sub = await req.json(); } catch { return json(env, { error: "json" }, 400); }
      if (sub?.endpoint) await env.KV.delete("sub:" + await hash(sub.endpoint));
      return json(env, { ok: true });
    }
    if (url.pathname === "/last" && req.method === "GET") {
      const last = await env.KV.get("last");
      return new Response(last || JSON.stringify({ title: "🎬 Radar Affiches", body: "Nouvelle alerte", url: "./" }),
        { headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...cors(env) } });
    }
    if (url.pathname === "/notify" && req.method === "POST") {
      if (!env.PUSH_SECRET || req.headers.get("Authorization") !== `Bearer ${env.PUSH_SECRET}`) return json(env, { error: "non autorisé" }, 401);
      let m; try { m = await req.json(); } catch { return json(env, { error: "json" }, 400); }
      return json(env, await broadcast(env, m));
    }
    return json(env, { name: "radar-push", ok: true });
  },
};
