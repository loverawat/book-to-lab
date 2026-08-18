let CONTENT = null;
let PROGRESS = null;
let CURRENT_BLOB_ID = null;

const $ = (id) => document.getElementById(id);

async function api(path, opts) {
  const res = await fetch(path, opts);
  return res.json();
}

function orderedBlobs() {
  const out = [];
  for (const chapter of CONTENT.chapters) {
    for (const blob of chapter.blobs) out.push({ chapter, blob });
  }
  return out;
}

function findBlob(id) {
  for (const { chapter, blob } of orderedBlobs()) {
    if (blob.id === id) return { chapter, blob };
  }
  return {};
}

function renderSidebar() {
  $("book-title").textContent = CONTENT.title;
  const list = $("chapter-list");
  list.innerHTML = "";
  let passed = 0, total = 0;
  for (const chapter of CONTENT.chapters) {
    const block = document.createElement("div");
    block.className = "chapter-block";
    const h4 = document.createElement("h4");
    h4.textContent = chapter.title;
    block.appendChild(h4);
    for (const blob of chapter.blobs) {
      total++;
      const state = PROGRESS.blobs[blob.id] || { status: "locked" };
      if (state.status === "passed") passed++;
      const item = document.createElement("div");
      item.className = "blob-item" + (blob.id === CURRENT_BLOB_ID ? " active" : "");
      const dot = document.createElement("span");
      dot.className = "status-dot status-" + state.status;
      item.appendChild(dot);
      const label = document.createElement("span");
      label.textContent = blob.concept;
      item.appendChild(label);
      if (state.status !== "locked") {
        item.onclick = () => loadBlob(blob.id);
      }
      block.appendChild(item);
    }
    list.appendChild(block);
  }
  $("progress-fill").style.width = total ? `${(100 * passed) / total}%` : "0%";
}

function renderReading(blob) {
  $("concept-title").textContent = blob.concept;
  $("reading-text").innerHTML = blob.reading_html || `<p>${blob.reading}</p>`;
}

function renderExercise(blob) {
  $("run-output").textContent = "";
  $("hint-output").innerHTML = "";
  $("claude-review-output").innerHTML = "";
  $("reveal-output").classList.add("hidden");
  $("reveal-output").textContent = "";
  $("next-row").classList.add("hidden");

  const ex = blob.exercise;
  const state = PROGRESS.blobs[blob.id] || {};
  $("exercise-prompt").textContent = ex.prompt;

  const isImpl = ex.type === "implementation";
  $("impl-exercise").classList.toggle("hidden", !isImpl);
  $("short-answer-exercise").classList.toggle("hidden", isImpl);

  if (isImpl) {
    $("code-input").value = state.draft || ex.starter_code || "";
  } else {
    $("answer-reveal").classList.add("hidden");
    $("expected-answer").textContent = ex.expected_answer || "";
  }

  if (state.status === "passed") $("next-row").classList.remove("hidden");
}

let draftSaveTimer = null;

function saveDraftNow() {
  if (!CURRENT_BLOB_ID) return;
  const { blob } = findBlob(CURRENT_BLOB_ID);
  if (!blob || blob.exercise.type !== "implementation") return;
  const code = $("code-input").value;
  navigator.sendBeacon
    ? navigator.sendBeacon(
        "/api/save-draft",
        new Blob([JSON.stringify({ blob_id: CURRENT_BLOB_ID, code })], { type: "application/json" })
      )
    : api("/api/save-draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ blob_id: CURRENT_BLOB_ID, code }),
      });
}

function scheduleDraftSave() {
  clearTimeout(draftSaveTimer);
  draftSaveTimer = setTimeout(saveDraftNow, 800);
}

$("code-input").addEventListener("input", scheduleDraftSave);
$("code-input").addEventListener("blur", saveDraftNow);
window.addEventListener("beforeunload", saveDraftNow);

async function loadBlob(blobId) {
  saveDraftNow();
  clearTimeout(draftSaveTimer);
  CURRENT_BLOB_ID = blobId;
  const { blob } = findBlob(blobId);
  renderReading(blob);
  renderExercise(blob);
  renderSidebar();
  window.scrollTo(0, 0);
}

