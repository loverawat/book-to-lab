let CONTENT = null;
let PROGRESS = null;
let CURRENT_BLOB_ID = null;

const $ = (id) => document.getElementById(id);

async function api(path, opts) {
  const res = await fetch(path, opts);
  return res.json();
}

const INDENT = "    "; // 4 spaces, matches generated starter_code/reference_solution

// Minimal code-editing affordances for a plain <textarea>: Tab inserts an
// indent instead of moving focus, Shift+Tab removes one, Enter continues
// the previous line's indentation (plus one more level after a trailing
// ":"). Deliberately not a real editor (no highlighting/bracket matching) -
// see CLAUDE.md for why: this covers what was actually asked for at zero
// added weight, a real editor library would need vendoring or a CDN.
function enableCodeEditing(id) {
  const el = $(id);
  el.addEventListener("keydown", (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const { value, selectionStart: start, selectionEnd: end } = el;
      if (e.shiftKey) {
        const lineStart = value.lastIndexOf("\n", start - 1) + 1;
        const match = value.slice(lineStart, start).match(/^( {1,4}|\t)/);
        if (match) {
          el.value = value.slice(0, lineStart) + value.slice(lineStart + match[0].length);
          el.selectionStart = el.selectionEnd = start - match[0].length;
        }
      } else {
        el.value = value.slice(0, start) + INDENT + value.slice(end);
        el.selectionStart = el.selectionEnd = start + INDENT.length;
      }
      el.dispatchEvent(new Event("input"));
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const { value, selectionStart: start, selectionEnd: end } = el;
      const lineStart = value.lastIndexOf("\n", start - 1) + 1;
      const line = value.slice(lineStart, start);
      let indent = (line.match(/^\s*/) || [""])[0];
      if (line.trim().endsWith(":")) indent += INDENT;
      const insertion = "\n" + indent;
      el.value = value.slice(0, start) + insertion + value.slice(end);
      el.selectionStart = el.selectionEnd = start + insertion.length;
      el.dispatchEvent(new Event("input"));
    }
  });
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
      const dotStatus = state.status === "passed" && state.skipped ? "skipped" : state.status;
      dot.className = "status-dot status-" + dotStatus;
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

let PENDING_FOLLOW_UP = null; // { question } while a follow-up round is in progress

function renderExercise(blob) {
  $("run-output").textContent = "";
  $("hint-output").innerHTML = "";
  $("claude-review-output").innerHTML = "";
  $("reveal-output").classList.add("hidden");
  $("reveal-output").textContent = "";
  $("next-row").classList.add("hidden");
  $("answer-input").value = "";
  $("grade-answer-output").innerHTML = "";
  $("follow-up-block").classList.add("hidden");
  $("follow-up-input").value = "";
  PENDING_FOLLOW_UP = null;

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
  $("skip-btn").classList.toggle("hidden", state.status === "passed");
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

function openReviewModal(reviewBlob) {
  const ex = reviewBlob.exercise;
  const isImpl = ex.type === "implementation";
  $("review-modal-title").textContent = reviewBlob.concept;
  $("review-modal-badge").textContent = reviewBlob.is_variant
    ? "Fresh variant - different specifics, same concept"
    : "Original exercise (claude was unreachable, showing the stored version)";
  $("review-modal-prompt").textContent = ex.prompt;
  $("review-code-input").classList.toggle("hidden", !isImpl);
  $("review-answer-input").classList.toggle("hidden", isImpl);
  $("review-code-input").value = isImpl ? ex.starter_code || "" : "";
  $("review-answer-input").value = "";
  $("review-output").textContent = "";
  $("review-modal").dataset.blobId = reviewBlob.id;
  $("review-modal").dataset.isImpl = isImpl ? "1" : "";
  $("review-modal").classList.remove("hidden");
}

async function checkReviewDue() {
  const data = await api("/api/review-due");
  if (data.blob) {
    $("review-banner").classList.remove("hidden");
    $("review-banner-text").textContent = `Time to review: ${data.blob.concept}`;
    $("review-banner-go").onclick = () => {
      openReviewModal(data.blob);
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

function renderVerdict(container, verdict, feedback) {
  container.innerHTML = "";
  const badge = document.createElement("p");
  badge.textContent = `Verdict: ${verdict}`;
  container.appendChild(badge);
  const fb = document.createElement("p");
  fb.textContent = feedback;
  container.appendChild(fb);
}

$("grade-answer-btn").onclick = async () => {
  const answer = $("answer-input").value;
  $("grade-answer-output").textContent = "Grading (grounded in this chapter only)...";
  const result = await api("/api/grade-answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blob_id: CURRENT_BLOB_ID, answer }),
  });
  if (result.error) {
    $("grade-answer-output").textContent = result.error;
    return;
  }
  renderVerdict($("grade-answer-output"), result.verdict, result.feedback);
  if (!result.final) {
    PENDING_FOLLOW_UP = { question: result.follow_up_question, originalAnswer: answer };
    $("follow-up-question").textContent = result.follow_up_question;
    $("follow-up-block").classList.remove("hidden");
  } else {
    $("follow-up-block").classList.add("hidden");
    await refreshContent();
  }
};

$("submit-follow-up-btn").onclick = async () => {
  if (!PENDING_FOLLOW_UP) return;
  const followUpAnswer = $("follow-up-input").value;
  $("grade-answer-output").textContent = "Grading...";
  const result = await api("/api/grade-answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      blob_id: CURRENT_BLOB_ID,
      answer: PENDING_FOLLOW_UP.originalAnswer,
      follow_up_question: PENDING_FOLLOW_UP.question,
      follow_up_answer: followUpAnswer,
    }),
  });
  if (result.error) {
    $("grade-answer-output").textContent = result.error;
    return;
  }
  renderVerdict($("grade-answer-output"), result.verdict, result.feedback);
  $("follow-up-block").classList.add("hidden");
  PENDING_FOLLOW_UP = null;
  await refreshContent();
};

