/* Metadata editor front end.
 *
 * State lives in `state`; every mutation ends in refresh(), which asks the
 * server for the pending view. The server owns what an edit means, so the
 * table, the linter panel and the diff can never disagree with the file
 * that a write would produce.
 */

const state = {
  session: null,
  preset: "manual",
  profile: "iphone-15-pro",
  shift: 0,
  edits: {},      // key -> new value, or null to delete
  tags: [],
  presets: {},
};

const CATEGORY_ORDER = [
  "location", "device", "content", "time", "software", "embedded", "benign",
];

const CATEGORY_LABEL = {
  location: "Location",
  device: "Device identity",
  content: "Content and people",
  time: "Timestamps",
  software: "Software trail",
  embedded: "Embedded images",
  benign: "Technical",
};

const CATEGORY_NOTE = {
  location: "Where the photo was taken.",
  device: "Which specific unit took it.",
  content: "What is in it, including names of people.",
  time: "When it was taken.",
  software: "What has edited it.",
  embedded: "Thumbnails, which are often the original pre-edit frame.",
  benign: "Needed to render the image correctly.",
};

const $ = (id) => document.getElementById(id);

function toast(message, bad = false) {
  const el = $("toast");
  el.textContent = message;
  el.classList.toggle("bad", bad);
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 4200);
}

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

  const profile = $("profile");
  profile.innerHTML = "";
  for (const [key, label] of Object.entries(data.profiles)) {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = label;
    profile.append(option);
  }
  profile.value = state.profile;
}

async function upload(file) {
  const body = new FormData();
  body.append("file", file);
  const data = await api("/api/upload", { method: "POST", body });

  state.session = data.session;
  state.edits = {};
  $("file-label").textContent =
    `${data.filename} - ${data.container} - ${(data.size / 1048576).toFixed(1)} MB`;
  $("drop").hidden = true;
  $("workspace").hidden = false;
  $("gates").hidden = true;
  renderLegend();
  await refresh();
  toast(`Loaded ${data.filename}`);
}

/* ---------- rendering ---------- */

function renderLegend() {
  $("legend").innerHTML = CATEGORY_ORDER.map((c) =>
    `<span><i class="swatch" style="background:var(--${c})"></i>${CATEGORY_LABEL[c]}</span>`
  ).join("");
}

function renderTags(tags) {
  state.tags = tags;
  const container = $("tags");
  container.innerHTML = "";

  const grouped = new Map();
  for (const tag of tags) {
    if (!grouped.has(tag.category)) grouped.set(tag.category, []);
    grouped.get(tag.category).push(tag);
  }

  for (const category of CATEGORY_ORDER) {
    const rows = grouped.get(category);
    if (!rows || !rows.length) continue;

    const section = document.createElement("section");
    section.className = "group";
    section.innerHTML = `
      <div class="group-head">
        <i class="swatch" style="background:var(--${category})"></i>
        <span class="group-title">${CATEGORY_LABEL[category]}</span>
        <span class="group-count">${rows.length} &middot; ${CATEGORY_NOTE[category]}</span>
      </div>`;

    for (const tag of rows) section.append(renderRow(tag));
    container.append(section);
  }

  if (!container.children.length) {
    container.innerHTML = `<p class="empty">No metadata left in this file.</p>`;
  }
}

