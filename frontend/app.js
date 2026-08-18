"use strict";

const TOKEN = window.MAILY_TOKEN || "";
const AUTH = { headers: { Authorization: "Bearer " + TOKEN } };
const PALETTE = ["#2e5fff", "#18c07a", "#f5a524", "#c159f5", "#ef476f", "#0e91d8"];
const TZ = "Europe/Paris";

const CATEGORIES = [
  { key: "primary", label: "Principale", icon: "📥" },
  { key: "promotions", label: "Promotions", icon: "🏷️" },
  { key: "social", label: "Réseaux sociaux", icon: "👥" },
  { key: "updates", label: "Notifications", icon: "🔔" },
];

const state = {
  accountId: null, currentId: null, query: "", tabs: [],
  folder: { type: "inbox" }, category: "primary", accounts: [], currentMsgs: [], composerAtts: [],
};
const accountColors = {};
const el = (sel) => document.querySelector(sel);

async function api(path) {
  const r = await fetch(path, AUTH);
  if (!r.ok) throw new Error(path + " -> " + r.status);
  return r.json();
}

async function postAction(path, body) {
  const headers = { ...AUTH.headers };
  const opts = { method: "POST", headers };
  if (body !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(r.status + " " + (await r.text()));
  return r.json();
}

function banner(msg) {
  let b = el(".banner");
  if (!b) { b = document.createElement("div"); b.className = "banner"; el(".win").insertBefore(b, el(".body")); }
  b.textContent = msg;
  b.classList.add("show");
}

function esc(s) { return (s || "").replace(/</g, "&lt;"); }

function fromName(addr) {
  if (!addr) return "(inconnu)";
  const m = addr.match(/^\s*"?([^"<]+?)"?\s*<.+>/);
  return (m ? m[1] : addr).trim();
}

function emailOnly(addr) {
  const m = (addr || "").match(/<([^>]+)>/);
  return (m ? m[1] : addr || "").trim();
}

function fmtDate(ms) {
  if (!ms) return "";
  const d = new Date(Number(ms));
  const dParis = d.toLocaleDateString("fr-FR", { timeZone: TZ });
  const nowParis = new Date().toLocaleDateString("fr-FR", { timeZone: TZ });
  return dParis === nowParis
    ? d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: TZ })
    : d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", timeZone: TZ });
}

function fmtSize(b) {
  if (!b) return "";
  const k = b / 1024;
  return k < 1024 ? Math.round(k) + " Ko" : (k / 1024).toFixed(1) + " Mo";
}

function orb(color) {
  return `<span class="orb" style="background:linear-gradient(180deg, ${color}cc, ${color})"></span>`;
}

function updateLayout() {
  el("#appbody").classList.toggle("no-read", !state.currentId);
}

/* ------------------------- Rail : comptes + dossiers ------------------------- */

async function loadAccounts() {
  const accs = await api("/accounts");
  state.accounts = accs;
  accs.forEach((a, i) => { accountColors[a.id] = a.color || PALETTE[i % PALETTE.length]; });
  const rail = el("#rail");
  rail.innerHTML = "";

  const all = document.createElement("div");
  all.className = "nav" + (state.accountId === null ? " on" : "");
  all.innerHTML = `<span class="nav-ico">📥</span> Tout (unifié)`;
  all.onclick = () => selectAccount(null);
  rail.appendChild(all);

  accs.forEach((a) => {
    const n = document.createElement("div");
    n.className = "nav" + (state.accountId === a.id ? " on" : "");
    const label = a.display_name || a.email;
    n.innerHTML = `${orb(accountColors[a.id])}<span class="nav-lbl">${esc(label)}</span>`;
    n.title = a.email;
    n.onclick = () => selectAccount(a.id);
    rail.appendChild(n);
  });

  if (state.accountId !== null) await loadFolders(state.accountId);
}

