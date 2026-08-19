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

// KaTeX auto-render: scans an element's text nodes for these delimiters
// and replaces them with typeset math in place. throwOnError: false so a
// malformed/partial LaTeX snippet (in book text or a learner's answer)
// degrades to visible red error text instead of breaking the page.
const KATEX_OPTIONS = {
  delimiters: [
    { left: "$$", right: "$$", display: true },
    { left: "$", right: "$", display: false },
    { left: "\\(", right: "\\)", display: false },
    { left: "\\[", right: "\\]", display: true },
  ],
  throwOnError: false,
};

function renderMath(el) {
  if (window.renderMathInElement) window.renderMathInElement(el, KATEX_OPTIONS);
}

function renderReading(blob) {
  $("concept-title").textContent = blob.concept;
  $("reading-text").innerHTML = blob.reading_html || `<p>${blob.reading}</p>`;
  renderMath($("reading-text"));
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
  renderMath($("exercise-prompt"));

  const isImpl = ex.type === "implementation";
  $("impl-exercise").classList.toggle("hidden", !isImpl);
  $("short-answer-exercise").classList.toggle("hidden", isImpl);

  if (isImpl) {
    $("code-input").value = state.draft || ex.starter_code || "";
  } else {
    $("answer-reveal").classList.add("hidden");
    $("expected-answer").textContent = ex.expected_answer || "";
    renderMath($("expected-answer"));
  }

  if (state.status === "passed") $("next-row").classList.remove("hidden");
  $("skip-btn").classList.toggle("hidden", state.status === "passed");

  renderCheckpointNudge(state.status === "passed");
  renderExtraQuestionsNudge(state.status === "passed", blob);
}

// Optional, non-gating nudge shown alongside "Continue" once this blob is
// passed: if enough concepts have been passed overall, offer a synthesis
// challenge combining recent ones right here instead of only via the
// sidebar button - "between blobs" is where combining what you just
// learned with what came before is most natural, and skipping it (just
// clicking Continue) has no cost.
function renderCheckpointNudge(blobPassed) {
  const passedCount = orderedBlobs().filter(
    ({ blob }) => (PROGRESS.blobs[blob.id] || {}).status === "passed"
  ).length;
  const eligible = blobPassed && passedCount >= 2;
  $("checkpoint-nudge").classList.toggle("hidden", !eligible);
  if (eligible) {
    $("checkpoint-nudge-text").textContent = "Optional: try a synthesis challenge combining recent concepts";
    $("checkpoint-nudge-btn").onclick = openSynthesisChallenge;
  }
}

// Optional, non-gating extra (authored) questions for this blob, shown
// the same way as the synthesis nudge above - never required, never
// blocks Continue. Skipping or answering wrong still has an effect
// server-side (see apply_extra_question_result in server.py): it pulls
// this blob's next spaced review closer, and a wrong answer also
// records what was missed so a later review variant/synthesis
// challenge specifically re-probes it - none of that needs UI here,
// just showing each question's resolved status once it has one.
function renderExtraQuestionsNudge(blobPassed, blob) {
  const extras = blob.extra_questions || [];
  const container = $("extra-questions-list");
  container.innerHTML = "";
  const eligible = blobPassed && extras.length > 0;
  $("extra-questions-nudge").classList.toggle("hidden", !eligible);
  if (!eligible) return;

  const state = PROGRESS.blobs[blob.id] || {};
  const extraStatus = state.extra_status || {};
  extras.forEach((eq, i) => {
    const status = extraStatus[String(i)];
    const row = document.createElement("div");
    row.className = "extra-question-row";
    const label = document.createElement("span");
    label.textContent = status ? `Extra question ${i + 1}: ${status}` : `Extra question ${i + 1} (optional)`;
    row.appendChild(label);
    if (!status) {
      const tryBtn = document.createElement("button");
      tryBtn.textContent = "Try it";
      tryBtn.onclick = () => openExtraModal(blob, i);
      row.appendChild(tryBtn);
      const skipBtn = document.createElement("button");
      skipBtn.textContent = "Skip";
      skipBtn.onclick = () => skipExtraQuestion(blob.id, i);
      row.appendChild(skipBtn);
    }
    container.appendChild(row);
  });
}

