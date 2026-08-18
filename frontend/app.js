"use strict";

const TOKEN = window.MAILY_TOKEN || "";
const AUTH = { headers: { Authorization: "Bearer " + TOKEN } };
const PALETTE = ["#2e5fff", "#18c07a", "#f5a524", "#c159f5", "#ef476f", "#0e91d8"];

const state = { accountId: null, currentId: null, query: "" };
const accountColors = {};

const el = (sel) => document.querySelector(sel);

async function api(path) {
  const r = await fetch(path, AUTH);
  if (!r.ok) throw new Error(path + " -> " + r.status);
  return r.json();
}

function banner(msg) {
  let b = el(".banner");
  if (!b) {
    b = document.createElement("div");
    b.className = "banner";
    el(".win").insertBefore(b, el(".body"));
  }
  b.textContent = msg;
  b.classList.add("show");
}

function fromName(addr) {
  if (!addr) return "(inconnu)";
  const m = addr.match(/^\s*"?([^"<]+?)"?\s*<.+>/);
  return (m ? m[1] : addr).trim();
}

const TZ = "Europe/Paris";

function fmtDate(ms) {
  if (!ms) return "";
  const d = new Date(Number(ms));
  const dParis = d.toLocaleDateString("fr-FR", { timeZone: TZ });
  const nowParis = new Date().toLocaleDateString("fr-FR", { timeZone: TZ });
  return dParis === nowParis
    ? d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: TZ })
    : d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", timeZone: TZ });
}

function orb(color) {
  return `<span class="orb" style="background:linear-gradient(180deg, ${color}cc, ${color})"></span>`;
}

async function loadAccounts() {
  const accs = await api("/accounts");
  state.accounts = accs;
  accs.forEach((a, i) => { accountColors[a.id] = a.color || PALETTE[i % PALETTE.length]; });
  const rail = el("#rail");
  rail.innerHTML = "";

  const all = document.createElement("div");
  all.className = "nav" + (state.accountId === null ? " on" : "");
  all.innerHTML = `<span>📥</span> Tout (unifié)`;
  all.onclick = () => selectAccount(null);
  rail.appendChild(all);

  accs.forEach((a) => {
    const n = document.createElement("div");
    n.className = "nav" + (state.accountId === a.id ? " on" : "");
    const label = (a.display_name || a.email);
    n.innerHTML = `${orb(accountColors[a.id])}<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${label}</span>`;
    n.title = a.email;
    n.onclick = () => selectAccount(a.id);
    rail.appendChild(n);
  });

  const sep = document.createElement("div");
  sep.className = "rail-sep";
  sep.textContent = "Dossiers";
  rail.appendChild(sep);
  ["🏷️ Libellés", "🗄️ Archivés", "🗑️ Corbeille"].forEach((t) => {
    const n = document.createElement("div");
    n.className = "nav"; n.style.opacity = ".6"; n.textContent = t;
    rail.appendChild(n);
  });
}

function selectAccount(id) {
  state.accountId = id;
  state.query = "";
  el("#search").value = "";
  loadAccounts();
  loadMessages();
}

async function loadMessages() {
  const list = el("#list");
  let msgs;
  try {
    if (state.query) {
      const q = "/search?q=" + encodeURIComponent(state.query) +
        (state.accountId ? "&account_id=" + state.accountId : "");
      msgs = await api(q);
    } else {
      const q = "/messages" + (state.accountId ? "?account_id=" + state.accountId : "");
      msgs = await api(q);
    }
  } catch (e) { banner("Erreur de chargement : " + e.message); return; }

  list.innerHTML = "";
  if (!msgs.length) {
    list.innerHTML = `<div style="padding:20px;color:var(--ink-soft);font-size:13px">Aucun message. Clique sur « Synchroniser ».</div>`;
    return;
  }
  msgs.forEach((m) => {
    const row = document.createElement("div");
    row.className = "li" + (m.id === state.currentId ? " on" : "");
    const color = accountColors[m.account_id] || "#888";
    row.innerHTML =
      `<div class="li-top">
         <span class="li-dot ${m.is_unread ? "" : "read"}"></span>
         <span class="li-from" style="color:${m.is_unread ? "var(--ink)" : "var(--ink-soft)"}">${fromName(m.addr_from)}</span>
         <span class="li-time">${fmtDate(m.internal_date)}</span>
       </div>
       <div class="li-subj">${(m.subject || "(sans sujet)").replace(/</g, "&lt;")}</div>`;
    row.onclick = () => openMessage(m.id);
    list.appendChild(row);
  });
}

