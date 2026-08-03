"use strict";
// Read-only frontend (§3). Talks only to this API. Swedish UI strings inline.

// [key, label, render, group]. The nav renders one row grouped under these
// section labels; Diagnostik holds the debug/programming views.
const NAV_GROUPS = ["Översikt", "Åtgärder", "Konfiguration", "Diagnostik"];
const TABS = [
  ["overview", "Översikt", renderOverview, "Översikt"],
  ["dues", "Medlemsavgifter", renderDues, "Översikt"],
  ["waiting", "Väntelista", renderWaiting, "Översikt"],
  ["findings", "Anmärkningar", renderFindings, "Översikt"],
  ["uppflyttning", "Uppflyttning", renderUppflyttning, "Åtgärder"],
  ["execute", "Utför uppflyttning", renderExecute, "Åtgärder"],
  ["templates", "Mallar", renderTemplates, "Konfiguration"],
  ["apicheck", "API-koll", renderApiCheck, "Diagnostik"],
  ["capabilities", "Funktioner", renderCapabilities, "Diagnostik"],
  ["verify", "Verifiera skrivning", renderVerify, "Diagnostik"],
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
  const orig = btn.textContent;
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = "Kopierat!";
  } catch {
    btn.textContent = "Kunde inte kopiera";
  }
  setTimeout(() => (btn.textContent = orig), 1500);
}

