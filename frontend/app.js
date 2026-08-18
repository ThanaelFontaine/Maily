"use strict";

const TOKEN = window.MAILY_TOKEN || "";
const AUTH = { headers: { Authorization: "Bearer " + TOKEN } };
const PALETTE = ["#2e5fff", "#18c07a", "#f5a524", "#c159f5", "#ef476f", "#0e91d8"];
const TZ = "Europe/Paris";

/* Icônes SVG épurées (style trait, currentColor) - cohérentes avec la DA verre. */
const ICONS = {
  theme: '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  send: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
  paperclip: '<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  reply: '<polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>',
  forward: '<polyline points="15 14 20 9 15 4"/><path d="M4 20v-7a4 4 0 0 1 4-4h12"/>',
  archive: '<polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  restore: '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
  inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  tag: '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  bell: '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
};
function ico(name) {
  return `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

const CATEGORIES = [
  { key: "primary", label: "Principale", icon: "inbox" },
  { key: "promotions", label: "Promotions", icon: "tag" },
  { key: "social", label: "Réseaux sociaux", icon: "users" },
  { key: "updates", label: "Notifications", icon: "bell" },
];

const state = {
  accountId: null, currentId: null, query: "", tabs: [],
  folder: { type: "inbox" }, category: "primary", accounts: [], currentMsgs: [],
  composerAtts: [], pendingReads: [], composerKey: null, openSeq: 0, listSeq: 0,
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

function esc(s) {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

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

function orb(color, id) {
  return `<span class="orb"${id != null ? ` data-acc="${id}"` : ""} style="background:linear-gradient(180deg, ${color}cc, ${color})"></span>`;
}

/* ------- Couleurs de compte : palette thème-aware + choix persistant ------- */
const THEME_PALETTES = {
  aero:   ["#2e5fff", "#0e91d8", "#18c07a", "#14b8a6", "#f5a524", "#ef476f", "#c159f5", "#8b5cf6"],
  glass:  ["#4f7cff", "#38bdf8", "#34d399", "#2dd4bf", "#fbbf24", "#fb7185", "#c084fc", "#a78bfa"],
  dedsec: ["#FF2D78", "#22E6DC", "#4AF626", "#F5A524", "#8b7cff", "#ef476f", "#00E5FF", "#39FF14"],
};
function paletteForTheme() {
  return THEME_PALETTES[document.documentElement.dataset.theme] || THEME_PALETTES.aero;
}

// Met a jour un profil (nom et/ou couleur) en base, puis recolore/renomme en place.
async function updateAccount(id, patch) {
  let acc;
  try {
    const r = await fetch(`/accounts/${id}`, {
      method: "PATCH",
      headers: { Authorization: "Bearer " + TOKEN, "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!r.ok) throw new Error();
    acc = await r.json();
  } catch { banner("Mise à jour du profil impossible."); return null; }
  const a = state.accounts.find((x) => x.id === id);
  if (a) Object.assign(a, acc);
  if (patch.color) {
    accountColors[id] = patch.color;
    document.querySelectorAll(`.orb[data-acc="${id}"]`).forEach((o) => {
      o.style.background = `linear-gradient(180deg, ${patch.color}cc, ${patch.color})`;
    });
    document.querySelectorAll(`.li[data-acc="${id}"] .li-dot`).forEach((d) => {
      d.style.setProperty("--dot", patch.color);
    });
  }
  if (patch.display_name !== undefined) {
    document.querySelectorAll(`.orb[data-acc="${id}"]`).forEach((o) => {
      const lbl = o.parentElement && o.parentElement.querySelector(".nav-lbl");
      if (lbl) lbl.textContent = acc.display_name || acc.email;
    });
  }
  return acc;
}

function closeColorPicker() {
  const p = document.getElementById("colorpop");
  if (p) { if (p._onDoc) document.removeEventListener("click", p._onDoc, true); p.remove(); }
}
function openColorPicker(accountId, anchor) {
  closeColorPicker();
  const pop = document.createElement("div");
  pop.id = "colorpop";
  pop.className = "colorpop";
  const cur = (accountColors[accountId] || "").toLowerCase();
  pop.innerHTML = paletteForTheme().map((c) =>
    `<button class="swatch${c.toLowerCase() === cur ? " on" : ""}" style="background:${c}" data-c="${c}" title="${c}"></button>`
  ).join("");
  document.body.appendChild(pop);
  const r = anchor.getBoundingClientRect();
  pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - pop.offsetWidth - 8)) + "px";
  pop.style.top = (r.bottom + 6) + "px";
  pop.querySelectorAll(".swatch").forEach((b) => {
    b.onclick = () => { updateAccount(accountId, { color: b.dataset.c }); closeColorPicker(); };
  });
  const onDoc = (e) => { if (!e.target.closest("#colorpop")) closeColorPicker(); };
  pop._onDoc = onDoc;
  setTimeout(() => document.addEventListener("click", onDoc, true), 0);
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
  all.innerHTML = `<span class="nav-ico">${ico("inbox")}</span> Tout (unifié)`;
  all.onclick = () => selectAccount(null);
  rail.appendChild(all);

  accs.forEach((a) => {
    const n = document.createElement("div");
    n.className = "nav" + (state.accountId === a.id ? " on" : "");
    const label = a.display_name || a.email;
    n.innerHTML = `${orb(accountColors[a.id], a.id)}<span class="nav-lbl">${esc(label)}</span>`;
    n.title = a.email;
    n.onclick = () => selectAccount(a.id);
    n.querySelector(".orb").onclick = (e) => { e.stopPropagation(); openColorPicker(a.id, e.currentTarget); };
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
    { name: "Boîte de réception", icon: "inbox", folder: { type: "inbox" } },
    { name: "Archivés", icon: "archive", folder: { type: "archived" } },
    { name: "Corbeille", icon: "trash", folder: { type: "trash" } },
  ];
  special.forEach((s) => rail.appendChild(folderNav(s.icon, s.name, s.folder)));

  const userLabels = labels.filter((l) => l.type === "user" && l.name);
  if (userLabels.length) {
    const sep2 = document.createElement("div");
    sep2.className = "rail-sep";
    sep2.textContent = "Libellés";
    rail.appendChild(sep2);
    userLabels.forEach((l) =>
      rail.appendChild(folderNav("tag", l.name, { type: "label", id: l.gmail_label_id, name: l.name })));
  }
}

function folderNav(icon, name, folder) {
  const n = document.createElement("div");
  const active = JSON.stringify(state.folder) === JSON.stringify(folder);
  n.className = "nav nav-folder" + (active ? " on" : "");
  n.innerHTML = `<span class="nav-ico">${ico(icon)}</span><span class="nav-lbl">${esc(name)}</span>`;
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
    t.innerHTML = `${ico(c.icon)} ${c.label}`;
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
  const seq = ++state.listSeq;
  el("#listbar-title").textContent = listTitle();
  let msgs;
  try { msgs = await api(messagesQuery()); }
  catch (e) { banner("Erreur de chargement : " + e.message); return; }
  if (seq !== state.listSeq) return;  // une requete plus recente a pris le relais
  state.currentMsgs = msgs;

  list.innerHTML = "";
  if (!msgs.length) {
    list.innerHTML = `<div class="list-empty">Aucun message ici. Clique sur « Synchroniser » si besoin.</div>`;
    return;
  }
  msgs.forEach((m) => {
    const row = document.createElement("div");
    row.className = "li" + (m.id === state.currentId ? " on" : "");
    row.dataset.id = m.id;
    if (m.account_id != null) row.dataset.acc = m.account_id;
    const dotColor = accountColors[m.account_id];
    row.innerHTML =
      `<div class="li-top">
         <span class="li-dot ${m.is_unread ? "" : "seen"}"${dotColor ? ` style="--dot:${dotColor}"` : ""}></span>
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
  let ok = 0;
  try {
    for (const m of unread) {
      await postAction(`/messages/${m.id}/modify`, { remove_labels: ["UNREAD"] });
      ok++;
    }
    banner(`${ok} message(s) marqué(s) comme lu(s).`);
  } catch (e) {
    banner(`Erreur après ${ok} marqué(s) : ` + e.message);
  } finally {
    await loadMessages();
    btn.disabled = false;
  }
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
  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(20,50,63,.28); border-radius: 999px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(20,50,63,.5); }
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
    `<button class="att-chip" data-att="${a.id}">${ico("paperclip")} ${esc(a.filename) || "fichier"}` +
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
  const wasCurrent = state.currentId === id;
  state.tabs = state.tabs.filter((t) => t.id !== id);
  if (state.tabs.length === 0) { closeReading(); return; }
  if (state.tabs.length === 1) {
    const only = state.tabs[0].id;
    state.tabs = [];  // 1 seul mail restant = pas de barre d'onglets
    openMessage(wasCurrent ? only : state.currentId);
    return;
  }
  openMessage(wasCurrent ? state.tabs[state.tabs.length - 1].id : state.currentId);
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