async function loadFolders(accountId) {
  let labels = [];
  try { labels = await api(`/accounts/${accountId}/labels`); } catch { /* ignore */ }
  const rail = el("#rail");

  const sep = document.createElement("div");
  sep.className = "rail-sep";
  sep.textContent = "Dossiers";
  rail.appendChild(sep);

  const special = [
    { name: "Boîte de réception", icon: "📥", folder: { type: "inbox" } },
    { name: "Archivés", icon: "🗄️", folder: { type: "archived" } },
    { name: "Corbeille", icon: "🗑️", folder: { type: "trash" } },
  ];
  special.forEach((s) => rail.appendChild(folderNav(s.icon, s.name, s.folder)));

  const userLabels = labels.filter((l) => l.type === "user" && l.name);
  if (userLabels.length) {
    const sep2 = document.createElement("div");
    sep2.className = "rail-sep";
    sep2.textContent = "Libellés";
    rail.appendChild(sep2);
    userLabels.forEach((l) =>
      rail.appendChild(folderNav("🏷️", l.name, { type: "label", id: l.gmail_label_id, name: l.name })));
  }
}

function folderNav(icon, name, folder) {
  const n = document.createElement("div");
  const active = JSON.stringify(state.folder) === JSON.stringify(folder);
  n.className = "nav nav-folder" + (active ? " on" : "");
  n.innerHTML = `<span class="nav-ico">${icon}</span><span class="nav-lbl">${esc(name)}</span>`;
  n.onclick = () => selectFolder(folder);
  return n;
}

function selectAccount(id) {
  state.accountId = id;
  state.folder = { type: "inbox" };
  state.category = "primary";
  state.query = "";
  el("#search").value = "";
  loadAccounts();
  renderCats();
  loadMessages();
}

function selectFolder(folder) {
  state.folder = folder;
  state.category = "primary";
  state.query = "";
  el("#search").value = "";
  loadAccounts();
  renderCats();
  loadMessages();
}

/* ------------------------- Onglets de catégories Gmail ------------------------- */

function renderCats() {
  const cats = el("#cats");
  const showCats = state.folder.type === "inbox" && !state.query;
  if (!showCats) { cats.innerHTML = ""; cats.style.display = "none"; return; }
  cats.style.display = "flex";
  cats.innerHTML = "";
  CATEGORIES.forEach((c) => {
    const t = document.createElement("div");
    t.className = "cat" + (state.category === c.key ? " on" : "");
    t.innerHTML = `<span>${c.icon}</span> ${c.label}`;
    t.onclick = () => { state.category = c.key; renderCats(); loadMessages(); };
    cats.appendChild(t);
  });
}

function listTitle() {
  if (state.query) return "Recherche : " + state.query;
  if (state.folder.type === "archived") return "Archivés";
  if (state.folder.type === "trash") return "Corbeille";
  if (state.folder.type === "label") return state.folder.name;
  return "";
}

/* ------------------------- Liste des messages ------------------------- */

function messagesQuery() {
  if (state.query) {
    return "/search?q=" + encodeURIComponent(state.query) +
      (state.accountId ? "&account_id=" + state.accountId : "");
  }
  let q = "/messages?";
  const p = [];
  if (state.accountId) p.push("account_id=" + state.accountId);
  if (state.folder.type === "inbox") p.push("category=" + state.category);
  else if (state.folder.type === "archived") p.push("archived=true");
  else if (state.folder.type === "trash") p.push("trashed=true");
  else if (state.folder.type === "label") p.push("label=" + encodeURIComponent(state.folder.id));
  return q + p.join("&");
}

async function loadMessages() {
  const list = el("#list");
  el("#listbar-title").textContent = listTitle();
  let msgs;
  try { msgs = await api(messagesQuery()); }
  catch (e) { banner("Erreur de chargement : " + e.message); return; }
  state.currentMsgs = msgs;

  list.innerHTML = "";
  if (!msgs.length) {
    list.innerHTML = `<div class="list-empty">Aucun message ici. Clique sur « Synchroniser » si besoin.</div>`;
    return;
  }
  msgs.forEach((m) => {
    const row = document.createElement("div");
    row.className = "li" + (m.id === state.currentId ? " on" : "");
    row.innerHTML =
      `<div class="li-top">
         <span class="li-dot ${m.is_unread ? "" : "seen"}"></span>
         <span class="li-from" style="color:${m.is_unread ? "var(--ink)" : "var(--ink-soft)"}">${esc(fromName(m.addr_from))}</span>
         <span class="li-time">${fmtDate(m.internal_date)}</span>
       </div>
       <div class="li-subj">${esc(m.subject) || "(sans sujet)"}</div>`;
    row.onclick = (e) => {
      if (e.metaKey || e.ctrlKey) openInTab(m.id, m.subject);
      else openSingle(m.id);
    };
    list.appendChild(row);
  });
}

