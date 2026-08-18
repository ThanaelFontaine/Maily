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

function fmtDate(ms) {
  if (!ms) return "";
  const d = new Date(Number(ms));
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
}

function orb(color) {
  return `<span class="orb" style="background:linear-gradient(180deg, ${color}cc, ${color})"></span>`;
}

async function loadAccounts() {
  const accs = await api("/accounts");
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

async function openMessage(id) {
  state.currentId = id;
  document.querySelectorAll(".li").forEach((r) => r.classList.remove("on"));
  let m, html;
  try {
    m = await api("/messages/" + id);
    const r = await fetch("/messages/" + id + "/html", AUTH);
    html = await r.text();
  } catch (e) { banner("Erreur : " + e.message); return; }

  const read = el("#read");
  read.innerHTML = "";
  const head = document.createElement("div");
  head.className = "read-head";
  head.innerHTML =
    `<h1 class="read-subj">${(m.subject || "(sans sujet)").replace(/</g, "&lt;")}</h1>
     <div class="read-meta">${(m.addr_from || "").replace(/</g, "&lt;")} · ${fmtDate(m.internal_date)}</div>
     <div class="read-actions">
       <button class="gel">↩︎ Répondre</button>
       <button class="ghost">➦ Transférer</button>
       <button class="ghost">🗄️ Archiver</button>
     </div>`;
  read.appendChild(head);

  const frame = document.createElement("iframe");
  frame.className = "read-frame";
  frame.setAttribute("sandbox", "");
  frame.srcdoc = html && html.trim()
    ? html
    : `<pre style="font-family:system-ui;white-space:pre-wrap;padding:16px;color:#14323F">${(m.body_text || "(vide)").replace(/</g, "&lt;")}</pre>`;
  read.appendChild(frame);

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
    }
    await loadMessages();
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

async function main() {
  el("#sync").onclick = syncAll;
  el("#compose").onclick = () => banner("La composition arrive bientôt (prochaine étape).");
  initSearch();
  try {
    await loadAccounts();
    await loadMessages();
  } catch (e) {
    banner("Impossible de contacter l'API locale : " + e.message);
  }
}

main();
