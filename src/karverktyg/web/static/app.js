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

const $ = (sel) => document.querySelector(sel);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else n.setAttribute(k, v);
  }
  for (const kid of kids) n.append(kid);
  return n;
};
const esc = (s) => (s == null ? "" : String(s));

async function api(path) {
  const r = await fetch("/api/" + path);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || "HTTP " + r.status);
  return body;
}

async function apiSend(method, path, body) {
  const r = await fetch("/api/" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.error || "HTTP " + r.status);
  }
  return r.json().catch(() => ({}));
}

function refresh() {
  show((location.hash || "#overview").slice(1));
}

async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = "Kopierat!";
  } catch {
    btn.textContent = "Kunde inte kopiera";
  }
  setTimeout(() => (btn.textContent = "Kopiera"), 1500);
}

function table(headers, rows) {
  const t = el("table");
  t.append(el("thead", {}, el("tr", {}, ...headers.map((h) => el("th", {}, esc(h))))));
  const tb = el("tbody");
  for (const row of rows) {
    tb.append(
      el("tr", {}, ...row.map((c) => (c instanceof Node ? el("td", {}, c) : el("td", { html: esc(c) })))),
    );
  }
  t.append(tb);
  return el("div", { class: "table-wrap" }, t);
}

function stat(n, label) {
  return el("div", { class: "stat" }, el("div", { class: "n" }, esc(n)), el("div", { class: "l" }, esc(label)));
}

async function renderOverview(root) {
  const d = await api("overview");
  root.append(
    el(
      "div",
      { class: "grid" },
      stat(d.member_count, "Aktiva medlemmar"),
      stat(d.avdelning_count, "Avdelningar"),
      stat(d.current_term || "–", "Innevarande termin"),
      stat(d.prev_term || "–", "Föregående termin"),
    ),
  );
  root.append(el("p", { class: "muted" }, d.note_current_term || ""));
}

async function renderDues(root) {
  const d = await api("dues");
  root.append(el("p", { class: "muted" }, "Betalstatus för " + esc(d.term) + " (innevarande termin är ännu inte fakturerad)."));
  for (const a of d.avdelningar) {
    const counts = Object.entries(a.counts).map(([k, v]) => `${k}: ${v}`).join(" · ");
    const card = el("div", { class: "card" }, el("strong", {}, esc(a.avdelning)), el("div", { class: "muted" }, counts));
    if (a.outstanding.length) {
      card.append(table(["Medlemsnr", "Namn", "Status"], a.outstanding.map((m) => [m.member_no, m.name, m.status || m.bucket])));
    }
    root.append(card);
  }
}