async function markAllRead() {
  const unread = state.currentMsgs.filter((m) => m.is_unread);
  if (!unread.length) { banner("Aucun message non lu ici."); return; }
  const btn = el("#markread");
  btn.disabled = true;
  try {
    for (const m of unread) {
      await postAction(`/messages/${m.id}/modify`, { remove_labels: ["UNREAD"] });
    }
    banner(`${unread.length} message(s) marqué(s) comme lu(s).`);
    await loadMessages();
  } catch (e) { banner("Erreur : " + e.message); }
  btn.disabled = false;
}

/* ------------------------- Lecture d'un message ------------------------- */

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

function buildDoc(fragment) {
  return `<!doctype html><html><head><meta charset="utf-8">` +
    `<meta name="viewport" content="width=device-width,initial-scale=1">` +
    `<style>${BASE_CSS}</style></head><body>${fragment}</body></html>`;
}

async function fetchHtml(id) {
  const r = await fetch("/messages/" + id + "/html?allow_remote=true", AUTH);
  return await r.text();
}

async function renderAttachments(id, wrap) {
  let atts;
  try { atts = await api(`/messages/${id}/attachments`); }
  catch { wrap.style.display = "none"; return; }
  const real = atts.filter((a) => !a.content_id);
  if (!real.length) { wrap.style.display = "none"; return; }
  wrap.innerHTML = real.map((a) =>
    `<button class="att-chip" data-att="${a.id}">📎 ${esc(a.filename) || "fichier"}` +
    `<span class="att-size">${fmtSize(a.size)}</span></button>`).join("");
  wrap.querySelectorAll(".att-chip").forEach((btn) => {
    const att = real.find((x) => String(x.id) === btn.dataset.att);
    btn.onclick = () => downloadAttachment(id, btn.dataset.att, att);
  });
}

async function downloadAttachment(id, attId, att) {
  try {
    const r = await fetch(`/messages/${id}/attachments/${attId}/download`, AUTH);
    if (!r.ok) throw new Error(r.status);
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = (att && att.filename) || "piece-jointe";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  } catch (e) { banner("Téléchargement échoué : " + e.message); }
}

function openSingle(id) { state.tabs = []; openMessage(id); }

function openInTab(id, subject) {
  if (!state.tabs.some((t) => t.id === id)) state.tabs.push({ id, subject });
  openMessage(id);
}

function closeTab(id) {
  state.tabs = state.tabs.filter((t) => t.id !== id);
  if (state.currentId === id) {
    if (state.tabs.length) openMessage(state.tabs[state.tabs.length - 1].id);
    else {
      state.currentId = null;
      el("#read").innerHTML = `<div class="read-empty">Sélectionne un message pour le lire.</div>`;
      updateLayout();
      loadMessages();
    }
  } else if (state.currentId) openMessage(state.currentId);
}

function renderTabBar() {
  const bar = document.createElement("div");
  bar.className = "mailtabs";
  state.tabs.forEach((t) => {
    const chip = document.createElement("div");
    chip.className = "mailtab" + (t.id === state.currentId ? " on" : "");
    chip.innerHTML = `<span class="mailtab-lbl">${esc(t.subject) || "(sans sujet)"}</span>` +
      `<span class="mailtab-x" title="Fermer l'onglet">×</span>`;
    chip.querySelector(".mailtab-lbl").onclick = () => openMessage(t.id);
    chip.querySelector(".mailtab-x").onclick = (e) => { e.stopPropagation(); closeTab(t.id); };
    bar.appendChild(chip);
  });
  return bar;
}