const BASE_CSS = `
  :root { color-scheme: light; }
  html, body { margin: 0; background: #fff; }
  body { font: 14px/1.55 -apple-system, 'Segoe UI', system-ui, sans-serif; color: #14323F;
    padding: 18px 22px; word-wrap: break-word; overflow-wrap: break-word; }
  img { max-width: 100%; height: auto; }
  img:not([src]), img[src=""] { display: none; }
  a { color: #0e6f97; }
  table { max-width: 100%; }
  blockquote { margin: 0 0 0 12px; padding-left: 12px; border-left: 3px solid rgba(20,50,63,.2); color: rgba(20,50,63,.75); }
  pre { white-space: pre-wrap; word-wrap: break-word; font: 14px/1.55 -apple-system, 'Segoe UI', system-ui, sans-serif; }
`;

function esc(s) { return (s || "").replace(/</g, "&lt;"); }

function buildDoc(fragment) {
  return `<!doctype html><html><head><meta charset="utf-8">` +
    `<meta name="viewport" content="width=device-width,initial-scale=1">` +
    `<style>${BASE_CSS}</style></head><body>${fragment}</body></html>`;
}

async function fetchHtml(id, allowRemote) {
  const url = "/messages/" + id + "/html" + (allowRemote ? "?allow_remote=true" : "");
  const r = await fetch(url, AUTH);
  return await r.text();
}

async function openMessage(id) {
  state.currentId = id;
  let m;
  try { m = await api("/messages/" + id); }
  catch (e) { banner("Erreur : " + e.message); return; }

  const read = el("#read");
  read.innerHTML = "";
  const head = document.createElement("div");
  head.className = "read-head";
  head.innerHTML =
    `<h1 class="read-subj">${esc(m.subject) || "(sans sujet)"}</h1>
     <div class="read-meta">${esc(m.addr_from)} · ${fmtDate(m.internal_date)}</div>
     <div class="read-actions">
       <button class="gel" id="replybtn">↩︎ Répondre</button>
       <button class="ghost" id="fwdbtn">➦ Transférer</button>
       <button class="ghost">🗄️ Archiver</button>
       <button class="ghost" id="imgbtn">🖼️ Charger les images</button>
     </div>`;
  read.appendChild(head);

  head.querySelector("#replybtn").onclick = () => replyTo(m);
  head.querySelector("#fwdbtn").onclick = () => forward(m);

  const frame = document.createElement("iframe");
  frame.className = "read-frame";
  frame.setAttribute("sandbox", "");
  read.appendChild(frame);

  async function render(allowRemote) {
    let html;
    try { html = await fetchHtml(id, allowRemote); }
    catch (e) { banner("Erreur : " + e.message); return; }
    const body = (html && html.trim()) ? html : `<pre>${esc(m.body_text) || "(vide)"}</pre>`;
    frame.srcdoc = buildDoc(body);
  }

  const imgbtn = head.querySelector("#imgbtn");
  imgbtn.onclick = () => { imgbtn.textContent = "🖼️ Images affichées"; imgbtn.disabled = true; render(true); };
  render(false);

  loadMessages();
}

async function syncAll() {
  const btn = el("#sync");
  btn.classList.add("spinning");
  btn.textContent = "⟳ Synchro…";
  try {
    const accs = await api("/accounts");
    for (const a of accs) {
      await fetch("/accounts/" + a.id + "/sync", { method: "POST", ...AUTH });
      await loadMessages();  // affichage progressif compte par compte
    }
  } catch (e) { banner("Erreur de synchro : " + e.message); }
  btn.classList.remove("spinning");
  btn.textContent = "⟳ Synchroniser";
}