$("next-btn").onclick = () => {
  const ids = orderedBlobs().map(({ blob }) => blob.id);
  const idx = ids.indexOf(CURRENT_BLOB_ID);
  if (idx >= 0 && idx + 1 < ids.length) loadBlob(ids[idx + 1]);
};

$("skip-btn").onclick = async () => {
  await api("/api/skip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blob_id: CURRENT_BLOB_ID }),
  });
  await refreshContent();
};

$("reset-progress-btn").onclick = async () => {
  const ok = confirm(
    "Reset all progress for this book? This erases every passed/skipped exercise and cannot be undone."
  );
  if (!ok) return;
  await api("/api/reset", { method: "POST" });
  CURRENT_BLOB_ID = null;
  await refreshContent();
};

$("shutdown-btn").onclick = async () => {
  const ok = confirm("Shut down the server? You'll need to run python3 server.py again to reopen this book.");
  if (!ok) return;
  await api("/api/shutdown", { method: "POST" });
  $("app").classList.add("hidden");
  $("shutdown-overlay").classList.remove("hidden");
};

$("show-graph-btn").onclick = async () => {
  const data = await api(`/api/graph?blob_id=${encodeURIComponent(CURRENT_BLOB_ID)}&depth=4`);
  const container = $("graph-tree");
  container.innerHTML = "";
  container.appendChild(renderGraphNode(data.graph, true));
  $("graph-modal").classList.remove("hidden");
};
$("graph-close-btn").onclick = () => $("graph-modal").classList.add("hidden");

$("review-close-btn").onclick = () => $("review-modal").classList.add("hidden");

$("review-submit-btn").onclick = async () => {
  const modal = $("review-modal");
  const blobId = modal.dataset.blobId;
  const isImpl = modal.dataset.isImpl === "1";
  const body = isImpl
    ? { blob_id: blobId, code: $("review-code-input").value }
    : { blob_id: blobId, answer: $("review-answer-input").value };
  $("review-output").textContent = "Grading...";
  const result = await api("/api/review-submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (result.error) {
    $("review-output").textContent = result.error;
    return;
  }
  const lines = [result.passed ? "PASSED" : "NOT QUITE"];
  if (result.output) lines.push(result.output);
  if (result.feedback) lines.push(result.feedback);
  $("review-output").textContent = lines.join("\n\n");
  await refreshContent();
};

$("synthesis-btn").onclick = async () => {
  const data = await api("/api/synthesis-challenge");
  if (data.error) {
    alert(data.error);
    return;
  }
  const modal = $("synthesis-modal");
  const isImpl = data.challenge.type === "implementation";
  $("synthesis-modal-concepts").textContent = `Combining: ${data.concepts.join(", ")}`;
  $("synthesis-modal-prompt").textContent = data.challenge.prompt;
  $("synthesis-code-input").classList.toggle("hidden", !isImpl);
  $("synthesis-answer-input").classList.toggle("hidden", isImpl);
  $("synthesis-code-input").value = isImpl ? data.challenge.starter_code || "" : "";
  $("synthesis-answer-input").value = "";
  $("synthesis-output").textContent = "";
  modal.dataset.challengeId = data.challenge_id;
  modal.dataset.isImpl = isImpl ? "1" : "";
  modal.classList.remove("hidden");
};

$("synthesis-close-btn").onclick = () => $("synthesis-modal").classList.add("hidden");

$("synthesis-submit-btn").onclick = async () => {
  const modal = $("synthesis-modal");
  const isImpl = modal.dataset.isImpl === "1";
  const body = isImpl
    ? { challenge_id: modal.dataset.challengeId, code: $("synthesis-code-input").value }
    : { challenge_id: modal.dataset.challengeId, answer: $("synthesis-answer-input").value };
  $("synthesis-output").textContent = "Grading...";
  const result = await api("/api/synthesis-submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (result.error) {
    $("synthesis-output").textContent = result.error;
    return;
  }
  const lines = [result.passed ? "PASSED" : "NOT QUITE"];
  if (result.output) lines.push(result.output);
  if (result.feedback) lines.push(result.feedback);
  $("synthesis-output").textContent = lines.join("\n\n");
};

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

enableCodeEditing("code-input");
enableCodeEditing("review-code-input");
enableCodeEditing("synthesis-code-input");

refreshContent();
checkReviewDue();