async function openMessage(id) {
  state.currentId = id;
  updateLayout();
  let m;
  try { m = await api("/messages/" + id); }
  catch (e) { banner("Erreur : " + e.message); return; }

  const read = el("#read");
  read.innerHTML = "";
  if (state.tabs.length >= 2) read.appendChild(renderTabBar());

  const head = document.createElement("div");
  head.className = "read-head";
  const inTrash = state.folder.type === "trash";
  head.innerHTML =
    `<h1 class="read-subj">${esc(m.subject) || "(sans sujet)"}</h1>
     <div class="read-meta">${esc(m.addr_from)} · ${fmtDate(m.internal_date)}</div>
     <div class="read-actions">
       <button class="gel" id="replybtn">↩︎ Répondre</button>
       <button class="ghost" id="fwdbtn">➦ Transférer</button>
       ${inTrash
        ? `<button class="ghost" id="untrashbtn">♻️ Restaurer</button>`
        : `<button class="ghost" id="archbtn">🗄️ Archiver</button>
           <button class="ghost" id="trashbtn">🗑️ Corbeille</button>`}
     </div>`;
  read.appendChild(head);

  head.querySelector("#replybtn").onclick = () => replyTo(m);
  head.querySelector("#fwdbtn").onclick = () => forward(m);
  if (inTrash) {
    head.querySelector("#untrashbtn").onclick = async () => {
      try { await postAction(`/messages/${id}/untrash`); afterAction("Restauré."); }
      catch (e) { banner("Erreur : " + e.message); }
    };
  } else {
    head.querySelector("#archbtn").onclick = async () => {
      try { await postAction(`/messages/${id}/modify`, { remove_labels: ["INBOX"] }); afterAction("Archivé."); }
      catch (e) { banner("Erreur : " + e.message); }
    };
    head.querySelector("#trashbtn").onclick = async () => {
      try { await postAction(`/messages/${id}/trash`); afterAction("Déplacé vers la corbeille."); }
      catch (e) { banner("Erreur : " + e.message); }
    };
  }

  const attWrap = document.createElement("div");
  attWrap.className = "attachments";
  read.appendChild(attWrap);
  renderAttachments(id, attWrap);

  const frame = document.createElement("iframe");
  frame.className = "read-frame";
  frame.setAttribute("sandbox", "");
  read.appendChild(frame);

  try {
    const html = await fetchHtml(id);
    const body = (html && html.trim()) ? html : `<pre>${esc(m.body_text) || "(vide)"}</pre>`;
    frame.srcdoc = buildDoc(body);
  } catch (e) { banner("Erreur : " + e.message); }

  if (m.is_unread) {
    postAction(`/messages/${id}/modify`, { remove_labels: ["UNREAD"] }).then(loadMessages).catch(() => {});
  } else {
    loadMessages();
  }
}

function afterAction(msg) {
  banner(msg);
  state.currentId = null;
  state.tabs = [];
  el("#read").innerHTML = `<div class="read-empty">${esc(msg)}</div>`;
  updateLayout();
  loadMessages();
}

/* ------------------------- Composition ------------------------- */