function closeReading() {
  state.currentId = null;
  state.tabs = [];
  el("#read").innerHTML = `<div class="read-empty">Sélectionne un message pour le lire.</div>`;
  updateLayout();
  loadMessages();
}

async function openMessage(id) {
  const seq = ++state.openSeq;
  state.currentId = id;
  updateLayout();
  // MAJ optimiste : la pastille non-lu disparait immediatement au clic
  const listRow = document.querySelector(`.li[data-id="${id}"]`);
  if (listRow) {
    listRow.querySelector(".li-dot")?.classList.add("seen");
    document.querySelectorAll(".li.on").forEach((r) => r.classList.remove("on"));
    listRow.classList.add("on");
  }
  let m;
  try { m = await api("/messages/" + id); }
  catch (e) { banner("Erreur : " + e.message); return; }
  if (seq !== state.openSeq) return;  // un autre mail a ete ouvert entre-temps

  const read = el("#read");
  read.innerHTML = "";
  if (state.tabs.length >= 2) read.appendChild(renderTabBar());

  const head = document.createElement("div");
  head.className = "read-head";
  const inTrash = state.folder.type === "trash";
  head.innerHTML =
    `<button class="read-close" id="read-close" title="Fermer">${ico("x")}</button>
     <h1 class="read-subj">${esc(m.subject) || "(sans sujet)"}</h1>
     <div class="read-meta">${esc(m.addr_from)} · ${fmtDate(m.internal_date)}</div>
     <div class="read-actions">
       <button class="gel" id="replybtn">${ico("reply")} Répondre</button>
       <button class="ghost" id="fwdbtn">${ico("forward")} Transférer</button>
       ${inTrash
        ? `<button class="ghost" id="untrashbtn">${ico("restore")} Restaurer</button>`
        : `<button class="ghost" id="archbtn">${ico("archive")} Archiver</button>
           <button class="ghost" id="trashbtn">${ico("trash")} Corbeille</button>`}
     </div>`;
  read.appendChild(head);

  head.querySelector("#read-close").onclick = closeReading;
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
    if (seq !== state.openSeq) return;
    const body = (html && html.trim()) ? html : `<pre>${esc(m.body_text) || "(vide)"}</pre>`;
    frame.srcdoc = buildDoc(body);
  } catch (e) { banner("Erreur : " + e.message); }

  if (m.is_unread) {
    postAction(`/messages/${id}/modify`, { remove_labels: ["UNREAD"] })
      .then(loadMessages)
      .catch(() => { banner("Impossible de marquer comme lu."); loadMessages(); });
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
  state.pendingReads = [];
  state.composerKey = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
    : "k" + Date.now() + Math.random().toString(16).slice(2);
  renderComposerAtts();
  c.hidden = false;
  el("#c-to").focus();
}