function openExtraModal(blob, index) {
  const eq = blob.extra_questions[index];
  const isImpl = eq.type === "implementation";
  $("extra-modal-prompt").textContent = eq.prompt;
  renderMath($("extra-modal-prompt"));
  $("extra-code-input").classList.toggle("hidden", !isImpl);
  $("extra-answer-input").classList.toggle("hidden", isImpl);
  $("extra-code-input").value = isImpl ? eq.starter_code || "" : "";
  $("extra-answer-input").value = "";
  $("extra-output").innerHTML = "";
  const modal = $("extra-modal");
  modal.dataset.blobId = blob.id;
  modal.dataset.index = String(index);
  modal.dataset.isImpl = isImpl ? "1" : "";
  modal.classList.remove("hidden");
}

async function skipExtraQuestion(blobId, index) {
  await api("/api/extra-skip", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ blob_id: blobId, index }),
  });
  await refreshContent();
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
  // Re-check on every refresh, not just page load, so a review that
  // becomes due mid-session (e.g. right after passing a blob, or after a
  // failed synthesis challenge pulls one forward) shows up between blobs
  // instead of only on the next reload.
  checkReviewDue();
}

function openReviewModal(reviewBlob) {
  const ex = reviewBlob.exercise;
  const isImpl = ex.type === "implementation";
  $("review-modal-title").textContent = reviewBlob.concept;
  $("review-modal-badge").textContent = reviewBlob.is_variant
    ? "Fresh variant - different specifics, same concept"
    : "Original exercise (claude was unreachable, showing the stored version)";
  $("review-modal-prompt").textContent = ex.prompt;
  renderMath($("review-modal-prompt"));
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
  } else {
    $("review-banner").classList.add("hidden");
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
  // refreshContent() re-renders the exercise section (to pick up the new
  // pass/locked state, unlocked next blob, etc.) and that unconditionally
  // clears #run-output - so it must run BEFORE we write the result, or
  // the result flashes for a frame and is immediately wiped.
  await refreshContent();
  $("run-output").textContent = (result.passed ? "PASSED\n\n" : "FAILED\n\n") + result.output;
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
    renderMath(p);
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
  renderMath($("claude-review-output"));
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

// Unified renderer for any graded result: shows the learner's own
// submitted answer read back (rendered, so typed LaTeX shows typeset
// rather than raw source), then the verdict/pass-fail, any code output,
// and feedback - used by grade-answer, review-submit, and
// synthesis-submit so the three surfaces behave consistently.
function renderGradedResult(container, { answer, verdict, passed, output, feedback }) {
  container.innerHTML = "";
  if (answer) {
    const label = document.createElement("p");
    label.className = "answer-readback-label";
    label.textContent = "Your answer:";
    container.appendChild(label);
    const body = document.createElement("p");
    body.className = "answer-readback";
    body.textContent = answer;
    container.appendChild(body);
  }
  if (verdict) {
    const v = document.createElement("p");
    v.textContent = `Verdict: ${verdict}`;
    container.appendChild(v);
  } else if (typeof passed === "boolean") {
    const v = document.createElement("p");
    v.textContent = passed ? "PASSED" : "NOT QUITE";
    container.appendChild(v);
  }
  if (output) {
    const o = document.createElement("pre");
    o.textContent = output;
    container.appendChild(o);
  }
  if (feedback) {
    const f = document.createElement("p");
    f.textContent = feedback;
    container.appendChild(f);
  }
  renderMath(container);
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
  if (!result.final) {
    // not final yet (a "partial" verdict) - no progress was written
    // server-side, so refreshContent() isn't called here and it's safe to
    // render straight away.
    renderGradedResult($("grade-answer-output"), { answer, verdict: result.verdict, feedback: result.feedback });
    PENDING_FOLLOW_UP = { question: result.follow_up_question, originalAnswer: answer };
    $("follow-up-question").textContent = result.follow_up_question;
    renderMath($("follow-up-question"));
    $("follow-up-block").classList.remove("hidden");
  } else {
    // final - progress was written server-side, so refresh (which
    // re-renders the exercise section and clears #grade-answer-output)
    // BEFORE writing the result, same reasoning as run-btn above.
    await refreshContent();
    renderGradedResult($("grade-answer-output"), { answer, verdict: result.verdict, feedback: result.feedback });
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
  // Always final (bounded to one follow-up round) - refresh before
  // rendering, same reasoning as grade-answer-btn above.
  PENDING_FOLLOW_UP = null;
  await refreshContent();
  renderGradedResult($("grade-answer-output"), { answer: followUpAnswer, verdict: result.verdict, feedback: result.feedback });
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
  const answer = isImpl ? null : $("review-answer-input").value;
  const body = isImpl ? { blob_id: blobId, code: $("review-code-input").value } : { blob_id: blobId, answer };
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
  renderGradedResult($("review-output"), { answer, passed: result.passed, output: result.output, feedback: result.feedback });
  await refreshContent();
};

async function openSynthesisChallenge() {
  const data = await api("/api/synthesis-challenge");
  if (data.error) {
    alert(data.error);
    return;
  }
  const modal = $("synthesis-modal");
  const isImpl = data.challenge.type === "implementation";
  $("synthesis-modal-concepts").textContent = `Combining: ${data.concepts.join(", ")}`;
  $("synthesis-modal-prompt").textContent = data.challenge.prompt;
  renderMath($("synthesis-modal-prompt"));
  $("synthesis-code-input").classList.toggle("hidden", !isImpl);
  $("synthesis-answer-input").classList.toggle("hidden", isImpl);
  $("synthesis-code-input").value = isImpl ? data.challenge.starter_code || "" : "";
  $("synthesis-answer-input").value = "";
  $("synthesis-output").textContent = "";
  modal.dataset.challengeId = data.challenge_id;
  modal.dataset.isImpl = isImpl ? "1" : "";
  modal.classList.remove("hidden");
}

$("synthesis-btn").onclick = openSynthesisChallenge;

$("synthesis-close-btn").onclick = () => $("synthesis-modal").classList.add("hidden");

$("synthesis-submit-btn").onclick = async () => {
  const modal = $("synthesis-modal");
  const isImpl = modal.dataset.isImpl === "1";
  const answer = isImpl ? null : $("synthesis-answer-input").value;
  const body = isImpl
    ? { challenge_id: modal.dataset.challengeId, code: $("synthesis-code-input").value }
    : { challenge_id: modal.dataset.challengeId, answer };
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
  renderGradedResult($("synthesis-output"), { answer, passed: result.passed, output: result.output, feedback: result.feedback });
  // A failed synthesis pulls its component blobs' next review forward
  // (see nudge_review_date in server.py) - refresh so that shows up
  // in the review banner right away instead of only after a page reload.
  await refreshContent();
};

$("extra-close-btn").onclick = () => $("extra-modal").classList.add("hidden");

$("extra-submit-btn").onclick = async () => {
  const modal = $("extra-modal");
  const blobId = modal.dataset.blobId;
  const index = parseInt(modal.dataset.index, 10);
  const isImpl = modal.dataset.isImpl === "1";
  const answer = isImpl ? null : $("extra-answer-input").value;
  const body = isImpl
    ? { blob_id: blobId, index, code: $("extra-code-input").value }
    : { blob_id: blobId, index, answer };
  $("extra-output").textContent = "Grading...";
  const result = await api("/api/extra-submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (result.error) {
    $("extra-output").textContent = result.error;
    return;
  }
  renderGradedResult($("extra-output"), { answer, passed: result.passed, output: result.output, feedback: result.feedback });
  // A wrong answer nudges this blob's next review forward and records
  // what was missed (see apply_extra_question_result in server.py) -
  // refresh so the sidebar/review banner/nudge list reflect it now.
  await refreshContent();
};

$("extra-skip-btn").onclick = async () => {
  const modal = $("extra-modal");
  await skipExtraQuestion(modal.dataset.blobId, parseInt(modal.dataset.index, 10));
  modal.classList.add("hidden");
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
enableCodeEditing("extra-code-input");

refreshContent();