// Väntelista: a compact table of all applicants; expand a row for the draft + actions.
async function renderWaiting(root) {
  const [w, dw, da] = await Promise.all([
    api("waiting"),
    api("membership/drafts?variant=waiting"),
    api("membership/drafts?variant=awaiting_approval"),
  ]);
  const drafts = {};
  for (const d of [...dw.drafts, ...da.drafts]) drafts[d.member_no] = d;
  const applicants = [
    ...w.waiting.map((a) => ({ ...a, list: "Väntelista" })),
    ...w.awaiting_approval.map((a) => ({ ...a, list: "Väntar godkännande" })),
  ];
  root.append(el("p", { class: "muted" }, "Klicka på en rad för att expandera och se e-postutkastet. Inget skickas av verktyget."));
  if (!applicants.length) {
    root.append(el("p", { class: "muted" }, "Inga ansökningar (kräver waiting/awaiting-capture i read_only-läge)."));
    return;
  }
  const t = el("table");
  t.append(el("thead", {}, el("tr", {}, ...["", "Medlemsnr", "Namn", "Avdelning", "Lista"].map((h) => el("th", {}, h)))));
  const tb = el("tbody");
  for (const a of applicants) {
    const caret = el("td", {}, "▸");
    const row = el("tr", { class: "expandable" }, caret, el("td", { html: esc(a.member_no) }), el("td", { html: esc(a.name) }), el("td", { html: esc(a.unit || "–") }), el("td", { html: esc(a.list) }));
    const cell = el("td", { colspan: "5" });
    const detail = el("tr", {}, cell);
    detail.style.display = "none";
    const draft = drafts[a.member_no];
    if (draft) {
      const to = draft.to.join(", ") || "(ingen adress – kan inte skickas)";
      const full = "Till: " + to + "\nÄmne: " + draft.subject + "\n\n" + draft.body;
      const copyBtn = el("button", { class: "action" }, "Kopiera");
      copyBtn.onclick = () => copyText(full, copyBtn);
      cell.append(
        el("div", {}, el("span", { class: "tag" }, draft.kind === "ledare" ? "Ledare" : "Scout"), draft.unsendable ? el("span", { class: "err" }, " · ingen adress") : ""),
        el("div", { class: "muted" }, "Till: " + to),
        el("div", { class: "muted" }, "Ämne: " + esc(draft.subject)),
        el("pre", { html: esc(draft.body) }),
        copyBtn,
      );
    } else {
      cell.append(el("p", { class: "muted" }, "Inget utkast."));
    }
    row.onclick = () => {
      const open = detail.style.display === "none";
      detail.style.display = open ? "" : "none";
      caret.textContent = open ? "▾" : "▸";
    };
    tb.append(row, detail);
  }
  t.append(tb);
  root.append(el("div", { class: "table-wrap" }, t));
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
        await apiSend("PUT", "templates/" + t.key, { subject: subj.value, body: body.value, by: "webb" });
        status.textContent = " sparad";
      } catch (e) {
        status.textContent = " fel: " + e.message;
      }
    };
    root.append(
      el("div", { class: "card" }, el("strong", {}, t.key), status, el("div", { class: "muted" }, t.description || ""), el("label", {}, "Ämne"), subj, el("label", {}, "Text"), body, el("div", { style: "margin-top:.5rem;" }, save)),
    );
  }
}

async function renderUppflyttning(root) {
  let d;
  try {
    d = await api("uppflyttning");
  } catch (e) {
    root.append(el("p", { class: "err" }, "Kan inte beräkna: " + e.message));
    return;
  }
  root.append(el("p", {}, "Uppflyttningsår N = ", el("strong", {}, esc(d.cohort_year)), ". ", el("a", { href: "/api/uppflyttning/changelist.xlsx" }, "Exportera changelist (Excel)")));
  root.append(
    el(
      "div",
      { class: "grid" },
      stat(d.ready.length, "Klara"),
      stat(d.pending.length, "Väntar på måldelning"),
      stat(d.off_cohort.length, "Utanför årskull"),
      stat(d.excluded.length, "Undantagna"),
    ),
  );

  // Cohort-level Äventyrare → Utmanare target election (§17).
  const electCard = el("div", { class: "card" }, el("strong", {}, "Måldelning för Äventyrare → Utmanare"));
  const sel = el("select", {});
  sel.append(el("option", { value: "" }, "– välj Utmanare-avdelning –"));
  for (const c of d.utmanare_candidates) {
    const o = el("option", { value: c.avdelning }, `${c.avdelning} (troop ${c.troop_id})`);
    if (d.elected_target && d.elected_target.avdelning === c.avdelning) o.setAttribute("selected", "selected");
    sel.append(o);
  }
  const electBtn = el("button", { class: "action" }, "Välj måldelning");
  electBtn.onclick = async () => {
    if (!sel.value) return;
    try {
      await apiSend("POST", "uppflyttning/target", { avdelning: sel.value, by: "webb" });
      refresh();
    } catch (e) {
      alert(e.message);
    }
  };
  electCard.append(
    el("div", { class: "muted" }, d.elected_target ? "Vald: " + d.elected_target.avdelning : "Ingen måldelning vald – Äventyrare-flyttar väntar."),
    el("div", { style: "margin-top:.4rem;" }, sel, " ", electBtn),
  );
  if (d.elected_target) {
    const clr = el("button", {}, "Rensa val");
    clr.onclick = async () => {
      await apiSend("DELETE", "uppflyttning/target");
      refresh();
    };
    electCard.append(el("div", { style: "margin-top:.4rem;" }, clr));
  }
  root.append(electCard);

  // Per-scout row: choose target, acknowledge/handle, or reset to the computed default.
  const moveRow = (m) => {
    const targetSel = el("select", {});
    targetSel.append(el("option", { value: "" }, m.target ? "Behåll: " + m.target : "– välj måldelning –"));
    for (const c of d.avdelningar) {
      const o = el("option", { value: c.avdelning }, c.avdelning);
      targetSel.append(o);
    }
    targetSel.onchange = async () => {
      try {
        await apiSend("POST", "uppflyttning/decision", { member_no: m.member_no, target_avdelning: targetSel.value, by: "webb" });
        refresh();
      } catch (e) {
        alert(e.message);
      }
    };
    const ack = el("input", { type: "checkbox" });
    if (m.acknowledged) ack.setAttribute("checked", "checked");
    ack.onchange = async () => {
      await apiSend("POST", "uppflyttning/decision", { member_no: m.member_no, acknowledged: ack.checked, by: "webb" });
      refresh();
    };
    const clr = el("a", { href: "#" }, "återställ");
    clr.onclick = async (ev) => {
      ev.preventDefault();
      await apiSend("DELETE", "uppflyttning/decision?member_no=" + encodeURIComponent(m.member_no));
      refresh();
    };
    const statusTxt = m.status + (m.override ? " ✎" : "");
    return [m.member_no, m.name, m.source || "–", targetSel, el("span", { class: "status-" + m.status }, statusTxt), ack, clr];
  };
  for (const [title, list] of [
    ["Klara", d.ready],
    ["Väntar på måldelning", d.pending],
    ["Utanför årskull", d.off_cohort],
    ["Undantagna (ledare/vuxna)", d.excluded],
  ]) {
    if (!list.length) continue;
    root.append(
      el("div", { class: "card" }, el("strong", {}, title + " (" + list.length + ")"), table(["Medlemsnr", "Namn", "Från", "Till (välj)", "Status", "Klar", ""], list.map(moveRow))),
    );
  }
}