function closeComposer() { el("#composer").hidden = true; }

function renderComposerAtts() {
  const wrap = el("#c-atts");
  const atts = state.composerAtts || [];
  wrap.innerHTML = atts.map((a, i) =>
    `<span class="c-att">${ico("paperclip")} ${esc(a.filename)}<span class="c-att-x" data-i="${i}">×</span></span>`).join("");
  wrap.querySelectorAll(".c-att-x").forEach((x) => {
    x.onclick = () => { state.composerAtts.splice(Number(x.dataset.i), 1); renderComposerAtts(); };
  });
}

function addComposerFiles(fileList) {
  [...fileList].forEach((f) => {
    const p = new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => {
        const data = String(reader.result).split(",")[1] || "";
        state.composerAtts.push({ filename: f.name, mime_type: f.type || "application/octet-stream", data });
        renderComposerAtts();
        resolve();
      };
      reader.onerror = () => { banner("Lecture du fichier échouée : " + f.name); resolve(); };
      reader.readAsDataURL(f);
    });
    state.pendingReads.push(p);
  });
  el("#c-file").value = "";
}

async function sendComposer() {
  const status = el("#c-status");
  const to = el("#c-to").value.trim();
  if (!to) { status.textContent = "Ajoute au moins un destinataire."; return; }
  el("#c-send").disabled = true;
  status.textContent = "Préparation…";
  await Promise.allSettled(state.pendingReads);  // attendre que les PJ soient lues
  const payload = {
    account_id: Number(el("#c-from").value),
    to, cc: el("#c-cc").value.trim() || null,
    subject: el("#c-subject").value,
    body_text: el("#c-body").value,
    in_reply_to: el("#composer").dataset.inReplyTo || null,
    thread_id: el("#composer").dataset.threadId || null,
    attachments: state.composerAtts || [],
    idempotency_key: state.composerKey,
  };
  status.textContent = "Envoi…";
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
  const label = btn.innerHTML;
  btn.innerHTML = `${ico("refresh")} Synchro…`;
  try {
    const accs = await api("/accounts");
    for (const a of accs) {
      await fetch("/accounts/" + a.id + "/sync", { method: "POST", ...AUTH });
      await loadAccounts();
      await loadMessages();
    }
  } catch (e) { banner("Erreur de synchro : " + e.message); }
  btn.disabled = false;
  btn.innerHTML = label;
}

/* ------------------------- Init ------------------------- */

