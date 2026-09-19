/* Metadata editor front end.
 *
 * State lives in `state`; every mutation ends in refresh(), which asks the
 * server for the pending view. The server owns what an edit means, so the
 * cards, the table, the linter and the diff can never disagree with the
 * file a write would actually produce.
 */

const state = {
  session: null,
  preset: "manual",
  profile: "iphone-15-pro",
  shift: 0,
  edits: {},          // key -> new value, or null to delete
  presets: {},
  profiles: {},
  categories: [],
  tags: [],
  selected: null,     // which category the detail table is showing
  revealed: false,    // whether sealed values are shown
};

const CATEGORY_LABEL = {
  location: "Location",
  device: "Device",
  content: "Content",
  time: "Time",
  software: "Software",
  embedded: "Embedded",
  benign: "Technical",
};

// Categories that identify you. Their cards read as risk while populated
// and as resolved once empty.
const RISKY = new Set(["location", "device", "content", "embedded"]);

const $ = (id) => document.getElementById(id);

function toast(message, bad = false) {
  const el = $("toast");
  el.textContent = message;
  el.classList.toggle("bad", bad);
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 4500);
}

function showError(message) {
  const el = $("error");
  el.textContent = message;
  el.hidden = false;
}

function clearError() { $("error").hidden = true; }

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

/* ---------- loading ---------- */

async function loadPresets() {
  const data = await api("/api/presets");
  state.presets = data.presets;

  const preset = $("preset");
  preset.innerHTML = "";
  for (const [key, description] of Object.entries(data.presets)) {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = key[0].toUpperCase() + key.slice(1);
    option.title = description;
    preset.append(option);
  }
  preset.value = state.preset;
  $("preset-help").textContent = data.presets[state.preset];

  state.profiles = data.profiles;

  const profile = $("profile");
  profile.innerHTML = "";
  const groups = [
    ["Plausible identities", data.credible],
    ["Novelty identities", data.novelty],
  ];
  for (const [caption, keys] of groups) {
    if (!keys || !keys.length) continue;
    const group = document.createElement("optgroup");
    group.label = caption;
    for (const key of keys) {
      const option = document.createElement("option");
      option.value = key;
      option.textContent = data.profiles[key].label;
      group.append(option);
    }
    profile.append(group);
  }
  profile.value = state.profile;
  renderProfileNote();
}

function renderProfileNote() {
  const note = $("profile-note");
  const profile = state.profiles[state.profile];
  const showing = state.preset === "reprofile" && profile && profile.note;
  note.hidden = !showing;
  if (!showing) return;
  note.textContent = profile.novelty
    ? `${profile.note} Consistency will flag this identity, which is the point — it is meant to be obviously untrue.`
    : profile.note;
}

async function upload(file) {
  clearError();
  toast(`Reading ${file.name} ...`);
  const body = new FormData();
  body.append("file", file);
  const data = await api("/api/upload", { method: "POST", body });

  state.session = data.session;
  state.edits = {};
  state.selected = null;
  state.revealed = false;

  $("file-label").textContent =
    `${data.filename} · ${data.container} · ${(data.size / 1048576).toFixed(1)} MB`;
  $("drop").hidden = true;
  $("workspace").hidden = false;
  $("gates").hidden = true;
  $("change-file").hidden = false;
  await refresh();
  toast(`Loaded ${data.filename}`);
}

/* ---------- risk cards ---------- */

function renderCards(categories) {
  state.categories = categories;
  const container = $("cards");
  container.innerHTML = "";

  const total = categories.reduce((sum, c) => sum + c.count, 0);
  $("tag-total").textContent = `${total} fields`;

  // Keep a selection that still exists, otherwise take the riskiest.
  if (!categories.some((c) => c.key === state.selected)) {
    state.selected = categories.length ? categories[0].key : null;
  }

  for (const category of categories) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "card";
    if (RISKY.has(category.key)) card.classList.add("risk");
    card.setAttribute("aria-pressed", String(category.key === state.selected));

    const top = document.createElement("span");
    top.className = "card-top";
    const count = document.createElement("span");
    count.className = "card-count";
    count.textContent = category.count;
    const name = document.createElement("span");
    name.className = "card-name";
    name.textContent = CATEGORY_LABEL[category.key] || category.key;
    top.append(count, name);

    const why = document.createElement("span");
    why.className = "card-why";
    why.textContent = category.summary;

    card.append(top, why);
    card.onclick = () => {
      state.selected = category.key;
      renderCards(state.categories);
      renderTags(state.tags);
    };
    container.append(card);
  }

  if (!categories.length) {
    container.innerHTML =
      `<p class="empty">Every field has been removed.</p>`;
  }
}

