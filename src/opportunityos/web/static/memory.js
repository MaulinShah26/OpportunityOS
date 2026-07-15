const preferenceLabels = {
  "recommendation:similar_profiles": "Opportunities similar to ones I marked worth pursuing",
  "recommendation:similar_opportunities": "Opportunities similar to ones I marked worth pursuing",
  "location:flexibility": "Location flexibility",
  "work_style:execution_only": "Execution-only work",
  "seniority:junior": "Junior-level roles",
  "engagement:presented_type": "The engagement type presented in the opportunity",
};

function memoryDisplayLabel(item) {
  if (item.category !== "preference") return item.key;
  if (preferenceLabels[item.key]) return preferenceLabels[item.key];
  const [namespace, rawValue] = item.key.split(":", 2);
  if (!rawValue) return humanise(item.key);
  const value = humanise(rawValue);
  if (namespace === "engagement") return `${value.charAt(0).toUpperCase()}${value.slice(1)} engagements`;
  if (namespace === "work_mode") return `${value.charAt(0).toUpperCase()}${value.slice(1)} work`;
  if (namespace === "industry") return `Industry: ${value}`;
  if (namespace === "location") return `Location: ${value}`;
  if (namespace === "seniority") return `Seniority: ${value}`;
  return `${humanise(namespace)} · ${value}`;
}

function memoryValueSummary(item) {
  const value = item.value || {};
  if (item.category === "capability") return `Proficiency ${Math.round((value.proficiency ?? item.confidence) * 100)}%`;
  if (item.category === "preference") return `Weight ${Math.round((value.weight ?? item.confidence) * 100)}%`;
  if (item.category === "constraint") {
    const accepted = (value.accepted_values || []).join(", ");
    const rejected = (value.rejected_values || []).join(", ");
    return `${humanise(value.kind || "constraint")}${accepted ? ` · accepts ${accepted}` : ""}${rejected ? ` · rejects ${rejected}` : ""}`;
  }
  if (item.category === "aspiration") return `Priority ${Math.round((value.weight ?? item.confidence) * 100)}%`;
  return value.name || JSON.stringify(value);
}

function renderMemory() {
  const content = $("#memory-content");
  if (!state.memory.length) {
    content.innerHTML = `<div class="empty-state"><h2>No memory items</h2><p>Onboard or load a profile to create structured personal memory.</p></div>`;
    return;
  }
  const grouped = Object.groupBy ? Object.groupBy(state.memory, (item) => item.category) : state.memory.reduce((acc, item) => {
    (acc[item.category] ||= []).push(item);
    return acc;
  }, {});
  content.innerHTML = Object.entries(grouped).map(([category, items]) => `
    <section class="memory-group">
      <div class="memory-group-heading"><h3>${escapeHtml(humanise(category))}</h3><span class="memory-count">${items.length} item${items.length === 1 ? "" : "s"}</span></div>
      <div class="memory-items">${items.map((item) => `
        <article class="memory-item">
          <div>
            <div class="memory-title-row">
              <h4>${escapeHtml(memoryDisplayLabel(item))}</h4>
              <span class="memory-pill ${escapeHtml(item.source)}">${escapeHtml(item.source)}</span>
              <span class="memory-pill ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span>
            </div>
            <p class="memory-value">${escapeHtml(memoryValueSummary(item))}</p>
            <div class="memory-confidence">Confidence ${Math.round(item.confidence * 100)}% · Updated ${escapeHtml(formatDate(item.updated_at))}</div>
          </div>
          <div class="memory-actions">
            ${item.active && item.status !== "confirmed" ? `<button class="button button-secondary button-small memory-action" data-action="confirm" data-id="${item.id}" type="button">Confirm</button>` : ""}
            ${item.active ? `<button class="button button-secondary button-small memory-edit" data-id="${item.id}" type="button">Edit</button>` : ""}
            ${item.active ? `<button class="button button-danger button-small memory-action" data-action="reject" data-id="${item.id}" type="button">Reject</button>` : ""}
            ${item.active ? `<button class="button button-ghost button-small memory-delete" data-id="${item.id}" type="button">Delete</button>` : ""}
          </div>
        </article>`).join("")}</div>
    </section>`).join("");
  $$(".memory-action", content).forEach((button) => button.addEventListener("click", () => mutateMemory(button.dataset.id, button.dataset.action, button)));
  $$(".memory-edit", content).forEach((button) => button.addEventListener("click", () => openMemoryEditor(button.dataset.id)));
  $$(".memory-delete", content).forEach((button) => button.addEventListener("click", () => deleteMemory(button.dataset.id, button)));
}

async function loadMemory() {
  if (!requireProfile()) return;
  const content = $("#memory-content");
  content.innerHTML = `<div class="loading">Loading personal memory…</div>`;
  try {
    const includeInactive = $("#include-inactive-toggle").checked;
    const response = await api(`/v1/users/${state.userId}/memory?include_inactive=${includeInactive}`);
    state.memory = response.items;
    renderMemory();
  } catch (error) {
    content.innerHTML = `<div class="blocked-outreach">${escapeHtml(error.message)}</div>`;
  }
}

async function mutateMemory(id, action, button) {
  setBusy(button, true, "Saving…");
  try {
    await api(`/v1/users/${state.userId}/memory/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, reason: `${humanise(action)} from the web interface` }),
    });
    await Promise.all([loadMemory(), loadProfile(state.userId, true)]);
    showNotice(action === "confirm" ? "Memory confirmed." : "Memory rejected.");
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

function openMemoryEditor(id) {
  const item = state.memory.find((candidate) => candidate.id === id);
  if (!item) return;
  $("#memory-edit-id").value = id;
  $("#memory-edit-key").value = item.key;
  $("#memory-edit-value").value = JSON.stringify(item.value, null, 2);
  $("#memory-edit-reason").value = "";
  $("#memory-dialog").showModal();
}

async function deleteMemory(id, button) {
  if (!window.confirm("Delete this memory item? It will remain visible in audit history.")) return;
  setBusy(button, true, "Deleting…");
  try {
    await api(`/v1/users/${state.userId}/memory/${id}`, { method: "DELETE" });
    await Promise.all([loadMemory(), loadProfile(state.userId, true)]);
    showNotice("Memory item deleted.");
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

async function loadAudit() {
  if (!requireProfile()) return;
  const content = $("#audit-content");
  content.innerHTML = `<div class="loading">Loading audit history…</div>`;
  try {
    const response = await api(`/v1/users/${state.userId}/memory-audit?limit=100`);
    state.audit = response.events;
    if (!state.audit.length) {
      content.innerHTML = `<div class="empty-state"><h2>No audit events</h2><p>Changes will appear here as the profile and memory evolve.</p></div>`;
      return;
    }
    content.innerHTML = state.audit.map((event) => `
      <article class="audit-item">
        <div class="audit-time">${escapeHtml(formatDate(event.created_at))}</div>
        <div class="audit-body">
          <strong>${escapeHtml(humanise(event.action))}</strong>
          <div class="audit-meta">Actor: ${escapeHtml(event.actor)}${event.memory_item_id ? ` · Memory ${escapeHtml(event.memory_item_id)}` : ""}</div>
          ${event.reason ? `<div class="audit-reason">${escapeHtml(event.reason)}</div>` : ""}
        </div>
      </article>`).join("");
  } catch (error) {
    content.innerHTML = `<div class="blocked-outreach">${escapeHtml(error.message)}</div>`;
  }
}
