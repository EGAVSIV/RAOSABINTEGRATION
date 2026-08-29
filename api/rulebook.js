const crypto = require("crypto");

const REPO = "EGAVSIV/RAOSABINTEGRATION";
const BRANCH = "main";
const ORIGIN_OK = new Set(["https://raosab.in", "https://www.raosab.in"]);
const MAX_FILE_BYTES = 3 * 1024 * 1024;

function cors(req, res) {
  const origin = req.headers.origin;
  if (ORIGIN_OK.has(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Access-Control-Allow-Credentials", "true");
  }
  res.setHeader("Vary", "Origin");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
}
function json(res, status, body) { res.status(status).json(body); }
function sign(value) { return crypto.createHmac("sha256", process.env.RULEBOOK_SESSION_SECRET || "").update(value).digest("hex"); }
function makeSession() { const payload = `${Date.now()}.${crypto.randomBytes(24).toString("hex")}`; return `${Buffer.from(payload).toString("base64url")}.${sign(payload)}`; }
function validSession(req) {
  const raw = req.cookies?.rulebook_session || "";
  const [encoded, mac] = raw.split(".");
  if (!encoded || !mac) return false;
  const payload = Buffer.from(encoded, "base64url").toString("utf8");
  if (sign(payload) !== mac) return false;
  const ts = Number(payload.split(".")[0]);
  return Number.isFinite(ts) && Date.now() - ts < 8 * 60 * 60 * 1000;
}
function setSession(res) { res.setHeader("Set-Cookie", `rulebook_session=${makeSession()}; Path=/; Max-Age=28800; HttpOnly; Secure; SameSite=None`); }
function clearSession(res) { res.setHeader("Set-Cookie", "rulebook_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=None"); }
function ghHeaders() { return { Accept: "application/vnd.github+json", Authorization: `Bearer ${process.env.GITHUB_TOKEN}`, "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json" }; }
async function github(path, options = {}) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${path}`, { ...options, headers: { ...ghHeaders(), ...(options.headers || {}) } });
  const text = await r.text(); let data = {}; try { data = text ? JSON.parse(text) : {}; } catch {}
  if (!r.ok) throw new Error(data.message || text || `GitHub API ${r.status}`);
  return data;
}
async function getRules() {
  try {
    const data = await github("rulebook/rules.json?ref=" + BRANCH, { method: "GET" });
    const decoded = Buffer.from(data.content.replace(/\n/g, ""), "base64").toString("utf8");
    const parsed = JSON.parse(decoded || "[]");
    return { rules: Array.isArray(parsed) ? parsed : (parsed.rules || []), sha: data.sha };
  } catch (e) {
    if (String(e.message).includes("Not Found")) return { rules: [], sha: null };
    throw e;
  }
}
async function putFile(path, base64, message, sha = null) {
  const body = { message, content: base64, branch: BRANCH }; if (sha) body.sha = sha;
  return github(path, { method: "PUT", body: JSON.stringify(body) });
}
function safeName(name) { return String(name || "file").replace(/[^a-zA-Z0-9._-]/g, "_").slice(0, 140); }

module.exports = async function handler(req, res) {
  cors(req, res);
  if (req.method === "OPTIONS") return res.status(204).end();
  try {
    if (req.method === "GET") return json(res, 200, { ok: true, service: "RaoSab Rulebook API" });
    if (req.method !== "POST") return json(res, 405, { ok: false, error: "Method not allowed" });
    const body = req.body || {};
    if (body.action === "login") {
      if (!process.env.RULEBOOK_PASSWORD || body.password !== process.env.RULEBOOK_PASSWORD) return json(res, 401, { ok: false, error: "Invalid password" });
      setSession(res); return json(res, 200, { ok: true });
    }
    if (body.action === "logout") { clearSession(res); return json(res, 200, { ok: true }); }
    if (!validSession(req)) return json(res, 401, { ok: false, error: "Not authenticated" });

    if (body.action === "upload") {
      const size = Number(body.size || 0), b64 = String(body.content || "");
      if (!size || size > MAX_FILE_BYTES) return json(res, 413, { ok: false, error: "File exceeds 3 MB API limit." });
      if (!b64) return json(res, 400, { ok: false, error: "File content missing" });
      const folder = body.kind === "pdf" ? "pdf" : "images";
      const filename = `${body.id || crypto.randomUUID()}_${Date.now()}_${safeName(body.name)}`;
      const path = `rulebook/uploads/${folder}/${filename}`;
      await putFile(path, b64, `rulebook: upload ${safeName(body.name)}`);
      return json(res, 200, { ok: true, path: `uploads/${folder}/${filename}` });
    }

    if (body.action === "save") {
      if (!body.rule || !body.rule.id || !body.rule.title) return json(res, 400, { ok: false, error: "Rule data is incomplete" });
      const current = await getRules();
      const next = Array.isArray(current.rules) ? [...current.rules] : [];
      const index = next.findIndex(x => x.id === body.rule.id);
      if (index >= 0) next[index] = body.rule; else next.push(body.rule);
      const encoded = Buffer.from(JSON.stringify(next, null, 2) + "\n", "utf8").toString("base64");
      await putFile("rulebook/rules.json", encoded, `rulebook: ${index >= 0 ? "update" : "add"} rule ${body.rule.title}`, current.sha);
      return json(res, 200, { ok: true, rules: next });
    }

    if (body.action === "delete") {
      if (!body.id) return json(res, 400, { ok: false, error: "Rule id missing" });
      const current = await getRules();
      const next = current.rules.filter(x => x.id !== body.id);
      const encoded = Buffer.from(JSON.stringify(next, null, 2) + "\n", "utf8").toString("base64");
      await putFile("rulebook/rules.json", encoded, `rulebook: delete rule ${body.id}`, current.sha);
      return json(res, 200, { ok: true, rules: next });
    }
    return json(res, 400, { ok: false, error: "Unknown action" });
  } catch (e) {
    console.error(e); return json(res, 500, { ok: false, error: e.message || "Server error" });
  }
};

module.exports.config = { api: { bodyParser: { sizeLimit: "4mb" } } };
