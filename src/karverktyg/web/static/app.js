"use strict";
// Read-only frontend (§3). Talks only to this API. Swedish UI strings inline.

const TABS = [
  ["overview", "Översikt", renderOverview],
  ["dues", "Medlemsavgifter", renderDues],
  ["waiting", "Väntelista", renderWaiting],
  ["uppflyttning", "Uppflyttning", renderUppflyttning],
  ["findings", "Anmärkningar", renderFindings],
  ["templates", "Mallar", renderTemplates],
  ["capabilities", "Funktioner", renderCapabilities],
];

async function copyText(text, btn) {
  try { await navigator.clipboard.writeText(text); btn.textContent = "Kopierat!"; }
  catch { btn.textContent = "Kunde inte kopiera"; }
  setTimeout(() => (btn.textContent = "Kopiera"), 1500);
}

const $ = (sel) => document.querySelector(sel);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v; else if (k === "html") n.innerHTML = v; else n.setAttribute(k, v);
  }
  for (const kid of kids) n.append(kid);
  return n;
};
const esc = (s) => (s == null ? "" : String(s));

async function api(path) {
  const r = await fetch("/api/" + path);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || ("HTTP " + r.status));
  return body;
}

function table(headers, rows) {
  const t = el("table");
  t.append(el("thead", {}, el("tr", {}, ...headers.map((h) => el("th", {}, esc(h))))));
  const tb = el("tbody");
  for (const row of rows) {
    tb.append(el("tr", {}, ...row.map((c) => (c instanceof Node ? el("td", {}, c) : el("td", { html: esc(c) })))));
  }
  t.append(tb);
  return el("div", { class: "table-wrap" }, t);
}

function stat(n, label) {
  return el("div", { class: "stat" }, el("div", { class: "n" }, esc(n)), el("div", { class: "l" }, esc(label)));
}

async function renderOverview(root) {
  const d = await api("overview");
  root.append(el("div", { class: "grid" },
    stat(d.member_count, "Aktiva medlemmar"),
    stat(d.avdelning_count, "Avdelningar"),
    stat(d.current_term || "–", "Innevarande termin"),
    stat(d.prev_term || "–", "Föregående termin")));
  root.append(el("p", { class: "muted" }, d.note_current_term || ""));
}

async function renderDues(root) {
  const d = await api("dues");
  root.append(el("p", { class: "muted" }, "Betalstatus för " + esc(d.term) + " (innevarande termin är ännu inte fakturerad)."));
  for (const a of d.avdelningar) {
    const counts = Object.entries(a.counts).map(([k, v]) => `${k}: ${v}`).join(" · ");
    const card = el("div", { class: "card" }, el("strong", {}, esc(a.avdelning)), el("div", { class: "muted" }, counts));
    if (a.outstanding.length) {
      card.append(table(["Medlemsnr", "Namn", "Status"],
        a.outstanding.map((m) => [m.member_no, m.name, m.status || m.bucket])));
    }
    root.append(card);
  }
}

async function renderWaiting(root) {
  const d = await api("waiting");
  const section = (title, list) => {
    const card = el("div", { class: "card" }, el("strong", {}, title + " (" + list.length + ")"));
    if (list.length) card.append(table(["Medlemsnr", "Namn", "Avdelning"], list.map((m) => [m.member_no, m.name, m.unit || "–"])));
    else card.append(el("p", { class: "muted" }, "Inga poster (kräver waiting/awaiting-capture i read_only-läge)."));
    return card;
  };
  root.append(section("Väntelista", d.waiting));
  root.append(section("Väntar på godkännande", d.awaiting_approval));

  const draftsCard = el("div", { class: "card" }, el("strong", {}, "E-postutkast (kopiera manuellt)"));
  draftsCard.append(el("p", { class: "muted" }, "Genereras från mallarna. Inget skickas av verktyget."));
  root.append(draftsCard);
  const dd = await api("membership/drafts?variant=waiting");
  if (!dd.drafts.length) draftsCard.append(el("p", { class: "muted" }, "Inga utkast."));
  for (const draft of dd.drafts) {
    const to = draft.to.join(", ") || "(ingen adress – kan inte skickas)";
    const full = "Till: " + to + "\nÄmne: " + draft.subject + "\n\n" + draft.body;
    const copyBtn = el("button", { class: "action" }, "Kopiera");
    copyBtn.onclick = () => copyText(full, copyBtn);
    const block = el("div", { class: "card" },
      el("div", {}, el("span", { class: "tag" }, draft.kind === "ledare" ? "Ledare" : "Scout"),
        " ", el("strong", {}, draft.member_no), draft.unsendable ? el("span", { class: "err" }, " · ingen adress") : ""),
      el("div", { class: "muted" }, "Till: " + to),
      el("div", { class: "muted" }, "Ämne: " + draft.subject),
      el("pre", { html: esc(draft.body) }),
      copyBtn);
    draftsCard.append(block);
  }
}