function renderRow(tag) {
  const row = document.createElement("div");
  row.className = "row";

  const edit = state.edits[tag.key];
  if (edit === null) row.classList.add("is-removed");
  else if (edit !== undefined) row.classList.add("is-edited");

  const key = document.createElement("div");
  key.className = "row-key";
  key.innerHTML = `<div class="row-name"></div><div class="row-group"></div>`;
  key.querySelector(".row-name").textContent = tag.name;
  key.querySelector(".row-group").textContent = tag.group;

  const value = document.createElement("div");
  value.className = "row-value";
  value.textContent = tag.display || tag.value || "(empty)";

  const actions = document.createElement("div");
  actions.className = "row-actions";

  if (tag.editable) {
    const editButton = document.createElement("button");
    editButton.className = "iconbtn";
    editButton.textContent = "Edit";
    editButton.onclick = () => startEdit(tag, value, row);

    const removeButton = document.createElement("button");
    removeButton.className = "iconbtn";
    removeButton.textContent = edit === null ? "Keep" : "Remove";
    removeButton.onclick = () => {
      if (state.edits[tag.key] === null) delete state.edits[tag.key];
      else state.edits[tag.key] = null;
      refresh();
    };
    actions.append(editButton, removeButton);
  } else {
    const note = document.createElement("span");
    note.className = "muted small";
    note.textContent = "derived";
    note.title = "Computed by ExifTool from other tags, or needed to render " +
                 "the image. Not directly editable.";
    actions.append(note);
  }

  row.append(key, value, actions);
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

function renderFindings(findings) {
  const container = $("findings");
  if (!findings.length) {
    container.innerHTML = `<p class="empty">Nothing contradicts itself.</p>`;
    return;
  }
  container.innerHTML = findings.map((finding) => `
    <div class="finding">
      <span class="finding-rule ${finding.severity}">${finding.severity} &middot; ${finding.rule.replace(/_/g, " ")}</span>
      <span class="finding-msg"></span>
    </div>`).join("");
  container.querySelectorAll(".finding-msg").forEach((node, index) => {
    node.textContent = findings[index].message;
  });
}

function renderDiff(diff) {
  const container = $("diff");
  if (!diff.length) {
    container.innerHTML = `<p class="empty">No changes pending.</p>`;
    return;
  }
  container.innerHTML = "";
  for (const entry of diff) {
    const row = document.createElement("div");
    row.className = `diff-row diff-${entry.kind}`;
    const key = document.createElement("div");
    key.className = "diff-key";
    key.textContent = entry.key;
    const value = document.createElement("div");
    value.className = "diff-val";
    value.textContent = entry.kind === "changed"
      ? `${entry.before}  ->  ${entry.after}`
      : (entry.before || entry.after);
    row.append(key, value);
    container.append(row);
  }
}

function renderGates(result) {
  const container = $("gates");
  container.hidden = false;
  container.className = `gates ${result.ok ? "pass" : "fail"}`;

  const head = document.createElement("div");
  head.className = "gates-head";
  const summary = document.createElement("div");
  summary.innerHTML = `<h2>${result.ok ? "Verified" : "Refused"}</h2>`;
  const note = document.createElement("div");
  note.className = "muted small";
  note.textContent = result.ok
    ? `${result.removed} tag(s) removed, ${result.changed} changed. Your original is untouched.`
    : "The output failed a check and was discarded. Your original is untouched.";
  summary.append(note);
  head.append(summary);

  if (result.download) {
    const link = document.createElement("a");
    link.className = "download";
    link.href = result.download;
    link.textContent = "Download clean copy";
    head.append(link);
  }
  container.innerHTML = "";
  container.append(head);

  for (const gate of result.gates) {
    const row = document.createElement("div");
    row.className = "gate";
    const mark = document.createElement("div");
    mark.className = `gate-mark ${gate.ok ? "ok" : "bad"}`;
    mark.textContent = gate.ok ? "✓" : "✗";
    const body = document.createElement("div");
    const name = document.createElement("div");
    name.className = "gate-name";
    name.textContent = gate.name;
    name.title = gate.meaning;
    const detail = document.createElement("div");
    detail.className = "gate-detail";
    detail.textContent = gate.detail;
    body.append(name, detail);
    row.append(mark, body);
    container.append(row);
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
    renderTags(data.tags);
    renderFindings(data.findings);
    renderDiff(data.diff);
  } catch (error) {
    toast(error.message, true);
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
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "Write clean copy";
  }
}

/* ---------- wiring ---------- */

function wire() {
  const drop = $("drop");
  const input = $("file-input");

  $("browse").onclick = () => input.click();
  input.onchange = () => { if (input.files[0]) upload(input.files[0]); };

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
    if (file) upload(file).catch((error) => toast(error.message, true));
  });

  $("preset").onchange = (e) => {
    state.preset = e.target.value;
    $("preset-help").textContent = state.presets[state.preset] || "";
    $("profile-control").hidden = state.preset !== "reprofile";
    refresh();
  };
  $("profile").onchange = (e) => { state.profile = e.target.value; refresh(); };
  $("shift").onchange = (e) => {
    state.shift = parseInt(e.target.value, 10) || 0;
    refresh();
  };
  $("apply").onclick = applyChanges;
}

wire();
loadPresets().catch((error) => toast(error.message, true));