/* ---------- tag detail ---------- */

function renderTags(tags) {
  state.tags = tags;
  const container = $("tags");
  container.innerHTML = "";

  const rows = tags.filter((t) => t.category === state.selected);
  const meta = state.categories.find((c) => c.key === state.selected);

  $("detail-title").textContent =
    meta ? `${CATEGORY_LABEL[meta.key]} — ${rows.length} field${rows.length === 1 ? "" : "s"}`
         : "Details";
  $("detail-summary").textContent = meta ? meta.summary : "";
  $("reveal-all").textContent = state.revealed ? "Hide values" : "Reveal values";
  $("reveal-all").hidden = !rows.some((r) => r.sealed);

  if (!rows.length) {
    container.innerHTML = `<p class="empty">Nothing left in this group.</p>`;
    return;
  }
  for (const tag of rows) container.append(renderRow(tag));
}

function renderRow(tag) {
  const row = document.createElement("div");
  row.className = "tagrow";

  const edit = state.edits[tag.key];
  if (edit === null) row.classList.add("is-removed");
  else if (edit !== undefined) row.classList.add("is-edited");

  const left = document.createElement("div");

  const name = document.createElement("div");
  name.className = "tagname";
  const nameText = document.createElement("span");
  nameText.textContent = tag.name;
  const group = document.createElement("span");
  group.className = "grp";
  group.textContent = tag.group;
  name.append(nameText, group);

  const value = document.createElement("div");
  value.className = "tagvalue";
  const shown = tag.display || tag.value || "(empty)";
  if (tag.sealed && !state.revealed) {
    const veil = document.createElement("span");
    veil.className = "veil";
    veil.textContent = shown;
    veil.title = "Click to reveal";
    veil.onclick = () => veil.classList.toggle("open");
    value.append(veil);
  } else {
    value.textContent = shown;
  }

  left.append(name, value);

  const actions = document.createElement("div");
  actions.className = "tagactions";

  if (tag.editable) {
    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "link";
    editButton.textContent = "Edit";
    editButton.onclick = () => startEdit(tag, value, row);

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = edit === null ? "link" : "link danger";
    removeButton.textContent = edit === null ? "Keep" : "Remove";
    removeButton.onclick = () => {
      if (state.edits[tag.key] === null) delete state.edits[tag.key];
      else state.edits[tag.key] = null;
      refresh();
    };
    actions.append(editButton, removeButton);
  } else {
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.textContent = "derived";
    pill.title = "Computed by ExifTool from other fields, or needed to render "
               + "the image. It disappears on its own when its sources go.";
    actions.append(pill);
  }

  const what = document.createElement("p");
  what.className = "tagwhat";
  const whatText = document.createElement("span");
  whatText.textContent = tag.what + " ";
  const reveals = document.createElement("span");
  reveals.className = "reveals";
  reveals.textContent = tag.reveals;
  what.append(whatText, reveals);

  row.append(left, actions, what);
  return row;
}

function startEdit(tag, valueCell, row) {
  const current = state.edits[tag.key] ?? tag.value ?? "";
  const input = document.createElement("input");
  input.type = "text";
  input.value = current;
  valueCell.textContent = "";
  valueCell.append(input);
  input.focus();
  input.select();

  const commit = () => {
    const next = input.value;
    if (next === String(tag.value ?? "")) delete state.edits[tag.key];
    else state.edits[tag.key] = next;
    refresh();
  };
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") commit();
    if (event.key === "Escape") refresh();
  });
  input.addEventListener("blur", commit);
  row.classList.add("is-edited");
}

/* ---------- side panels ---------- */