function initSearch() {
  let t;
  el("#search").addEventListener("input", (e) => {
    clearTimeout(t);
    state.query = e.target.value.trim();
    t = setTimeout(loadMessages, 250);
  });
}

function emailOnly(addr) {
  const m = (addr || "").match(/<([^>]+)>/);
  return (m ? m[1] : addr || "").trim();
}

function openComposer(prefill) {
  const fromSel = el("#c-from");
  fromSel.innerHTML = "";
  (state.accounts || []).forEach((a) => {
    const o = document.createElement("option");
    o.value = a.id;
    o.textContent = a.display_name || a.email;
    fromSel.appendChild(o);
  });
  if (prefill.accountId) fromSel.value = prefill.accountId;
  el("#composer-title").textContent = prefill.title || "Nouveau message";
  el("#c-to").value = prefill.to || "";
  el("#c-cc").value = "";
  el("#c-subject").value = prefill.subject || "";
  el("#c-body").value = prefill.body || "";
  el("#c-status").textContent = "";
  const c = el("#composer");
  c.dataset.inReplyTo = prefill.inReplyTo || "";
  c.dataset.threadId = prefill.threadId || "";
  c.hidden = false;
  el("#c-to").focus();
}

function closeComposer() { el("#composer").hidden = true; }

async function sendComposer() {
  const status = el("#c-status");
  const to = el("#c-to").value.trim();
  if (!to) { status.textContent = "Ajoute au moins un destinataire."; return; }
  const payload = {
    account_id: Number(el("#c-from").value),
    to,
    cc: el("#c-cc").value.trim() || null,
    subject: el("#c-subject").value,
    body_text: el("#c-body").value,
    in_reply_to: el("#composer").dataset.inReplyTo || null,
    thread_id: el("#composer").dataset.threadId || null,
  };
  status.textContent = "Envoi…";
  el("#c-send").disabled = true;
  try {
    const r = await fetch("/send", {
      method: "POST",
      headers: { ...AUTH.headers, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(r.status + " " + (await r.text()));
    closeComposer();
    banner("Message envoyé.");
    fetch("/accounts/" + payload.account_id + "/sync", { method: "POST", ...AUTH })
      .then(loadMessages).catch(() => {});
  } catch (e) {
    status.textContent = "Échec de l'envoi : " + e.message;
  }
  el("#c-send").disabled = false;
}

function replyTo(m) {
  openComposer({
    title: "Répondre",
    accountId: m.account_id,
    to: emailOnly(m.addr_from),
    subject: /^re\s*:/i.test(m.subject || "") ? m.subject : "Re: " + (m.subject || ""),
    inReplyTo: m.rfc822_message_id || "",
    threadId: m.thread_id || "",
    body: "\n\n----- Message d'origine -----\n" + (m.body_text || ""),
  });
}

function forward(m) {
  openComposer({
    title: "Transférer",
    accountId: m.account_id,
    subject: /^tr\s*:/i.test(m.subject || "") ? m.subject : "Tr: " + (m.subject || ""),
    body: "\n\n----- Message transféré -----\nDe : " + (m.addr_from || "") +
      "\nObjet : " + (m.subject || "") + "\n\n" + (m.body_text || ""),
  });
}

async function main() {
  el("#sync").onclick = syncAll;
  el("#compose").onclick = () => openComposer({ accountId: state.accountId || undefined });
  el("#c-close").onclick = closeComposer;
  el("#c-cancel").onclick = closeComposer;
  el("#c-send").onclick = sendComposer;
  el("#composer").addEventListener("click", (e) => { if (e.target.id === "composer") closeComposer(); });
  initSearch();
  try {
    await loadAccounts();
    await loadMessages();
  } catch (e) {
    banner("Impossible de contacter l'API locale : " + e.message);
  }
}

main();
