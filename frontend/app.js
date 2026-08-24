const API_BASE = ""; // same origin as the Flask server

const state = {
  jobs: [],
  activeJobId: null,
  pendingFiles: [],
};

const el = {
  jobForm: document.getElementById("job-form"),
  jobTitle: document.getElementById("job-title"),
  jobDescription: document.getElementById("job-description"),
  jobPickerWrap: document.getElementById("job-picker-wrap"),
  jobPicker: document.getElementById("job-picker"),
  jobCount: document.getElementById("job-count"),

  uploadForm: document.getElementById("upload-form"),
  dropzone: document.getElementById("dropzone"),
  resumeInput: document.getElementById("resume-input"),
  fileList: document.getElementById("file-list"),
  uploadBtn: document.getElementById("upload-btn"),

  statusLine: document.getElementById("status-line"),
  resultsTitle: document.getElementById("results-title"),
  resultsSub: document.getElementById("results-sub"),
  emptyState: document.getElementById("empty-state"),
  candidateList: document.getElementById("candidate-list"),
  cardTemplate: document.getElementById("candidate-card-template"),
};

init();

async function init() {
  await refreshJobs();
  bindEvents();
}

function bindEvents() {
  el.jobForm.addEventListener("submit", onCreateJob);
  el.jobPicker.addEventListener("change", onSwitchJob);

  el.dropzone.addEventListener("click", () => el.resumeInput.click());
  el.dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    el.dropzone.classList.add("drag-over");
  });
  el.dropzone.addEventListener("dragleave", () => el.dropzone.classList.remove("drag-over"));
  el.dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    el.dropzone.classList.remove("drag-over");
    addFiles(e.dataTransfer.files);
  });
  el.resumeInput.addEventListener("change", (e) => addFiles(e.target.files));

  el.uploadForm.addEventListener("submit", onUploadResumes);
}

// ------------------------------- jobs ---------------------------------

async function refreshJobs() {
  const jobs = await api("GET", "/api/jobs");
  state.jobs = jobs;
  el.jobCount.textContent = jobs.length;

  if (jobs.length === 0) {
    el.jobPickerWrap.style.display = "none";
    return;
  }

  el.jobPickerWrap.style.display = "flex";
  el.jobPicker.innerHTML = jobs
    .map((j) => `<option value="${j.id}">${escapeHtml(j.title)}</option>`)
    .join("");

  if (!state.activeJobId || !jobs.some((j) => j.id === state.activeJobId)) {
    state.activeJobId = jobs[0].id;
  }
  el.jobPicker.value = state.activeJobId;
  onJobChanged();
}

async function onCreateJob(e) {
  e.preventDefault();
  const title = el.jobTitle.value.trim();
  const description = el.jobDescription.value.trim();
  if (!title || !description) return;

  setStatus("Opening requisition…");
  try {
    const job = await api("POST", "/api/jobs", { title, description });
    state.activeJobId = job.id;
    el.jobForm.reset();
    await refreshJobs();
    setStatus(`Requisition "${job.title}" is open. Upload resumes below.`, "success");
  } catch (err) {
    setStatus(err.message, "error");
  }
}

function onSwitchJob() {
  state.activeJobId = el.jobPicker.value;
  onJobChanged();
}

function onJobChanged() {
  const job = state.jobs.find((j) => j.id === state.activeJobId);
  if (!job) return;
  el.resultsTitle.textContent = job.title;
  el.resultsSub.textContent = "Ranked by fit — best match first.";
  renderFileList();
  loadCandidates();
}

// ------------------------------ uploads --------------------------------

function addFiles(fileListLike) {
  const incoming = Array.from(fileListLike);
  for (const f of incoming) {
    if (!state.pendingFiles.some((p) => p.name === f.name && p.size === f.size)) {
      state.pendingFiles.push(f);
    }
  }
  renderFileList();
}

function renderFileList() {
  el.fileList.innerHTML = "";
  state.pendingFiles.forEach((f, idx) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${escapeHtml(f.name)}</span><span class="remove" data-idx="${idx}">remove</span>`;
    li.querySelector(".remove").addEventListener("click", () => {
      state.pendingFiles.splice(idx, 1);
      renderFileList();
    });
    el.fileList.appendChild(li);
  });
  el.uploadBtn.disabled = state.pendingFiles.length === 0 || !state.activeJobId;
}

async function onUploadResumes(e) {
  e.preventDefault();
  if (!state.activeJobId) {
    setStatus("Open a requisition first.", "error");
    return;
  }
  if (state.pendingFiles.length === 0) return;

  const formData = new FormData();
  state.pendingFiles.forEach((f) => formData.append("resumes", f));

  el.uploadBtn.disabled = true;
  setStatus(`Screening ${state.pendingFiles.length} resume(s) against the job description…`);

  try {
    const res = await fetch(`${API_BASE}/api/jobs/${state.activeJobId}/resumes`, {
      method: "POST",
      body: formData,
    });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.error || "Upload failed.");

    const scored = payload.results.filter((r) => r.status === "scored").length;
    const failed = payload.results.filter((r) => r.status !== "scored");

    let msg = `Scored ${scored} of ${payload.results.length} resume(s).`;
    if (failed.length) {
      msg += "\n" + failed.map((f) => `⚠ ${f.filename}: ${f.reason}`).join("\n");
    }
    setStatus(msg, failed.length ? "error" : "success");

    state.pendingFiles = [];
    renderFileList();
    await loadCandidates();
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    el.uploadBtn.disabled = state.pendingFiles.length === 0;
  }
}

// ---------------------------- candidates -------------------------------

async function loadCandidates() {
  if (!state.activeJobId) return;
  const candidates = await api("GET", `/api/jobs/${state.activeJobId}/candidates`);
  renderCandidates(candidates);
}

function renderCandidates(candidates) {
  el.candidateList.innerHTML = "";
  el.emptyState.style.display = candidates.length ? "none" : "block";

  candidates.forEach((c) => {
    const node = el.cardTemplate.content.cloneNode(true);
    const li = node.querySelector(".dossier");

    node.querySelector(".dossier-name").textContent = c.candidate_name || "Unknown candidate";
    node.querySelector(".dossier-file").textContent = c.filename;
    node.querySelector(".dossier-justification").textContent = c.justification || "No justification returned.";
    node.querySelector(".dossier-experience").textContent = c.experience_summary || "—";
    node.querySelector(".dossier-education").textContent = c.education_summary || "—";

    const skillsEl = node.querySelector(".dossier-skills");
    (c.skills || []).forEach((s) => {
      const tag = document.createElement("li");
      tag.textContent = s;
      skillsEl.appendChild(tag);
    });

    const stamp = node.querySelector(".dossier-stamp");
    stamp.style.setProperty("--score-color", scoreColor(c.match_score));
    node.querySelector(".stamp-score").textContent = c.match_score ?? "–";

    node.querySelector(".dossier-remove").addEventListener("click", async () => {
      await api("DELETE", `/api/candidates/${c.id}`);
      loadCandidates();
    });

    el.candidateList.appendChild(node);
  });
}

function scoreColor(score) {
  if (score >= 8) return "#3c6b52"; // green
  if (score >= 5) return "#a9761f"; // amber
  return "#a13d2c"; // red
}

// ------------------------------- utils ----------------------------------

async function api(method, path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.error || `Request failed (${res.status})`);
  return payload;
}

function setStatus(message, kind) {
  el.statusLine.textContent = message;
  el.statusLine.className = "status-line" + (kind ? " " + kind : "");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