function renderFindings(findings) {
  const container = $("findings");
  container.innerHTML = "";
  if (!findings.length) {
    container.innerHTML = `<p class="empty">Nothing contradicts itself.</p>`;
    return;
  }
  for (const finding of findings) {
    const row = document.createElement("div");
    row.className = `finding ${finding.severity}`;
    const rule = document.createElement("div");
    rule.className = "rulename";
    rule.textContent = `${finding.severity} · ${finding.rule.replace(/_/g, " ")}`;
    const message = document.createElement("div");
    message.className = "msgtext";
    message.textContent = finding.message;
    row.append(rule, message);
    container.append(row);
  }
}

function renderDiff(diff) {
  const container = $("diff");
  container.innerHTML = "";
  $("diff-count").textContent = diff.length ? `${diff.length}` : "";
  if (!diff.length) {
    container.innerHTML = `<p class="empty">No changes pending.</p>`;
    return;
  }
  for (const entry of diff) {
    const row = document.createElement("div");
    row.className = `diffrow ${entry.kind}`;
    const key = document.createElement("div");
    key.className = "k";
    const kind = document.createElement("span");
    kind.className = "kind";
    kind.textContent = entry.kind;
    const label = document.createElement("span");
    label.textContent = entry.key;
    key.append(kind, label);
    const value = document.createElement("div");
    value.className = "v";
    value.textContent = entry.kind === "changed"
      ? `${entry.before} → ${entry.after}`
      : (entry.before || entry.after);
    row.append(key, value);
    container.append(row);
  }
}

function renderGates(result) {
  const panel = $("gates");
  panel.hidden = false;
  panel.innerHTML = "";

  const heading = document.createElement("h2");
  heading.textContent = "Verification";
  panel.append(heading);

  const head = document.createElement("div");
  head.className = "gatehead";
  const verdict = document.createElement("span");
  verdict.className = `verdict ${result.ok ? "" : "bad"}`;
  verdict.textContent = result.ok ? "Verified" : "Refused";
  const note = document.createElement("span");
  note.className = "hint m0";
  note.textContent = result.ok
    ? `${result.removed} field(s) removed, ${result.changed} changed. Your original is untouched.`
    : "A check failed, so the output was discarded. Your original is untouched.";
  head.append(verdict, note);
  panel.append(head);

  const trustrow = document.createElement("div");
  trustrow.className = "trustrow";
  for (const gate of result.gates) {
    const chip = document.createElement("span");
    chip.className = `trust ${gate.ok ? "on" : "attn"}`;
    chip.innerHTML = `<span class="dot"></span>`;
    chip.append(document.createTextNode(gate.name));
    chip.title = gate.meaning;
    trustrow.append(chip);
  }
  panel.append(trustrow);

  const list = document.createElement("div");
  list.className = "gatelist mt16";
  for (const gate of result.gates) {
    const row = document.createElement("div");
    row.className = "gate";
    const dot = document.createElement("span");
    dot.className = `dot ${gate.ok ? "pass" : "fail"}`;
    const body = document.createElement("div");
    body.className = "gate-body";
    const name = document.createElement("div");
    name.className = "gate-name";
    name.textContent = gate.name;
    const meaning = document.createElement("div");
    meaning.className = "gate-meaning";
    meaning.textContent = gate.meaning;
    const detail = document.createElement("div");
    detail.className = "gate-detail";
    detail.textContent = gate.detail;
    body.append(name, meaning, detail);
    row.append(dot, body);
    list.append(row);
  }
  panel.append(list);

  if (result.ok && result.saved_path) {
    const saved = document.createElement("div");
    saved.className = "savedbar";
    const lead = document.createElement("span");
    lead.className = "lead";
    lead.textContent = "Saved to disk";
    const path = document.createElement("code");
    path.className = "path";
    path.textContent = result.saved_path;

    const copy = document.createElement("button");
    copy.type = "button";
    copy.textContent = "Copy path";
    copy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(result.saved_path);
        toast("Path copied.");
      } catch {
        // Clipboard access can be refused; selecting the text still works.
        const range = document.createRange();
        range.selectNodeContents(path);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        toast("Path selected — press Ctrl+C to copy.");
      }
    };

    const download = document.createElement("a");
    download.className = "button-link";
    download.href = result.download;
    download.setAttribute("download", result.saved_name || "");
    download.textContent = "Also download";

    const again = document.createElement("label");
    again.className = "button-link";
    again.setAttribute("for", "file-input");
    again.textContent = "Clean another file";

    saved.append(lead, path, copy, download, again);
    panel.append(saved);
  }
}