function copyButton(label, text) {
  const b = el("button", { class: "action", style: "margin: 0.2rem 0.4rem 0 0;" }, label);
  b.onclick = () => copyText(text, b);
  return b;
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

// Väntelista: each list loads independently so a slow/unavailable variant
// (e.g. Scoutnet stalling on awaiting_approval) never blocks the other.
async function renderWaiting(root) {
  root.append(el("p", { class: "muted" }, "Klicka på en rad för att expandera och se e-postutkastet. Inget skickas av verktyget."));
  for (const [title, variant] of [
    ["Väntelista", "waiting"],
    ["Väntar godkännande", "awaiting_approval"],
  ]) {
    const card = el("div", { class: "card" }, el("strong", {}, title), el("div", { class: "muted" }, "Laddar…"));
    root.append(card);
    loadWaitingSection(card, title, variant); // fire-and-forget; updates itself
  }
}

async function loadWaitingSection(card, title, variant) {
  const fail = (msg) => card.replaceChildren(el("strong", {}, title), el("div", { class: "err" }, msg));
  let d;
  try {
    d = await api("membership/drafts?variant=" + variant);
  } catch (e) {
    fail("Kunde inte hämtas: " + e.message);
    return;
  }
  if (d.unavailable) {
    fail("Kunde inte hämtas från Scoutnet (" + (d.reason || "tidsgräns") + ").");
    return;
  }
  const apps = d.applicants || [];
  if (!apps.length) {
    card.replaceChildren(el("strong", {}, title + " (0)"), el("div", { class: "muted" }, "Inga ansökningar."));
    return;
  }
  const t = el("table");
  t.append(el("thead", {}, el("tr", {}, ...["", "Medlemsnr", "Namn", "Avdelning"].map((h) => el("th", {}, h)))));
  const tb = el("tbody");
  for (const a of apps) {
    const caret = el("td", {}, "▸");
    const row = el("tr", { class: "expandable" }, caret, el("td", { html: esc(a.member_no) }), el("td", { html: esc(a.name) }), el("td", { html: esc(a.unit || "–") }));
    const cell = el("td", { colspan: "4" });
    const detail = el("tr", {}, cell);
    detail.style.display = "none";
    const recipients = (a.to || []).join(", ");
    const to = recipients || "(ingen adress – kan inte skickas)";
    const full = "Till: " + to + "\nÄmne: " + a.subject + "\n\n" + a.body;
    const buttons = el("div", {});
    if (recipients) buttons.append(copyButton("Kopiera mottagare", recipients));
    buttons.append(
      copyButton("Kopiera ämne", a.subject),
      copyButton("Kopiera text", a.body),
      copyButton("Kopiera allt", full),
    );
    cell.append(
      el("div", {}, el("span", { class: "tag" }, a.kind === "ledare" ? "Ledare" : "Scout"), a.unsendable ? el("span", { class: "err" }, " · ingen adress") : ""),
      el("div", { class: "muted" }, "Till: " + to),
      el("div", { class: "muted" }, "Ämne: " + esc(a.subject)),
      el("pre", { html: esc(a.body) }),
      buttons,
    );
    row.onclick = () => {
      const open = detail.style.display === "none";
      detail.style.display = open ? "" : "none";
      caret.textContent = open ? "▾" : "▸";
    };
    tb.append(row, detail);
  }
  t.append(tb);
  card.replaceChildren(el("strong", {}, title + " (" + apps.length + ")"), el("div", { class: "table-wrap" }, t));
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

const STATUS_SV = {
  ready: "Redo att förflyttas",
  pending_target: "Väntar på måldelning",
  off_cohort: "Utanför årskull",
  excluded: "Undantagen (ledare/vuxen)",
  override_stay: "Behålls kvar (val)",
};

const statusText = (e) => (STATUS_SV[e.status] || e.status) + (e.override ? " ✎" : "");

function flash(node) {
  node.style.transition = "background-color 0.15s";
  node.style.backgroundColor = "rgba(47, 125, 63, 0.18)";
  setTimeout(() => (node.style.backgroundColor = ""), 600);
}

async function renderUppflyttning(root) {
  let d;
  try {
    d = await api("uppflyttning");
  } catch (e) {
    root.append(el("p", { class: "err" }, "Kan inte beräkna: " + e.message));
    return;
  }

  // Always-visible reset for the whole uppflyttning, at the top of the blade.
  const changeParts = [];
  if (d.decisions_count > 0) changeParts.push(d.decisions_count + " individuella val");
  if (d.elected_target) changeParts.push("måldelning: " + d.elected_target.avdelning);
  const hasChanges = changeParts.length > 0;
  const resetBtn = el("button", { class: "danger" }, "Återställ hela uppflyttningen");
  resetBtn.disabled = !hasChanges;
  resetBtn.onclick = async () => {
    if (!confirm("Återställ hela uppflyttningen? Alla dina val (måldelningar, granskade, stannar) och den valda Utmanare-måldelningen tas bort.")) return;
    try {
      await apiSend("POST", "uppflyttning/reset");
      refresh();
    } catch (e) {
      alert(e.message);
    }
  };
  root.append(
    el(
      "div",
      { class: "card danger sticky-reset" },
      el("div", {}, el("strong", {}, "Återställ hela uppflyttningen"), " ", resetBtn),
      el(
        "div",
        { class: "muted" },
        hasChanges ? "Tillämpade ändringar: " + changeParts.join(", ") + "." : "Inga ändringar gjorda – beräknade standardvärden gäller.",
      ),
    ),
  );

  root.append(el("p", {}, "Uppflyttningsår N = ", el("strong", {}, esc(d.cohort_year)), ". ", el("a", { href: "/api/uppflyttning/changelist.xlsx" }, "Exportera changelist (Excel)")));
  root.append(
    el(
      "div",
      { class: "grid" },
      stat(d.ready.length, "Redo att förflyttas"),
      stat(d.pending.length, "Väntar på måldelning"),
      stat(d.kept.length, "Behålls kvar"),
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

  // Per-scout row. Every control persists async and updates ONLY its own row
  // from the server's reply — no full re-render.
  const moveRow = (m) => {
    const statusSpan = el("span", { class: "status-" + m.status }, statusText(m));
    const targetSel = el("select", {});
    targetSel.append(el("option", { value: "" }, "– ingen måldelning –"));
    for (const c of d.avdelningar) {
      const label = c.avdelning + (c.avdelning === m.default_target ? " ★" : "");
      targetSel.append(el("option", { value: c.avdelning }, label));
    }
    const keep = el("input", {
      type: "checkbox",
      title: "Behåll scouten i nuvarande avdelning – undanta från flytten i år",
    });
    const clr = el("a", { href: "#", title: "Nollställ till den beräknade standarden (★)" }, "återställ");
    const born = m.birth_year ? m.birth_year + " (" + (d.cohort_year - m.birth_year) + " år)" : "–";
    const noteDiv = el("div", { class: "muted", style: "font-size:.8rem;" }, m.note || "");
    const tr = el(
      "tr",
      {},
      el("td", { html: esc(m.member_no) }),
      el("td", { html: esc(m.name) }),
      el("td", { html: esc(born) }),
      el("td", { html: esc(m.source || "–") }),
      el("td", {}, targetSel),
      el("td", {}, statusSpan, noteDiv),
      el("td", {}, keep),
      el("td", {}, clr),
    );

    const apply = (entry) => {
      if (!entry) return;
      statusSpan.className = "status-" + entry.status;
      statusSpan.textContent = statusText(entry);
      noteDiv.textContent = entry.note || "";
      keep.checked = !!entry.stay;
      targetSel.value = entry.target || "";
      tr.style.opacity = entry.stay ? "0.55" : "";
      flash(tr);
    };
    const send = async (method, path, body) => {
      try {
        const r = await apiSend(method, path, body);
        apply(r.entry);
        return true;
      } catch (e) {
        alert(e.message);
        return false;
      }
    };
    const revert = () => send("DELETE", "uppflyttning/decision?member_no=" + encodeURIComponent(m.member_no));
    const decide = (body) => send("POST", "uppflyttning/decision", { member_no: m.member_no, by: "webb", ...body });

    targetSel.onchange = () => {
      const v = targetSel.value;
      if (v === "" || v === m.default_target) revert(); // back to the computed default
      else decide({ target_avdelning: v, stay_until: 0 }); // override target (clears any keep)
    };
    keep.onchange = async () => {
      const ok = keep.checked
        ? await decide({ target_avdelning: "", stay_until: d.cohort_year }) // keep in place this year
        : await revert();
      if (!ok) keep.checked = !keep.checked;
    };
    clr.onclick = (ev) => {
      ev.preventDefault();
      revert();
    };

    // initial state from the loaded entry
    targetSel.value = m.target || "";
    keep.checked = !!m.stay;
    if (m.stay) tr.style.opacity = "0.55";
    return tr;
  };

  root.append(
    el(
      "p",
      { class: "muted" },
      "Till (välj): måldelning per scout. ★ markerar den beräknade standarden (t.ex. Spårare → samma veckodag); " +
        "välj en annan för att flytta en individ annorlunda, eller för att ge en rad utan måldelning ett mål. " +
        "Behåll: bocka för att behålla scouten i nuvarande avdelning (undanta från flytten i år). " +
        "återställ: nollställ raden till ★-standarden.",
    ),
  );
  const headers = ["Medlemsnr", "Namn", "Född", "Från", "Till (välj)", "Status", "Behåll", ""];
  for (const [title, list] of [
    ["Redo att förflyttas", d.ready],
    ["Väntar på måldelning", d.pending],
    ["Behålls kvar (val)", d.kept],
    ["Utanför årskull", d.off_cohort],
    ["Undantagna (ledare/vuxna)", d.excluded],
  ]) {
    if (!list.length) continue;
    const t = el("table");
    t.append(el("thead", {}, el("tr", {}, ...headers.map((h) => el("th", {}, h)))));
    const tb = el("tbody");
    for (const m of list) tb.append(moveRow(m));
    t.append(tb);
    root.append(el("div", { class: "card" }, el("strong", {}, title + " (" + list.length + ")"), el("div", { class: "table-wrap" }, t)));
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

const CHK_SV = { ok: "OK", fail: "FEL", disabled: "Avstängd", fixture: "Fixtur" };

async function renderApiCheck(root) {
  const d = await api("api-check");
  const anyFail = d.checks.some((c) => c.status === "fail");

  // Overall status box — green when healthy, green-but-clearly-labelled in
  // fixture mode, red when any real key failed.
  if (d.fixture) {
    root.append(
      el(
        "div",
        { class: "banner banner-fixture" },
        el("div", {}, el("strong", {}, "ℹ FIXTURE-LÄGE — exempeldata")),
        el(
          "div",
          { class: "banner-sub" },
          "Inga anrop görs mot Scoutnet. All data kommer från committade exempelfiler. " +
            "Kontrollerna nedan är gröna för att visa att verktyget fungerar – inte att några riktiga nycklar testats.",
        ),
      ),
    );
  } else if (anyFail) {
    root.append(
      el(
        "div",
        { class: "banner banner-fail" },
        el("div", {}, el("strong", {}, "⚠ Ett eller flera API-anrop misslyckades")),
        el(
          "div",
          { class: "banner-sub" },
          "En nyckel kan vara felaktig, satt för fel endpoint, eller så stämmer inte entity-id:t. Se detaljer per endpoint nedan.",
        ),
      ),
    );
  } else {
    root.append(
      el(
        "div",
        { class: "banner banner-ok" },
        el("div", {}, el("strong", {}, "✓ Alla aktiva API-nycklar svarar")),
        el("div", { class: "banner-sub" }, "Läge: " + esc(d.mode) + ". Varje nyckel testades med en riktig läsning."),
      ),
    );
  }

  // A prominent info box per failing key (this is what tells any user something is wrong).
  for (const c of d.checks.filter((x) => x.status === "fail")) {
    root.append(
      el(
        "div",
        { class: "card infobox-fail" },
        el("strong", {}, "Fel: " + esc(c.endpoint) + " (" + esc(c.key_env) + ")"),
        el("div", { class: "muted" }, "Nyckeln är satt men anropet misslyckades:"),
        el("pre", { html: esc(c.detail) }),
      ),
    );
  }

  const pill = (c) => el("span", { class: "chk chk-" + c.status }, CHK_SV[c.status] || c.status);
  const fp = d.fingerprint || { algo: "sha256", chars: 8, over: "utf-8" };
  const fpHead = "Fingeravtryck (" + fp.algo + "[:" + fp.chars + "])";
  const card = el(
    "div",
    { class: "card" + (anyFail ? "" : " ok-frame") },
    el("strong", {}, "Endpoint-kontroller"),
    table(
      ["Endpoint", "Nyckel (env)", "Status", "Svar / detalj", fpHead],
      d.checks.map((c) => [c.endpoint, c.key_env, pill(c), c.detail, c.key_hash || "–"]),
    ),
  );
  // Explain the fingerprint so it can be replicated against a candidate key.
  card.append(
    el(
      "div",
      { class: "muted", style: "font-size:.82rem;margin-top:.5rem;" },
      "Fingeravtryck = " + fp.algo + "(nyckelns " + fp.over + "-bytes), hex, första " + fp.chars + " tecken. Reproducera:",
    ),
    el(
      "pre",
      {},
      "python3 -c \"import hashlib,sys;print(hashlib." +
        fp.algo +
        "(sys.argv[1].encode()).hexdigest()[:" +
        fp.chars +
        '])" DIN_NYCKEL',
    ),
  );
  root.append(card);
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
  // In fixture mode every enabled action runs against committed sample data,
  // not live Scoutnet — make that explicit next to each one.
  const fixtureNote = d.mode === "fixture" ? "Fixturdata (committad exempeldata, ej live)" : "";
  root.append(
    el(
      "div",
      { class: "card" },
      el("strong", {}, "Åtgärder"),
      table(
        ["Åtgärd", "Aktiverad", "Förklaring"],
        d.actions.map((a) => [a.action, a.enabled ? "ja" : "nej", a.reason || (a.enabled ? fixtureNote : "")]),
      ),
    ),
  );
  const om = d.openapi;
  root.append(el("div", { class: "card" }, el("strong", {}, "OpenAPI"), el("div", { class: "muted" }, om ? `version ${om.version} · ${om.git_commit || ""} · ${om.retrieved || ""}` : "ej vendorerad ännu")));
}

// --- Utför (write path, §8) -----------------------------------------------

const CAT_SV = {
  will_apply: "Kommer att flyttas",
  already_applied: "Redan på plats (hoppas över)",
  drifted: "Avviker – hoppas över",
};
const RUNSTATE_SV = {
  running: "Kör…",
  done: "Klar",
  failed: "Misslyckades",
  aborted: "Avbruten",
};

function preview(out, r) {
  // Group the pre-flight rows by category so the operator sees, before writing,
  // exactly what will happen and what is being skipped (§8 drift check).
  const byCat = { will_apply: [], already_applied: [], drifted: [] };
  for (const p of r.preflight) (byCat[p.category] || (byCat[p.category] = [])).push(p);
  out.replaceChildren(
    el(
      "div",
      { class: "grid" },
      stat(byCat.will_apply.length, "Kommer att flyttas"),
      stat(byCat.already_applied.length, "Redan på plats"),
      stat(byCat.drifted.length, "Avviker (hoppas över)"),
    ),
  );
  for (const cat of ["will_apply", "drifted", "already_applied"]) {
    const rows = byCat[cat] || [];
    if (!rows.length) continue;
    out.append(
      el(
        "div",
        { class: "card" },
        el("strong", {}, CAT_SV[cat] + " (" + rows.length + ")"),
        table(
          ["Medlemsnr", "Till (troop)", "Avdelning", "Nuvarande", "Anledning"],
          rows.map((p) => [p.member_no, p.target_troop_id, p.label || "–", p.current_troop_id ?? "–", p.reason || ""]),
        ),
      ),
    );
  }
  return byCat.will_apply.length;
}

function runStatusCard(area, s) {
  const j = s.journal || {};
  const counts = Object.entries(j).map(([k, v]) => `${k}: ${v}`).join(" · ") || "–";
  const card = el(
    "div",
    { class: "card" },
    el("strong", {}, "Körning " + s.run_id.slice(0, 8) + " · " + (RUNSTATE_SV[s.state] || s.state)),
    el("div", { class: "muted" }, s.kind + " · " + counts),
  );
  const failed = (s.members || []).filter((m) => m.state === "failed");
  if (failed.length) {
    const b = el("button", { class: "action" }, "Återuppta från felad chunk");
    b.onclick = async () => {
      try {
        await apiSend("POST", "write/runs/" + s.run_id + "/resume");
        pollRun(area, s.run_id);
      } catch (e) {
        alert(e.message);
      }
    };
    card.append(
      table(["Medlemsnr", "Fel"], failed.map((m) => [m.member_no, m.error || ""])),
      el("div", { style: "margin-top:.5rem;" }, b),
    );
  }
  if (s.state === "done" && s.undo_available) {
    const undoBtn = el("button", {}, "Ångra körningen (förhandsgranska)");
    const undoOut = el("div", {});
    undoBtn.onclick = async () => {
      try {
        const r = await apiSend("POST", "write/runs/" + s.run_id + "/undo"); // dry-run
        const n = preview(undoOut, r);
        const go = el("button", { class: "danger", style: "margin-top:.5rem;" }, "Utför ångra (" + n + ")");
        go.disabled = n === 0;
        go.onclick = async () => {
          if (!confirm("Ångra körningen? " + n + " medlem(mar) flyttas tillbaka.")) return;
          go.disabled = true;
          const r2 = await apiSend("POST", "write/runs/" + s.run_id + "/undo?mode=execute");
          pollRun(area, r2.run_id); // poll the new undo run to completion
        };
        undoOut.append(go);
      } catch (e) {
        undoOut.replaceChildren(el("p", { class: "err" }, e.message));
      }
    };
    card.append(el("div", { style: "margin-top:.5rem;" }, undoBtn), undoOut);
  }
  area.replaceChildren(card);
}

async function pollRun(area, runId) {
  const tick = async () => {
    let s;
    try {
      s = await api("write/runs/" + runId);
    } catch {
      area.replaceChildren(el("p", { class: "muted" }, "Startar körning…"));
      setTimeout(tick, 1000);
      return;
    }
    runStatusCard(area, s);
    if (s.state === "running") setTimeout(tick, 1000);
  };
  tick();
}

async function renderExecute(root) {
  const cap = await api("capabilities");
  if (!cap.read_write_active) {
    const reason =
      (cap.actions.find((a) => a.action === "execute_writes") || {}).reason ||
      "Skrivning kräver read_write-läge.";
    root.append(
      el(
        "div",
        { class: "card" },
        el("strong", {}, "Utför uppflyttning"),
        el("p", { class: "muted" }, "Ej tillgängligt i detta läge (" + esc(cap.mode) + "). " + esc(reason)),
        el("p", { class: "muted" }, "Granska och exportera changelist under fliken Uppflyttning."),
      ),
    );
    return;
  }

  root.append(
    el(
      "div",
      { class: "banner banner-fail" },
      el("div", {}, el("strong", {}, "⚠ READ_WRITE — skrivning mot Scoutnet")),
      el("div", { class: "banner-sub" }, "Torrkörning är standard. Utförande skriver på riktigt, en medlem i taget, och kan ångras så länge ögonblicksbilden finns kvar."),
    ),
  );

  // Off-cohort acknowledgement gate (§17): must be ticked before executing.
  let upp;
  try {
    upp = await api("uppflyttning");
  } catch (e) {
    root.append(el("p", { class: "err" }, "Kan inte beräkna uppflyttningen: " + e.message));
    return;
  }
  let ackedBy = null;
  const offCount = upp.off_cohort.length;

  const previewOut = el("div", {});
  const progress = el("div", {});
  const execBtn = el("button", { class: "danger" }, "Utför (skriv till Scoutnet)");
  execBtn.disabled = true;
  let willApply = 0;

  const dryBtn = el("button", { class: "action" }, "Förhandsgranska (torrkörning)");
  dryBtn.onclick = async () => {
    previewOut.replaceChildren(el("p", { class: "muted" }, "Kör torrkörning…"));
    try {
      const r = await apiSend("POST", "uppflyttning/run", { mode: "dry_run" });
      willApply = preview(previewOut, r);
      execBtn.disabled = willApply === 0 || (offCount > 0 && !ackedBy);
    } catch (e) {
      previewOut.replaceChildren(el("p", { class: "err" }, e.message));
    }
  };

  const controls = el("div", { class: "card" }, el("strong", {}, "Uppflyttning år " + esc(upp.cohort_year)));
  if (offCount > 0) {
    const ack = el("input", { type: "checkbox" });
    ack.onchange = () => {
      ackedBy = ack.checked ? "webb" : null;
      execBtn.disabled = willApply === 0 || !ackedBy;
    };
    controls.append(
      el(
        "label",
        { class: "muted", style: "display:block;margin:.4rem 0;" },
        ack,
        " Jag har granskat de " + offCount + " medlemmarna utanför årskull (fliken Uppflyttning) och vill fortsätta.",
      ),
    );
  }
  controls.append(el("div", { style: "margin-top:.4rem;" }, dryBtn, " ", execBtn));
  root.append(controls, previewOut, progress);

  execBtn.onclick = async () => {
    if (!confirm("Utför uppflyttningen? " + willApply + " medlem(mar) skrivs till Scoutnet.")) return;
    // Lock the blade's controls the moment we commit: the run is server-side and
    // serialised, so a stray second click must not fire another request.
    dryBtn.disabled = true;
    execBtn.disabled = true;
    try {
      const r = await apiSend("POST", "uppflyttning/run", { mode: "execute", ack_by: ackedBy });
      pollRun(progress, r.run_id);
    } catch (e) {
      progress.replaceChildren(el("p", { class: "err" }, e.message));
    }
  };

  // Run history + snapshots.
  try {
    const runs = (await api("write/runs")).runs || [];
    if (runs.length) {
      root.append(
        el(
          "div",
          { class: "card" },
          el("strong", {}, "Tidigare körningar"),
          table(
            ["Körning", "Typ", "Läge", "Status"],
            runs.map((r) => [r.run_id.slice(0, 8), r.kind, r.mode, RUNSTATE_SV[r.state] || r.state]),
          ),
        ),
      );
    }
    const snaps = (await api("write/snapshots")).snapshots || [];
    if (snaps.length) {
      const rows = snaps.map((s) => {
        const del = el("button", {}, "Radera");
        del.onclick = async () => {
          if (!confirm("Radera ögonblicksbilden? Ångra av dess körning blir omöjlig.")) return;
          await apiSend("DELETE", "write/snapshots/" + s.id);
          refresh();
        };
        return [s.taken_at, (s.size_bytes / 1024).toFixed(1) + " kB", s.run_id ? s.run_id.slice(0, 8) : "–", del];
      });
      root.append(el("div", { class: "card" }, el("strong", {}, "Ögonblicksbilder"), table(["Tidpunkt", "Storlek", "Körning", ""], rows)));
    }
  } catch {
    /* history is best-effort */
  }
}

// --- Verifiera skrivning (stage-2 single-member check, §8) -----------------

async function renderVerify(root) {
  const cap = await api("capabilities");
  if (!cap.read_write_active) {
    root.append(
      el(
        "div",
        { class: "card" },
        el("strong", {}, "Verifiera skrivning (stage 2)"),
        el("p", { class: "muted" }, "Endast i read_write-läge (nuvarande: " + esc(cap.mode) + ")."),
      ),
    );
    return;
  }
  const info = await api("write/verify");
  root.append(
    el(
      "div",
      { class: "banner banner-fail" },
      el("div", {}, el("strong", {}, "⚠ Testskrivning mot Scoutnet")),
      el("div", { class: "banner-sub" }, "Flytta EN medlem (helst platshållarkontot) för att bekräfta att troop_id fungerar, verifiera i Scoutnet, och ångra sedan."),
    ),
  );
  const memberLabel = (m) => (m.name ? `${m.name} (${m.member_no})` : m.member_no);

  root.append(
    el(
      "div",
      { class: "card" },
      el("strong", {}, "Tillåtna medlemmar (allowlist)"),
      el(
        "div",
        { class: "muted" },
        info.allowlist.length
          ? info.allowlist.map(memberLabel).join(", ")
          : "(tom — inga skrivningar tillåtna)",
      ),
      el("div", { class: "muted", style: "font-size:.82rem;" }, "Konfigureras via SCOUTNET_WRITE_ALLOWLIST (deployment) — kan inte ändras här."),
    ),
  );

  // Members are limited to the allowlist, so pick from a dropdown (first = default).
  const memberSel = el("select", {});
  for (const m of info.allowlist || []) {
    memberSel.append(el("option", { value: m.member_no }, memberLabel(m)));
  }
  const targetSel = el("select", {});
  targetSel.append(el("option", { value: "" }, "– välj måldelning –"));
  for (const a of info.avdelningar || []) {
    targetSel.append(el("option", { value: a.troop_id }, `${a.avdelning} (troop ${a.troop_id})`));
  }
  const progress = el("div", {});
  const dryBtn = el("button", { class: "action" }, "Testa (torrkörning)");
  const execBtn = el("button", { class: "danger" }, "Utför testflytt");
  execBtn.disabled = true;
  let willApply = 0;

  const body = () => ({ member_no: memberSel.value, target_troop_id: Number(targetSel.value) });
  const valid = () => memberSel.value && targetSel.value !== "";

  dryBtn.onclick = async () => {
    if (!valid()) {
      progress.replaceChildren(el("p", { class: "err" }, "Välj medlem och måldelning."));
      return;
    }
    progress.replaceChildren(el("p", { class: "muted" }, "Kör torrkörning…"));
    try {
      const r = await apiSend("POST", "write/verify", { ...body(), mode: "dry_run" });
      willApply = preview(progress, r);
      execBtn.disabled = willApply === 0;
    } catch (e) {
      progress.replaceChildren(el("p", { class: "err" }, e.message));
    }
  };
  execBtn.onclick = async () => {
    const chosen = memberSel.options[memberSel.selectedIndex]?.textContent || memberSel.value;
    if (!confirm("Utför testflytt av " + chosen + "? Detta skriver till Scoutnet.")) return;
    dryBtn.disabled = true;
    execBtn.disabled = true;
    try {
      const r = await apiSend("POST", "write/verify", { ...body(), mode: "execute" });
      pollRun(progress, r.run_id); // status card offers undo when done
    } catch (e) {
      progress.replaceChildren(el("p", { class: "err" }, e.message));
    }
  };

  root.append(
    el(
      "div",
      { class: "card" },
      el("strong", {}, "Testflytt av en medlem"),
      el("div", { style: "margin:.5rem 0;" }, el("label", {}, "Medlem "), memberSel, " ", el("label", {}, "Till avdelning "), targetSel),
      el("div", {}, dryBtn, " ", execBtn),
    ),
    progress,
  );
}

let renderGen = 0;

async function show(key) {
  const gen = ++renderGen; // guards against overlapping renders double-appending
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.k === key));
  const root = $("#content");
  root.replaceChildren(el("p", { class: "muted" }, "Laddar…"));
  const tab = TABS.find((t) => t[0] === key) || TABS[0];
  const container = el("div"); // build off-screen, swap in atomically
  try {
    await tab[2](container);
    if (gen !== renderGen) return; // a newer navigation superseded this one
    root.replaceChildren(container);
  } catch (e) {
    if (gen !== renderGen) return;
    root.replaceChildren(el("p", { class: "err" }, "Fel: " + e.message));
  }
  location.hash = key;
}

async function boot() {
  const nav = $("#nav");
  for (const group of NAV_GROUPS) {
    const wrap = el("div", { class: "nav-group" }, el("span", { class: "nav-group-label" }, group));
    for (const [key, label, , g] of TABS) {
      if (g !== group) continue;
      const b = el("button", {}, label);
      b.dataset.k = key;
      b.onclick = () => show(key);
      wrap.append(b);
    }
    nav.append(wrap);
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
  const banner = $("#api-banner");
  banner.onclick = () => show("apicheck"); // clickable → the blade with details
  show((location.hash || "#overview").slice(1));
  checkApiHealth(); // non-blocking; surfaces a site-wide banner if a key is broken
}

// Probe API health for the global banner. Fixture mode is fine (no banner); a
// real failure shows a red, clickable banner on every blade.
async function checkApiHealth() {
  const banner = $("#api-banner");
  try {
    const d = await api("api-check");
    const failed = d.checks.filter((c) => c.status === "fail").map((c) => c.endpoint);
    if (!d.fixture && failed.length) {
      banner.textContent = "⚠ API-fel: " + failed.join(", ") + " svarar inte — klicka för detaljer.";
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  } catch {
    banner.textContent = "⚠ Kunde inte kontrollera API-status — klicka för detaljer.";
    banner.hidden = false;
  }
}

boot();