async function renderTemplates(root) {
  const d = await api("templates");
  root.append(el("p", { class: "muted" }, "Mallar lagras i databasen och kan redigeras. Variabler: {{ first_name }}, {{ kar }}, {{ birth_year }}, {{ pronoun }}, {{ bracket_label }}, {{ avdelningar_sentence }}."));
  for (const t of d.templates) {
    const subj = el("input", { type: "text", value: t.subject, style: "width:100%;margin:.3rem 0;" });
    const body = el("textarea", { rows: "12", style: "width:100%;font-family:ui-monospace,monospace;" });
    body.value = t.body;
    const save = el("button", { class: "action" }, "Spara");
    const status = el("span", { class: "muted" }, t.edited ? " (redigerad)" : " (standard)");
    save.onclick = async () => {
      try {
        const r = await fetch("/api/templates/" + t.key, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ subject: subj.value, body: body.value, by: "webb" }),
        });
        status.textContent = r.ok ? " sparad" : " fel vid sparande";
      } catch (e) { status.textContent = " fel: " + e.message; }
    };
    root.append(el("div", { class: "card" },
      el("strong", {}, t.key), status,
      el("div", { class: "muted" }, t.description || ""),
      el("label", {}, "Ämne"), subj,
      el("label", {}, "Text"), body,
      el("div", { style: "margin-top:.5rem;" }, save)));
  }
}

async function renderUppflyttning(root) {
  let d;
  try { d = await api("uppflyttning"); }
  catch (e) { root.append(el("p", { class: "err" }, "Kan inte beräkna: " + e.message)); return; }
  root.append(el("p", {}, "Uppflyttningsår N = ", el("strong", {}, esc(d.cohort_year)), ". ",
    el("a", { href: "/api/uppflyttning/changelist.xlsx" }, "Exportera changelist (Excel)")));
  root.append(el("div", { class: "grid" },
    stat(d.ready.length, "Klara flyttar"), stat(d.pending.length, "Väntar på måldelning"),
    stat(d.off_cohort.length, "Utanför årskull"), stat(d.excluded.length, "Undantagna (ledare/vuxna)")));
  const move = (m) => [m.member_no, m.name, m.source, m.target || "–",
    el("span", { class: "status-" + m.status }, m.status), m.note || ""];
  for (const [title, list] of [["Klara", d.ready], ["Väntar", d.pending], ["Utanför årskull", d.off_cohort], ["Undantagna", d.excluded]]) {
    if (!list.length) continue;
    root.append(el("div", { class: "card" }, el("strong", {}, title + " (" + list.length + ")"),
      table(["Medlemsnr", "Namn", "Från", "Till", "Status", "Notering"], list.map(move))));
  }
}

async function renderFindings(root) {
  const d = await api("findings");
  if (!d.findings.length) { root.append(el("p", { class: "muted" }, "Inga anmärkningar.")); return; }
  root.append(table(["Allvar", "Typ", "Medlemsnr", "Namn", "Avdelning", "Detalj"],
    d.findings.map((f) => [
      el("span", { class: "tag sev-" + f.severity }, f.severity),
      f.type, f.member_no, f.name, f.avdelning || "–", f.detail,
    ])));
}

async function renderCapabilities(root) {
  const d = await api("capabilities");
  root.append(el("div", { class: "card" },
    el("div", {}, "Kår: " + esc(d.kar)),
    el("div", {}, "Läge: " + esc(d.mode)),
    el("div", {}, "Version: " + esc(d.app_version) + " (" + esc(d.build_number) + ")"),
    el("div", {}, "Swedish ICU-collation: " + (d.icu_collation ? "ja" : "nej (fallback)")),
    el("div", {}, "Konfiguration: " + (d.config_placeholder ? "platshållare" : "anpassad"))));
  root.append(el("div", { class: "card" }, el("strong", {}, "Endpoints"),
    table(["Endpoint", "Nyckel", "Fingeravtryck"],
      d.endpoints.map((e) => [e.endpoint, e.configured ? "konfigurerad" : "saknas", e.key_hash || "–"]))));
  root.append(el("div", { class: "card" }, el("strong", {}, "Åtgärder"),
    table(["Åtgärd", "Aktiverad", "Förklaring"],
      d.actions.map((a) => [a.action, a.enabled ? "ja" : "nej", a.reason || ""]))));
  const om = d.openapi;
  root.append(el("div", { class: "card" }, el("strong", {}, "OpenAPI"),
    el("div", { class: "muted" }, om ? `version ${om.version} · ${om.git_commit || ""} · ${om.retrieved || ""}` : "ej vendorerad ännu")));
}

async function show(key) {
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.k === key));
  const root = $("#content");
  root.replaceChildren(el("p", { class: "muted" }, "Laddar…"));
  const tab = TABS.find((t) => t[0] === key) || TABS[0];
  try {
    root.replaceChildren();
    await tab[2](root);
  } catch (e) {
    root.replaceChildren(el("p", { class: "err" }, "Fel: " + e.message));
  }
  location.hash = key;
}

async function boot() {
  const nav = $("#nav");
  for (const [key, label] of TABS) {
    const b = el("button", {}, label); b.dataset.k = key;
    b.onclick = () => show(key); nav.append(b);
  }
  try {
    const cap = await api("capabilities");
    $("#kar-name").textContent = cap.kar + " – Kårverktyg";
    document.title = cap.kar + " – Kårverktyg";
    if (cap.read_write_active) $("#rw-banner").hidden = false;
    $("#footer").textContent = `${cap.kar} · v${cap.app_version} · läge ${cap.mode}`;
  } catch (e) { /* capabilities optional for boot */ }
  show((location.hash || "#overview").slice(1));
}

boot();