/* ---------- actions ---------- */

function requestBody() {
  return {
    session: state.session,
    preset: state.preset,
    profile: state.profile,
    time_shift_days: state.shift,
    edits: state.edits,
  };
}

async function refresh() {
  if (!state.session) return;
  // Any settings change invalidates an earlier result. Leaving the panel up
  // would offer a download that no longer matches what is on screen.
  $("gates").hidden = true;
  try {
    const data = await api("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody()),
    });
    renderCards(data.categories);
    renderTags(data.tags);
    renderFindings(data.findings);
    renderDiff(data.diff);
    $("plan-note").textContent = data.diff.length
      ? `${data.diff.length} change(s) staged`
      : "nothing staged yet";
    clearError();
  } catch (error) {
    showError(error.message);
  }
}

async function applyChanges() {
  const button = $("apply");
  button.disabled = true;
  button.textContent = "Verifying...";
  try {
    const result = await api("/api/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody()),
    });
    renderGates(result);
    toast(result.ok ? "Written and verified." : "Refused: a check failed.", !result.ok);
    $("gates").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    showError(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Write verified copy";
  }
}

/* ---------- theme ---------- */

const THEMES = ["dark", "light", "hc-dark", "hc-light"];
const THEME_LABEL = {
  dark: "Dark", light: "Light", "hc-dark": "High contrast dark",
  "hc-light": "High contrast light",
};

function applyTheme(name) {
  document.documentElement.setAttribute("data-theme", name);
  $("theme-label").textContent = THEME_LABEL[name];
  try { localStorage.setItem("theme", name); } catch { /* private mode */ }
}

function initTheme() {
  let stored = null;
  try { stored = localStorage.getItem("theme"); } catch { /* private mode */ }
  applyTheme(THEMES.includes(stored) ? stored : "dark");
}

/* ---------- wiring ---------- */

function wire() {
  const drop = $("drop");
  const input = $("file-input");

  // Every label with for="file-input" opens the picker natively; JS only
  // handles the result. Clearing value afterwards matters: without it,
  // choosing the SAME file twice fires no change event and looks broken.
  input.onchange = () => {
    const file = input.files[0];
    input.value = "";
    if (file) upload(file).catch((e) => showError(e.message));
  };

  for (const event of ["dragenter", "dragover"]) {
    drop.addEventListener(event, (e) => {
      e.preventDefault();
      drop.classList.add("over");
    });
  }
  for (const event of ["dragleave", "drop"]) {
    drop.addEventListener(event, (e) => {
      e.preventDefault();
      drop.classList.remove("over");
    });
  }
  drop.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) upload(file).catch((error) => showError(error.message));
  });

  // Once a file is open the start panel is hidden, so the whole window
  // accepts a drop. That is the fastest way to move on to the next photo.
  for (const event of ["dragenter", "dragover", "drop"]) {
    window.addEventListener(event, (e) => {
      if (!e.dataTransfer || !e.dataTransfer.types.includes("Files")) return;
      e.preventDefault();
      document.body.classList.toggle("dragging", event !== "drop");
      if (event === "drop" && e.dataTransfer.files[0]) {
        upload(e.dataTransfer.files[0]).catch((err) => showError(err.message));
      }
    });
  }
  window.addEventListener("dragleave", (e) => {
    if (e.relatedTarget === null) document.body.classList.remove("dragging");
  });

  $("preset").onchange = (e) => {
    state.preset = e.target.value;
    $("preset-help").textContent = state.presets[state.preset] || "";
    $("profile-control").hidden = state.preset !== "reprofile";
    renderProfileNote();
    refresh();
  };
  $("profile").onchange = (e) => {
    state.profile = e.target.value;
    renderProfileNote();
    refresh();
  };
  $("shift").onchange = (e) => {
    state.shift = parseInt(e.target.value, 10) || 0;
    refresh();
  };
  $("apply").onclick = applyChanges;

  $("reveal-all").onclick = () => {
    state.revealed = !state.revealed;
    renderTags(state.tags);
  };

  $("theme").onclick = () => {
    const current = document.documentElement.getAttribute("data-theme");
    applyTheme(THEMES[(THEMES.indexOf(current) + 1) % THEMES.length]);
  };
}

initTheme();
wire();
loadPresets().catch((error) => showError(error.message));