async function renderFindings(root) {
  const d = await api("findings");
  if (!d.findings.length) {
    root.append(el("p", { class: "muted" }, "Inga anmärkningar."));
    return;
  }
  root.append(
    table(
      ["Allvar", "Typ", "Medlemsnr", "Namn", "Avdelning", "Detalj"],
      d.findings.map((f) => [el("span", { class: "tag sev-" + f.severity }, f.severity), f.type, f.member_no, f.name, f.avdelning || "–", f.detail]),
    ),
  );
}

async function renderCapabilities(root) {
  const d = await api("capabilities");
  root.append(
    el(
      "div",
      { class: "card" },
      el("div", {}, "Kår: " + esc(d.kar)),
      el("div", {}, "Läge: " + esc(d.mode)),
      el("div", {}, "Version: " + esc(d.app_version) + " (" + esc(d.build_number) + ")"),
      el("div", {}, "Swedish ICU-collation: " + (d.icu_collation ? "ja" : "nej (fallback)")),
      el("div", {}, "Konfiguration: " + (d.config_placeholder ? "platshållare" : "anpassad")),
    ),
  );
  root.append(el("div", { class: "card" }, el("strong", {}, "Endpoints"), table(["Endpoint", "Nyckel", "Fingeravtryck"], d.endpoints.map((e) => [e.endpoint, e.configured ? "konfigurerad" : "saknas", e.key_hash || "–"]))));
  root.append(el("div", { class: "card" }, el("strong", {}, "Åtgärder"), table(["Åtgärd", "Aktiverad", "Förklaring"], d.actions.map((a) => [a.action, a.enabled ? "ja" : "nej", a.reason || ""]))));
  const om = d.openapi;
  root.append(el("div", { class: "card" }, el("strong", {}, "OpenAPI"), el("div", { class: "muted" }, om ? `version ${om.version} · ${om.git_commit || ""} · ${om.retrieved || ""}` : "ej vendorerad ännu")));
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
    const b = el("button", {}, label);
    b.dataset.k = key;
    b.onclick = () => show(key);
    nav.append(b);
  }
  try {
    const cap = await api("capabilities");
    $("#kar-name").textContent = cap.kar + " – Kårverktyg";
    document.title = cap.kar + " – Kårverktyg";
    if (cap.read_write_active) $("#rw-banner").hidden = false;
    $("#footer").textContent = `${cap.kar} · v${cap.app_version} · läge ${cap.mode}`;
  } catch {
    /* capabilities optional for boot */
  }
  show((location.hash || "#overview").slice(1));
}

boot();