function openComposer(prefill) {
  const fromSel = el("#c-from");
  fromSel.innerHTML = "";
  (state.accounts || []).forEach((a) => {
    const o = document.createElement("option");
    o.value = a.id; o.textContent = a.display_name || a.email;
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
  state.composerAtts = [];
  renderComposerAtts();
  c.hidden = false;
  el("#c-to").focus();
}

function closeComposer() { el("#composer").hidden = true; }

function renderComposerAtts() {
  const wrap = el("#c-atts");
  const atts = state.composerAtts || [];
  wrap.innerHTML = atts.map((a, i) =>
    `<span class="c-att">📎 ${esc(a.filename)}<span class="c-att-x" data-i="${i}">×</span></span>`).join("");
  wrap.querySelectorAll(".c-att-x").forEach((x) => {
    x.onclick = () => { state.composerAtts.splice(Number(x.dataset.i), 1); renderComposerAtts(); };
  });
}

function addComposerFiles(fileList) {
  [...fileList].forEach((f) => {
    const reader = new FileReader();
    reader.onload = () => {
      const data = String(reader.result).split(",")[1] || "";
      state.composerAtts.push({ filename: f.name, mime_type: f.type || "application/octet-stream", data });
      renderComposerAtts();
    };
    reader.readAsDataURL(f);
  });
  el("#c-file").value = "";
}

async function sendComposer() {
  const status = el("#c-status");
  const to = el("#c-to").value.trim();
  if (!to) { status.textContent = "Ajoute au moins un destinataire."; return; }
  const payload = {
    account_id: Number(el("#c-from").value),
    to, cc: el("#c-cc").value.trim() || null,
    subject: el("#c-subject").value,
    body_text: el("#c-body").value,
    in_reply_to: el("#composer").dataset.inReplyTo || null,
    thread_id: el("#composer").dataset.threadId || null,
    attachments: state.composerAtts || [],
  };
  status.textContent = "Envoi…";
  el("#c-send").disabled = true;
  try {
    const r = await fetch("/send", {
      method: "POST", headers: { ...AUTH.headers, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(r.status + " " + (await r.text()));
    closeComposer();
    banner("Message envoyé.");
    fetch("/accounts/" + payload.account_id + "/sync", { method: "POST", ...AUTH })
      .then(loadMessages).catch(() => {});
  } catch (e) { status.textContent = "Échec de l'envoi : " + e.message; }
  el("#c-send").disabled = false;
}

function replyTo(m) {
  openComposer({
    title: "Répondre", accountId: m.account_id, to: emailOnly(m.addr_from),
    subject: /^re\s*:/i.test(m.subject || "") ? m.subject : "Re: " + (m.subject || ""),
    inReplyTo: m.rfc822_message_id || "", threadId: m.thread_id || "",
    body: "\n\n----- Message d'origine -----\n" + (m.body_text || ""),
  });
}

function forward(m) {
  openComposer({
    title: "Transférer", accountId: m.account_id,
    subject: /^tr\s*:/i.test(m.subject || "") ? m.subject : "Tr: " + (m.subject || ""),
    body: "\n\n----- Message transféré -----\nDe : " + (m.addr_from || "") +
      "\nObjet : " + (m.subject || "") + "\n\n" + (m.body_text || ""),
  });
}

/* ------------------------- Recherche ------------------------- */

function initSearch() {
  let t;
  el("#search").addEventListener("input", (e) => {
    clearTimeout(t);
    state.query = e.target.value.trim();
    renderCats();
    t = setTimeout(loadMessages, 250);
  });
}

/* ------------------------- Synchro ------------------------- */

async function syncAll() {
  const btn = el("#sync");
  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = "⟳ Synchro…";
  try {
    const accs = await api("/accounts");
    for (const a of accs) {
      await fetch("/accounts/" + a.id + "/sync", { method: "POST", ...AUTH });
      await loadAccounts();
      await loadMessages();
    }
  } catch (e) { banner("Erreur de synchro : " + e.message); }
  btn.disabled = false;
  btn.textContent = label;
}

/* ------------------------- Init ------------------------- */

async function main() {
  document.documentElement.dataset.theme = localStorage.getItem("maily_theme") || "aero";
  el("#themebtn").onclick = () => {
    const next = document.documentElement.dataset.theme === "dedsec" ? "aero" : "dedsec";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("maily_theme", next);
  };
  el("#sync").onclick = syncAll;
  el("#markread").onclick = markAllRead;
  el("#compose").onclick = () => openComposer({ accountId: state.accountId || undefined });
  el("#c-close").onclick = closeComposer;
  el("#c-cancel").onclick = closeComposer;
  el("#c-send").onclick = sendComposer;
  el("#c-attach").onclick = () => el("#c-file").click();
  el("#c-file").onchange = (e) => addComposerFiles(e.target.files);
  el("#composer").addEventListener("click", (e) => { if (e.target.id === "composer") closeComposer(); });
  initSearch();
  updateLayout();
  renderCats();
  try {
    await loadAccounts();
    await loadMessages();
  } catch (e) {
    banner("Impossible de contacter l'API locale : " + e.message);
  }
}

main();