function setTheme(t) {
  document.documentElement.dataset.theme = t;
  localStorage.setItem("maily_theme", t);
  document.querySelectorAll(".theme-opt").forEach((b) => b.classList.toggle("on", b.dataset.themeVal === t));
}

function openThemeMenu() {
  const cur = document.documentElement.dataset.theme;
  document.querySelectorAll(".theme-opt").forEach((b) => b.classList.toggle("on", b.dataset.themeVal === cur));
  el("#thememodal").hidden = false;
}

function closeThemeMenu() { el("#thememodal").hidden = true; }

/* ------- Page réglages : nom + couleur par profil ------- */
function renderSettings() {
  const wrap = el("#settings-accounts");
  const pal = paletteForTheme();
  wrap.innerHTML = state.accounts.map((a) => {
    const cur = (accountColors[a.id] || "").toLowerCase();
    const sw = pal.map((c) =>
      `<button class="swatch${c.toLowerCase() === cur ? " on" : ""}" style="background:${c}" data-c="${c}" data-acc="${a.id}" title="${c}"></button>`
    ).join("");
    return `<div class="settings-row">
      <div class="settings-row-top">
        ${orb(accountColors[a.id], a.id)}
        <input class="settings-name" data-acc="${a.id}" value="${esc(a.display_name || "")}" placeholder="${esc(a.email)}" maxlength="60">
      </div>
      <div class="settings-email">${esc(a.email)}</div>
      <div class="settings-swatches">${sw}</div>
    </div>`;
  }).join("");
  wrap.querySelectorAll(".settings-name").forEach((inp) => {
    inp.onchange = () => updateAccount(parseInt(inp.dataset.acc, 10), { display_name: inp.value.trim() });
  });
  wrap.querySelectorAll(".settings-swatches .swatch").forEach((b) => {
    b.onclick = async () => {
      await updateAccount(parseInt(b.dataset.acc, 10), { color: b.dataset.c });
      renderSettings();
    };
  });
}
function openSettings() {
  if (!state.accounts.length) { banner("Aucun compte à régler."); return; }
  renderSettings();
  el("#settingsmodal").hidden = false;
}
function closeSettings() { el("#settingsmodal").hidden = true; }

/* ------- Densité du fond (thème Verre) : slider -> vibrancy native ------- */
const GLASS_ALPHA_KEY = "maily_glass_alpha";

function applyGlassAlpha(a) {
  fetch("/glass", {
    method: "POST",
    headers: { Authorization: "Bearer " + TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ alpha: a }),
  }).catch(() => { /* pas de vibrancy (non-macOS) : sans effet */ });
}

function initGlassSlider() {
  const s = el("#glass-alpha");
  const val = el("#glass-alpha-val");
  if (!s) return;
  const saved = parseFloat(localStorage.getItem(GLASS_ALPHA_KEY));
  const a0 = isNaN(saved) ? 0.6 : Math.max(0, Math.min(1, saved));
  s.value = Math.round(a0 * 100);
  if (val) val.textContent = s.value + "%";
  applyGlassAlpha(a0);
  s.addEventListener("input", () => {
    if (val) val.textContent = s.value + "%";
    applyGlassAlpha(s.value / 100);                       // aperçu en direct
  });
  s.addEventListener("change", () => {
    localStorage.setItem(GLASS_ALPHA_KEY, (s.value / 100).toString());  // sauvegarde au relâchement
  });
}

function paintStaticIcons() {
  const map = {
    "#settingsbtn": ["settings", "Réglages"], "#themebtn": ["theme", "Thème"], "#compose": ["edit", "Écrire"],
    "#sync": ["refresh", "Synchroniser"], "#markread": ["check", "Tout marquer lu"],
    "#c-send": ["send", "Envoyer"], "#c-attach": ["paperclip", "Joindre"],
  };
  for (const [sel, [name, label]] of Object.entries(map)) {
    const b = el(sel); if (b) b.innerHTML = `${ico(name)} ${label}`;
  }
  ["#c-close", "#theme-close", "#settings-close"].forEach((sel) => { const b = el(sel); if (b) b.innerHTML = ico("x"); });
}

async function main() {
  setTheme(localStorage.getItem("maily_theme") || "glass");
  paintStaticIcons();
  el("#themebtn").onclick = openThemeMenu;
  el("#theme-close").onclick = closeThemeMenu;
  el("#thememodal").addEventListener("click", (e) => { if (e.target.id === "thememodal") closeThemeMenu(); });
  document.querySelectorAll(".theme-opt").forEach((b) => {
    b.onclick = () => { setTheme(b.dataset.themeVal); closeThemeMenu(); };
  });
  el("#settingsbtn").onclick = openSettings;
  el("#settings-close").onclick = closeSettings;
  el("#settingsmodal").addEventListener("click", (e) => { if (e.target.id === "settingsmodal") closeSettings(); });
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
  initGlassSlider();
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