async function refreshContent() {
  const data = await api("/api/content");
  CONTENT = data.content;
  PROGRESS = data.progress;
  if (!CURRENT_BLOB_ID) {
    const first = orderedBlobs().find(
      ({ blob }) => (PROGRESS.blobs[blob.id] || {}).status !== "locked"
    );
    if (first) CURRENT_BLOB_ID = first.blob.id;
  }
  renderSidebar();
  if (CURRENT_BLOB_ID) {
    const { blob } = findBlob(CURRENT_BLOB_ID);
    renderReading(blob);
    renderExercise(blob);
  }
}

async function checkReviewDue() {
  const data = await api("/api/review-due");
  if (data.blob) {
    $("review-banner").classList.remove("hidden");
    $("review-banner-text").textContent = `Time to review: ${data.blob.concept}`;
    $("review-banner-go").onclick = () => {
      loadBlob(data.blob.id);
      $("review-banner").classList.add("hidden");
    };
  }
}

$("run-btn").onclick = async () => {
  const code = $("code-input").value;
  $("run-output").textContent = "Running...";
  const result = await api("/api/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blob_id: CURRENT_BLOB_ID, code }),
  });
  $("run-output").textContent = (result.passed ? "PASSED\n\n" : "FAILED\n\n") + result.output;
  await refreshContent();
};

$("hint-btn").onclick = async () => {
  const el = $("hint-output");
  const level = el.dataset.level ? parseInt(el.dataset.level) : 0;
  const result = await api("/api/hint", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blob_id: CURRENT_BLOB_ID, level }),
  });
  if (result.hint) {
    const p = document.createElement("p");
    p.textContent = `Hint ${level + 1}: ${result.hint}`;
    el.appendChild(p);
    el.dataset.level = level + 1;
  }
  if (level + 1 >= result.total_hints) $("hint-btn").disabled = true;
};

$("claude-review-btn").onclick = async () => {
  const code = $("code-input").value;
  $("claude-review-output").textContent = "Asking claude (grounded in this chapter only)...";
  const result = await api("/api/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blob_id: CURRENT_BLOB_ID, code }),
  });
  $("claude-review-output").textContent = result.feedback;
};

$("reveal-btn").onclick = () => {
  const { blob } = findBlob(CURRENT_BLOB_ID);
  const out = $("reveal-output");
  out.textContent = blob.exercise.reference_solution;
  out.classList.remove("hidden");
};

$("reveal-answer-btn").onclick = () => {
  $("answer-reveal").classList.remove("hidden");
};

$("got-it-btn").onclick = async () => {
  await api("/api/self-assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blob_id: CURRENT_BLOB_ID, correct: true }),
  });
  await refreshContent();
};

$("missed-it-btn").onclick = async () => {
  await api("/api/self-assess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blob_id: CURRENT_BLOB_ID, correct: false }),
  });
  await refreshContent();
};

$("next-btn").onclick = () => {
  const ids = orderedBlobs().map(({ blob }) => blob.id);
  const idx = ids.indexOf(CURRENT_BLOB_ID);
  if (idx >= 0 && idx + 1 < ids.length) loadBlob(ids[idx + 1]);
};

$("show-graph-btn").onclick = async () => {
  const data = await api(`/api/graph?blob_id=${encodeURIComponent(CURRENT_BLOB_ID)}&depth=4`);
  const container = $("graph-tree");
  container.innerHTML = "";
  container.appendChild(renderGraphNode(data.graph, true));
  $("graph-modal").classList.remove("hidden");
};
$("graph-close-btn").onclick = () => $("graph-modal").classList.add("hidden");

function renderGraphNode(node, isRoot) {
  const div = document.createElement("div");
  div.className = isRoot ? "" : "graph-node";
  const label = document.createElement("div");
  label.className = "concept";
  label.textContent = node.concept || node.id;
  div.appendChild(label);
  if (node.prerequisites) {
    for (const child of node.prerequisites) {
      div.appendChild(renderGraphNode(child, false));
    }
  } else if (!isRoot && !node.prerequisites) {
    const leaf = document.createElement("div");
    leaf.style.color = "var(--text-dim)";
    leaf.style.fontSize = "12px";
    leaf.textContent = "(no further prerequisites)";
    div.appendChild(leaf);
  }
  return div;
}

refreshContent();
checkReviewDue();
