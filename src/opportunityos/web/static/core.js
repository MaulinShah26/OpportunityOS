const state = {
  userId: localStorage.getItem("opportunityos.userId"),
  profile: null,
  analysis: null,
  memory: [],
  audit: [],
  evaluationDatasets: [],
  evaluationReport: null,
  evaluationShowHistory: false,
};

const viewCopy = {
  "profile-view": [
    "Build your personal opportunity model",
    "Upload a résumé or reconnect an existing profile. OpportunityOS stores structured memory, not the résumé file.",
  ],
  "analyse-view": [
    "Evaluate one real opportunity",
    "Use a role, consulting brief, founder post or company signal. The system will explain relevance instead of producing a generic match score.",
  ],
  "result-view": [
    "Make an evidence-backed decision",
    "Inspect the fit dimensions, evidence, hypotheses, guardrails and safe next action before pursuing anything.",
  ],
  "evaluation-view": [
    "Measure relevance quality repeatedly",
    "Freeze your explicit decisions into a stable benchmark and compare the same opportunities across mock, OpenAI and Claude runs.",
  ],
  "memory-view": [
    "Control what the system learns",
    "Review explicit and inferred memory. Confirm accurate beliefs, correct them or remove them before they influence future recommendations.",
  ],
  "audit-view": [
    "See how your personal model changed",
    "OpportunityOS records material memory changes so adaptation remains inspectable rather than opaque.",
  ],
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function humanise(value) {
  return String(value ?? "").replaceAll("_", " ").replaceAll(":", " · ");
}

function formatDate(value) {
  if (!value) return "Unknown time";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function showNotice(message, type = "success") {
  const notice = $("#notice");
  notice.textContent = message;
  notice.classList.toggle("is-error", type === "error");
  notice.classList.remove("is-hidden");
  window.clearTimeout(showNotice.timer);
  showNotice.timer = window.setTimeout(() => notice.classList.add("is-hidden"), 5500);
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get("content-type") || "";
  let body = null;
  if (response.status !== 204) {
    body = contentType.includes("application/json") ? await response.json() : await response.text();
  }
  if (!response.ok) {
    const detail = body?.detail || body?.message || body || `Request failed (${response.status})`;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : detail);
  }
  return body;
}

function setBusy(button, busy, label = "Working…") {
  if (!button) return;
  if (busy) {
    button.dataset.originalLabel = button.textContent;
    button.textContent = label;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalLabel || button.textContent;
    button.disabled = false;
  }
}

function activateView(viewId) {
  $$(".view-panel").forEach((view) => view.classList.toggle("is-active", view.id === viewId));
  $$(".nav-item").forEach((item) => item.classList.toggle("is-active", item.dataset.view === viewId));
  const [title, description] = viewCopy[viewId];
  $("#view-title").textContent = title;
  $("#view-description").textContent = description;
  if (viewId === "evaluation-view" && state.userId) loadEvaluationDatasets();
  if (viewId === "memory-view" && state.userId) loadMemory();
  if (viewId === "audit-view" && state.userId) loadAudit();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function requireProfile() {
  if (state.userId && state.profile) return true;
  showNotice("Create or load a profile before analysing an opportunity.", "error");
  activateView("profile-view");
  return false;
}

async function checkHealth() {
  try {
    const health = await api("/health");
    $("#health-dot").classList.add("is-healthy");
    const providers = health.llm_mode === "live" && health.providers ? ` · ${health.providers}` : "";
    $("#health-label").textContent = `API ready · ${health.llm_mode}${providers}`;
  } catch (error) {
    $("#health-dot").classList.add("is-error");
    $("#health-label").textContent = "API unavailable";
  }
}

function setActiveProfile(profile) {
  state.profile = profile;
  state.userId = profile.user_id;
  localStorage.setItem("opportunityos.userId", state.userId);
  $("#profile-id-input").value = state.userId;
  $("#active-user-label").textContent = `${profile.display_name} · ${state.userId}`;
  $("#change-profile-button").classList.remove("is-hidden");
  renderProfile(profile);
}

function commaSeparated(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function enrichOnboardedProfile(profile, formData) {
  const engagement = String(formData.get("preferred_engagement") || "").trim();
  const workMode = String(formData.get("work_mode") || "").trim();
  if (engagement) {
    profile.preferences.push({
      key: `engagement:${engagement}`,
      weight: 0.9,
      explicit: true,
      confidence: 1.0,
    });
  }
  if (workMode) {
    profile.preferences.push({
      key: `work_mode:${workMode}`,
      weight: 0.9,
      explicit: true,
      confidence: 1.0,
    });
  }
  commaSeparated(formData.get("aspirations")).forEach((name) => {
    profile.aspirations.push({ name, weight: 0.8 });
  });
  profile.target_problem_areas = [
    ...new Set([...(profile.target_problem_areas || []), ...commaSeparated(formData.get("problem_areas"))]),
  ];
  const exclusions = commaSeparated(formData.get("hard_exclusions"));
  if (exclusions.length) {
    profile.constraints.push({
      key: "onboarding exclusions",
      kind: "hard",
      accepted_values: [],
      rejected_values: exclusions,
      penalty: 1.0,
    });
  }
  return profile;
}

function clearProfile() {
  state.userId = null;
  state.profile = null;
  state.analysis = null;
  state.memory = [];
  state.audit = [];
  state.evaluationDatasets = [];
  state.evaluationReport = null;
  state.evaluationShowHistory = false;
  localStorage.removeItem("opportunityos.userId");
  $("#active-user-label").textContent = "No active profile";
  $("#change-profile-button").classList.add("is-hidden");
  $("#profile-summary").classList.add("is-hidden");
  $("#evaluation-datasets").innerHTML = "";
  $("#evaluation-report").classList.add("is-hidden");
  activateView("profile-view");
}

function renderProfile(profile) {
  const summary = $("#profile-summary");
  const tags = profile.capabilities.slice(0, 10).map((item) => `<span class="tag">${escapeHtml(item.name)}</span>`).join("");
  summary.innerHTML = `
    <div class="profile-overview">
      <div>
        <p class="section-kicker">Active profile</p>
        <h2>${escapeHtml(profile.display_name)}</h2>
        <p class="profile-meta">${escapeHtml(profile.headline)}</p>
        <div class="profile-id">${escapeHtml(profile.user_id)}</div>
        <div class="tag-list">${tags}</div>
      </div>
      <div class="profile-stats">
        <div><strong>${profile.capabilities.length}</strong><span>capabilities</span></div>
        <div><strong>${profile.preferences.length}</strong><span>preferences</span></div>
        <div><strong>${profile.constraints.length}</strong><span>constraints</span></div>
      </div>
    </div>`;
  summary.classList.remove("is-hidden");
}
