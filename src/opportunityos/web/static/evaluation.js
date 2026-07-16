function percentage(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function decisionLabelHtml(labels) {
  return ["pursue", "hold", "reject"]
    .map((key) => `<span class="decision-badge decision-${key}">${key}: ${labels?.[key] || 0}</span>`)
    .join("");
}

function normalisedDatasetName(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function isGeneratedTitle(value) {
  const title = String(value || "").trim();
  return title === "General opportunity"
    || /^Opportunity at .+/i.test(title)
    || /^(Consulting|Fractional|Contract|Full Time|Advisory|Partnership) opportunity$/i.test(title);
}

function updateHistoryButton() {
  const button = $("#toggle-evaluation-history-button");
  if (!button) return;
  button.textContent = state.evaluationShowHistory ? "Show latest only" : "Show revision history";
}

function updateMergeButton() {
  const button = $("#merge-evaluation-datasets-button");
  if (!button) return;
  const selected = $$(".dataset-merge-select:checked");
  button.disabled = selected.length < 2;
  button.textContent = selected.length < 2
    ? "Select snapshots to combine"
    : `Combine ${selected.length} selected snapshots`;
}

function renderEvaluationDatasets() {
  const target = $("#evaluation-datasets");
  updateHistoryButton();
  if (!state.evaluationDatasets.length) {
    target.innerHTML = `<article class="card evaluation-empty"><p class="section-kicker">No frozen dataset</p><h2>Label real opportunities first</h2><p class="memory-value">Analyse opportunities and record Worth pursuing, Save signal, or Not relevant.</p></article>`;
    return;
  }

  const latestRevisionByName = {};
  state.evaluationDatasets.forEach((dataset) => {
    const key = normalisedDatasetName(dataset.name);
    latestRevisionByName[key] = Math.max(latestRevisionByName[key] || 0, dataset.revision || 1);
  });

  const historyControls = state.evaluationShowHistory
    ? `<article class="card evaluation-lineage-controls">
        <div class="card-heading">
          <div>
            <p class="section-kicker">Revision history</p>
            <h2>Combine split benchmark snapshots</h2>
            <p class="memory-value">Older snapshots remain available for auditability. Select same-name snapshots only when they need to be combined into a new immutable revision.</p>
          </div>
          <button id="merge-evaluation-datasets-button" class="button button-secondary" type="button" disabled>Select snapshots to combine</button>
        </div>
      </article>`
    : "";

  target.innerHTML = `${historyControls}${state.evaluationDatasets.map((dataset) => {
    const revision = dataset.revision || 1;
    const isLatest = revision === latestRevisionByName[normalisedDatasetName(dataset.name)];
    const lineage = (dataset.parent_dataset_ids || []).length
      ? ` · derived from ${(dataset.parent_dataset_ids || []).length} snapshot${dataset.parent_dataset_ids.length === 1 ? "" : "s"}`
      : "";
    const snapshotSelector = state.evaluationShowHistory
      ? `<label class="toggle-label dataset-merge-label"><input class="dataset-merge-select" data-dataset-id="${escapeHtml(dataset.dataset_id)}" data-dataset-name="${escapeHtml(dataset.name)}" type="checkbox"> Select snapshot</label>`
      : "";
    const correctionButton = isLatest
      ? `<button class="button button-secondary evaluation-correct-button" data-dataset-id="${escapeHtml(dataset.dataset_id)}" data-dataset-name="${escapeHtml(dataset.name)}" data-dataset-revision="${revision}" type="button">Correct benchmark labels</button>`
      : "";
    return `
      <article class="card evaluation-dataset-card" data-dataset-id="${escapeHtml(dataset.dataset_id)}" data-dataset-name="${escapeHtml(dataset.name)}">
        <div class="card-heading">
          <div>
            <p class="section-kicker">Frozen dataset · revision ${revision}${isLatest ? " · latest" : ""}</p>
            <h2>${escapeHtml(dataset.name)}</h2>
            <p class="memory-value">Created ${escapeHtml(formatDate(dataset.created_at))} · ${dataset.case_count} cases · ${dataset.extraction_label_count || 0} extraction-labelled${lineage}</p>
          </div>
          <span class="${dataset.ready_for_comparison ? "privacy-badge" : "selective-badge"}">${dataset.ready_for_comparison ? "Comparison ready" : "Directional sample"}</span>
        </div>
        <div class="decision-row evaluation-labels">${decisionLabelHtml(dataset.decision_labels)}</div>
        <div class="feedback-actions">
          <button class="button button-primary evaluation-run-button" data-dataset-id="${escapeHtml(dataset.dataset_id)}" type="button">Run current mode</button>
          <button class="button button-secondary evaluation-extend-button" data-dataset-id="${escapeHtml(dataset.dataset_id)}" data-dataset-name="${escapeHtml(dataset.name)}" type="button">Extend with new cases</button>
          ${correctionButton}
          ${snapshotSelector}
        </div>
      </article>`;
  }).join("")}`;

  $$(".evaluation-run-button", target).forEach((button) => {
    button.addEventListener("click", () => runEvaluation(button.dataset.datasetId, button));
  });
  $$(".evaluation-extend-button", target).forEach((button) => {
    button.addEventListener("click", () => startDatasetExtension(button.dataset.datasetId, button.dataset.datasetName, button));
  });
  $$(".evaluation-correct-button", target).forEach((button) => {
    button.addEventListener("click", () => startDatasetCorrection(
      button.dataset.datasetId,
      button.dataset.datasetName,
      button.dataset.datasetRevision,
      button,
    ));
  });
  $$(".dataset-merge-select", target).forEach((input) => input.addEventListener("change", updateMergeButton));
  $("#merge-evaluation-datasets-button")?.addEventListener("click", mergeSelectedDatasets);
}

async function loadEvaluationDatasets() {
  if (!state.userId) return;
  const target = $("#evaluation-datasets");
  target.innerHTML = `<div class="loading">Loading frozen datasets…</div>`;
  try {
    const path = state.evaluationShowHistory
      ? `/v1/users/${state.userId}/evaluation-datasets/history`
      : `/v1/users/${state.userId}/evaluation-datasets/latest`;
    const response = await api(path);
    state.evaluationDatasets = response.datasets || [];
    renderEvaluationDatasets();
  } catch (error) {
    target.innerHTML = `<div class="blocked-outreach"><strong>Evaluation unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
  }
}

function splitLabels(value) {
  return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
}

function candidateEditorHtml(candidate) {
  const item = candidate.current_extraction || {};
  const remote = item.remote_allowed === true ? "true" : item.remote_allowed === false ? "false" : "";
  const placeholderTitle = isGeneratedTitle(item.title);
  const titleWarning = placeholderTitle
    ? `<div class="issue-card warning"><p><strong>This looks like a generated placeholder title.</strong> Replace it with the real role or opportunity title. When the source genuinely has no title, explicitly confirm that below.</p><label class="toggle-label"><input data-field="accept_placeholder_title" type="checkbox"> The source genuinely has no explicit role title</label></div>`
    : "";
  return `
    <article class="card extraction-candidate" data-analysis-id="${escapeHtml(candidate.source_analysis_id)}">
      <div class="card-heading">
        <div>
          <p class="section-kicker">Expected ${escapeHtml(candidate.expected_decision)}</p>
          <h3>${escapeHtml(candidate.name)}</h3>
        </div>
        <label class="toggle-label"><input data-field="selected" type="checkbox" checked> Include in this revision</label>
      </div>
      <div class="issue-card info"><p>Confirm these values against the original source. The benchmark measures the labels you approve, so do not leave an incorrect prefilled value unchanged.</p></div>
      ${titleWarning}
      <div class="two-column-fields">
        <label><span>Expected company</span><input data-field="company_name" value="${escapeHtml(item.company_name || "")}"></label>
        <label><span>Expected title</span><input data-field="title" value="${escapeHtml(item.title || "")}"></label>
        <label><span>Opportunity type</span><select data-field="opportunity_type">${["", "consulting", "fractional", "contract", "full_time", "advisory", "partnership", "unknown"].map((value) => `<option value="${value}" ${value === (item.opportunity_type || "") ? "selected" : ""}>${value ? humanise(value) : "Not labelled"}</option>`).join("")}</select></label>
        <label><span>Remote allowed</span><select data-field="remote_allowed"><option value="" ${remote === "" ? "selected" : ""}>Not labelled</option><option value="true" ${remote === "true" ? "selected" : ""}>Yes</option><option value="false" ${remote === "false" ? "selected" : ""}>No</option></select></label>
      </div>
      <label><span>Expected location <small>leave blank when not stated</small></span><input data-field="location" value="${escapeHtml(item.location || "")}"></label>
      <label><span>Required skills <small>comma-separated</small></span><input data-field="required_skills" value="${escapeHtml((item.required_skills || []).join(", "))}"></label>
      <label><span>Problem areas <small>comma-separated</small></span><input data-field="problem_areas" value="${escapeHtml((item.problem_areas || []).join(", "))}"></label>
      <label><span>Responsibilities or workflows <small>comma-separated</small></span><input data-field="responsibilities" value="${escapeHtml((item.responsibilities || []).join(", "))}"></label>
    </article>`;
}

function setDatasetBuildMode(datasetId = null, datasetName = "") {
  state.evaluationBaseDatasetId = datasetId;
  const form = $("#evaluation-dataset-form");
  const input = $("input[name='name']", form);
  const submit = $("button[type='submit']", form);
  let mode = $("#evaluation-build-mode");
  if (!mode) {
    mode = document.createElement("div");
    mode.id = "evaluation-build-mode";
    form.prepend(mode);
  }

  if (datasetId) {
    input.value = datasetName;
    input.readOnly = true;
    submit.textContent = "Create extended revision";
    mode.innerHTML = `<div class="issue-card info"><p><strong>Extending ${escapeHtml(datasetName)}</strong></p><p>The selected frozen snapshot will be preserved. New reviewed cases will be added into a new immutable revision.</p><button id="cancel-dataset-extension" class="button button-small button-ghost" type="button">Cancel extension</button></div>`;
    $("#cancel-dataset-extension").addEventListener("click", () => setDatasetBuildMode());
  } else {
    input.readOnly = false;
    submit.textContent = "Create frozen dataset";
    mode.innerHTML = `<div class="explanation-box"><strong>New benchmark series</strong><p>Use a new unique name. To add cases to an existing benchmark, select Extend on that snapshot.</p></div>`;
  }
}

async function loadEvaluationCandidates(button) {
  setBusy(button, true, "Loading cases…");
  try {
    const response = await api(`/v1/users/${state.userId}/evaluation-candidates`);
    const allCandidates = response.candidates || [];
    const newCandidates = allCandidates.filter((item) => !item.previously_frozen);
    const priorCount = allCandidates.length - newCandidates.length;
    state.evaluationCandidates = newCandidates;
    let target = $("#evaluation-candidate-editor");
    if (!target) {
      target = document.createElement("div");
      target.id = "evaluation-candidate-editor";
      target.className = "evaluation-layout";
      $("#evaluation-dataset-form").after(target);
    }
    const exclusionNote = priorCount
      ? `<div class="issue-card info"><p>${priorCount} case${priorCount === 1 ? " was" : "s were"} excluded because they already belong to a frozen snapshot.</p></div>`
      : "";
    target.innerHTML = newCandidates.length
      ? `${exclusionNote}<div class="issue-card warning"><p>Review each extraction label before freezing. Existing snapshots remain immutable; this operation creates a new revision.</p></div>${newCandidates.map(candidateEditorHtml).join("")}`
      : `${exclusionNote}<div class="blocked-outreach"><strong>No new decided opportunities</strong><p>Analyse and explicitly decide new opportunities before creating or extending a benchmark.</p></div>`;
    showNotice(`${newCandidates.length} new cases loaded; ${priorCount} frozen cases excluded.`);
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

async function startDatasetExtension(datasetId, datasetName, button) {
  closeDatasetCorrection();
  setDatasetBuildMode(datasetId, datasetName);
  $("#evaluation-dataset-form").scrollIntoView({ behavior: "smooth", block: "start" });
  await loadEvaluationCandidates(button);
}

function hasUnresolvedPlaceholderTitle() {
  return $$(".extraction-candidate")
    .filter((card) => $("[data-field='selected']", card)?.checked)
    .some((card) => {
      const title = $("[data-field='title']", card)?.value || "";
      const accepted = $("[data-field='accept_placeholder_title']", card)?.checked || false;
      return isGeneratedTitle(title) && !accepted;
    });
}

function collectExtractionLabels() {
  return $$(".extraction-candidate")
    .filter((card) => $("[data-field='selected']", card)?.checked)
    .map((card) => {
      const value = (field) => $(`[data-field='${field}']`, card)?.value || "";
      const remote = value("remote_allowed");
      return {
        source_analysis_id: card.dataset.analysisId,
        expected: {
          company_name: value("company_name").trim() || null,
          title: value("title").trim() || null,
          opportunity_type: value("opportunity_type") || null,
          location: value("location").trim() || null,
          remote_allowed: remote === "" ? null : remote === "true",
          required_skills: splitLabels(value("required_skills")),
          problem_areas: splitLabels(value("problem_areas")),
          responsibilities: splitLabels(value("responsibilities")),
        },
      };
    });
}

function sourcePanelHtml(opportunity) {
  const sourceUrl = opportunity.source_url
    ? `<p><strong>Public URL:</strong> ${escapeHtml(opportunity.source_url)}</p>`
    : "";
  const hints = [
    opportunity.company_hint ? `<p><strong>Company input:</strong> ${escapeHtml(opportunity.company_hint)}</p>` : "",
    opportunity.role_hint ? `<p><strong>Role input:</strong> ${escapeHtml(opportunity.role_hint)}</p>` : "",
  ].join("");
  const sourceText = opportunity.raw_text
    ? `<pre class="benchmark-source-text">${escapeHtml(opportunity.raw_text)}</pre>`
    : `<p class="memory-value">No pasted source text was stored for this case.</p>`;
  return `<div class="benchmark-source-panel"><p class="section-kicker">Original frozen source</p>${hints}${sourceUrl}${sourceText}</div>`;
}

function correctionEditorHtml(caseItem) {
  const remote = caseItem.expected_remote_allowed === true
    ? "true"
    : caseItem.expected_remote_allowed === false ? "false" : "";
  const placeholderTitle = isGeneratedTitle(caseItem.expected_title);
  const warning = placeholderTitle
    ? `<div class="issue-card warning"><p><strong>The current expected title is a generated placeholder.</strong> Replace it with the title supported by the source, or explicitly confirm that no title exists.</p><label class="toggle-label"><input data-field="accept_placeholder_title" type="checkbox"> The original source genuinely has no explicit title</label></div>`
    : "";
  return `
    <article class="card benchmark-correction-case" data-case-id="${escapeHtml(caseItem.case_id)}">
      <div class="card-heading">
        <div>
          <p class="section-kicker">Correct frozen labels</p>
          <h3>${escapeHtml(caseItem.name)}</h3>
        </div>
        <label class="toggle-label"><input data-field="reviewed" type="checkbox"> Reviewed against source</label>
      </div>
      <div class="benchmark-correction-grid">
        ${sourcePanelHtml(caseItem.opportunity || {})}
        <div class="benchmark-label-panel">
          ${warning}
          <label><span>Expected decision</span><select data-field="expected_decision">${["pursue", "hold", "reject"].map((value) => `<option value="${value}" ${value === caseItem.expected_decision ? "selected" : ""}>${humanise(value)}</option>`).join("")}</select></label>
          <div class="two-column-fields">
            <label><span>Expected company</span><input data-field="company_name" value="${escapeHtml(caseItem.expected_company_name || "")}"></label>
            <label><span>Expected role / title</span><input data-field="title" value="${escapeHtml(caseItem.expected_title || "")}"></label>
            <label><span>Opportunity type</span><select data-field="opportunity_type">${["", "consulting", "fractional", "contract", "full_time", "advisory", "partnership", "unknown"].map((value) => `<option value="${value}" ${value === (caseItem.expected_opportunity_type || "") ? "selected" : ""}>${value ? humanise(value) : "Not labelled"}</option>`).join("")}</select></label>
            <label><span>Remote allowed</span><select data-field="remote_allowed"><option value="" ${remote === "" ? "selected" : ""}>Not labelled</option><option value="true" ${remote === "true" ? "selected" : ""}>Yes</option><option value="false" ${remote === "false" ? "selected" : ""}>No</option></select></label>
          </div>
          <label><span>Expected location</span><input data-field="location" value="${escapeHtml(caseItem.expected_location || "")}"></label>
          <label><span>Required skills <small>comma-separated</small></span><input data-field="required_skills" value="${escapeHtml((caseItem.expected_required_skills || []).join(", "))}"></label>
          <label><span>Problem areas <small>comma-separated</small></span><input data-field="problem_areas" value="${escapeHtml((caseItem.expected_problem_areas || []).join(", "))}"></label>
          <label><span>Responsibilities or workflows <small>comma-separated</small></span><input data-field="responsibilities" value="${escapeHtml((caseItem.expected_responsibilities || []).join(", "))}"></label>
        </div>
      </div>
    </article>`;
}

function closeDatasetCorrection() {
  $("#evaluation-correction-editor")?.remove();
  state.evaluationCorrectionDatasetId = null;
}

async function startDatasetCorrection(datasetId, datasetName, revision, button) {
  setBusy(button, true, "Loading frozen cases…");
  try {
    const dataset = await api(`/v1/users/${state.userId}/evaluation-datasets/${datasetId}`);
    closeDatasetCorrection();
    $("#evaluation-candidate-editor")?.remove();
    setDatasetBuildMode();
    state.evaluationCorrectionDatasetId = datasetId;
    const editor = document.createElement("section");
    editor.id = "evaluation-correction-editor";
    editor.className = "evaluation-layout";
    editor.innerHTML = `
      <article class="card">
        <div class="card-heading">
          <div>
            <p class="section-kicker">Immutable label correction</p>
            <h2>Correct ${escapeHtml(datasetName)} revision ${escapeHtml(revision)}</h2>
            <p class="memory-value">Review every frozen case against its original source. The existing revision and its benchmark runs remain unchanged; saving creates revision ${(dataset.revision || Number(revision) || 1) + 1}.</p>
          </div>
          <button id="cancel-dataset-correction" class="button button-ghost" type="button">Cancel</button>
        </div>
        <label><span>Correction reason</span><textarea id="benchmark-correction-reason" rows="3" minlength="5" maxlength="1000" placeholder="Example: Replaced generated placeholder titles and corrected expected opportunity types." required></textarea></label>
        <div class="issue-card warning"><p>This action corrects human benchmark labels only. It does not rerun extraction, update learned memory, or alter the original opportunities.</p></div>
      </article>
      ${dataset.cases.map(correctionEditorHtml).join("")}
      <article class="card benchmark-correction-submit">
        <p class="memory-value">All ${dataset.cases.length} cases must be marked reviewed. At least one frozen label must change.</p>
        <button id="submit-dataset-correction" class="button button-primary" type="button">Create corrected revision</button>
      </article>`;
    $("#evaluation-datasets").after(editor);
    $("#cancel-dataset-correction").addEventListener("click", closeDatasetCorrection);
    $("#submit-dataset-correction").addEventListener("click", submitDatasetCorrection);
    editor.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

function correctionHasUnresolvedPlaceholderTitle() {
  return $$(".benchmark-correction-case").some((card) => {
    const title = $("[data-field='title']", card)?.value || "";
    const accepted = $("[data-field='accept_placeholder_title']", card)?.checked || false;
    return isGeneratedTitle(title) && !accepted;
  });
}

function collectBenchmarkCorrections() {
  return $$(".benchmark-correction-case").map((card) => {
    const value = (field) => $(`[data-field='${field}']`, card)?.value || "";
    const remote = value("remote_allowed");
    return {
      case_id: card.dataset.caseId,
      expected_decision: value("expected_decision"),
      expected: {
        company_name: value("company_name").trim() || null,
        title: value("title").trim() || null,
        opportunity_type: value("opportunity_type") || null,
        location: value("location").trim() || null,
        remote_allowed: remote === "" ? null : remote === "true",
        required_skills: splitLabels(value("required_skills")),
        problem_areas: splitLabels(value("problem_areas")),
        responsibilities: splitLabels(value("responsibilities")),
      },
    };
  });
}

async function submitDatasetCorrection() {
  const button = $("#submit-dataset-correction");
  const cards = $$(".benchmark-correction-case");
  const reviewed = cards.filter((card) => $("[data-field='reviewed']", card)?.checked);
  if (reviewed.length !== cards.length) {
    showNotice(`Review every case before saving. ${cards.length - reviewed.length} case(s) are still unchecked.`, "error");
    return;
  }
  if (correctionHasUnresolvedPlaceholderTitle()) {
    showNotice("Replace generated placeholder titles, or explicitly confirm that the original source has no title.", "error");
    return;
  }
  const reason = String($("#benchmark-correction-reason")?.value || "").trim();
  if (reason.length < 5) {
    showNotice("Enter a correction reason of at least five characters.", "error");
    return;
  }
  setBusy(button, true, "Creating corrected revision…");
  try {
    const dataset = await api(
      `/v1/users/${state.userId}/evaluation-datasets/${state.evaluationCorrectionDatasetId}/correct`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason, corrections: collectBenchmarkCorrections() }),
      },
    );
    closeDatasetCorrection();
    state.evaluationShowHistory = false;
    showNotice(`Created corrected ${dataset.name} revision ${dataset.revision}. The previous revision remains in history.`);
    await loadEvaluationDatasets();
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

async function mergeSelectedDatasets() {
  const button = $("#merge-evaluation-datasets-button");
  const selected = $$(".dataset-merge-select:checked");
  if (selected.length < 2) return;
  const names = [...new Set(selected.map((input) => normalisedDatasetName(input.dataset.datasetName)))];
  if (names.length !== 1) {
    showNotice("Select snapshots with the same benchmark name.", "error");
    return;
  }
  setBusy(button, true, "Combining snapshots…");
  try {
    const dataset = await api(`/v1/users/${state.userId}/evaluation-datasets/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_dataset_ids: selected.map((input) => input.dataset.datasetId) }),
    });
    state.evaluationShowHistory = false;
    showNotice(`Created ${dataset.name} revision ${dataset.revision} with ${dataset.cases.length} distinct cases. Earlier revisions moved into history.`);
    await loadEvaluationDatasets();
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

function signedScore(value) {
  const numeric = Number(value || 0);
  return `${numeric >= 0 ? "+" : ""}${numeric}`;
}

function extractionChecksHtml(item) {
  const checks = Object.entries(item.extraction_field_results || {});
  if (!checks.length) return `<p>Extraction was not labelled for this frozen case.</p>`;
  return `<div class="diagnostic-grid">${checks.map(([field, passed]) => `<div class="diagnostic-row"><span>${escapeHtml(humanise(field))}</span><strong>${passed ? "match" : "mismatch"}</strong></div>`).join("")}</div>`;
}

function fitDiagnosticsHtml(item) {
  const contributions = Object.entries(item.fit_contributions || {})
    .sort((a, b) => b[1] - a[1])
    .map(([name, contribution]) => `<div class="diagnostic-row"><span>${escapeHtml(humanise(name))}</span><strong>${Number(contribution).toFixed(1)} points</strong></div>`)
    .join("");
  const gates = item.decision_gates || [];
  return `<details class="evaluation-diagnostics"><summary>Why this score and decision?</summary><div class="diagnostic-grid"><div class="diagnostic-row"><span>Extraction confidence</span><strong>${percentage(item.extraction_confidence)}</strong></div><div class="diagnostic-row"><span>Margin above HOLD threshold</span><strong>${signedScore(item.distance_to_hold_threshold)}</strong></div><div class="diagnostic-row"><span>Margin above PURSUE threshold</span><strong>${signedScore(item.distance_to_pursue_threshold)}</strong></div>${contributions}</div>${gates.length ? `<div class="issue-card warning"><p><strong>Decision gate:</strong> ${gates.map((code) => escapeHtml(humanise(code))).join(", ")}</p></div>` : `<p>Decision gates: none</p>`}<h4>Extraction checks</h4>${extractionChecksHtml(item)}</details>`;
}

function caseResultHtml(item) {
  if (item.error_type) return `<div class="evaluation-case is-error"><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.error_type)}: ${escapeHtml(item.error_message)}</p></div>`;
  const predicted = item.predicted_decision || "unknown";
  const company = item.extracted_company_name || item.analysis?.opportunity?.company_name || "Unknown company";
  const title = item.extracted_title || item.analysis?.opportunity?.title || item.name;
  const opportunityType = item.extracted_opportunity_type || item.analysis?.opportunity?.opportunity_type;
  const extractionLabel = item.extraction_case_correct == null ? "not labelled" : item.extraction_case_correct ? "fully correct" : "has mismatches";
  return `<div class="evaluation-case ${item.correct ? "is-correct" : "is-mismatch"}"><div><strong>${escapeHtml(`${company} — ${title}`)}</strong><p>Expected ${escapeHtml(item.expected_decision)} · predicted ${escapeHtml(predicted)} · fit ${item.fit_score}${opportunityType ? ` · ${escapeHtml(humanise(opportunityType))}` : ""}</p><p>${item.extraction_checks_passed}/${item.extraction_checks} extraction checks passed · ${escapeHtml(extractionLabel)} · critic ${item.critic_passed ? "passed" : "flagged"}</p>${fitDiagnosticsHtml(item)}</div><span class="decision-badge decision-${escapeHtml(predicted)}">${item.correct ? "match" : "mismatch"}</span></div>`;
}

function predictionPatternHtml(metrics) {
  return `<article class="card evaluation-diagnostic-card"><p class="section-kicker">Decision pattern</p><h2>Is the system too aggressive or too conservative?</h2><div class="evaluation-metrics compact-metrics"><div class="stat-box"><strong>${metrics.prediction_labels?.pursue || 0}</strong><span>predicted pursue</span></div><div class="stat-box"><strong>${metrics.prediction_labels?.hold || 0}</strong><span>predicted hold</span></div><div class="stat-box"><strong>${metrics.prediction_labels?.reject || 0}</strong><span>predicted reject</span></div><div class="stat-box"><strong>${percentage(metrics.underprediction_rate)}</strong><span>underprediction</span></div><div class="stat-box"><strong>${percentage(metrics.overprediction_rate)}</strong><span>overprediction</span></div><div class="stat-box"><strong>${metrics.gated_case_count || 0}</strong><span>gated cases</span></div></div></article>`;
}

function thresholdSimulationHtml(report) {
  const policy = report.decision_policy || { hold_threshold: 45, pursue_threshold: 72 };
  const simulation = report.threshold_simulation;
  if (!simulation) return `<article class="card evaluation-diagnostic-card"><p class="section-kicker">Threshold calibration</p><h2>No better safe threshold candidate yet</h2><p class="memory-value">Current policy: HOLD at ${policy.hold_threshold}, PURSUE at ${policy.pursue_threshold}.</p></article>`;
  return `<article class="card evaluation-diagnostic-card"><p class="section-kicker">Exploratory threshold simulation</p><h2>A candidate policy fits this frozen sample better</h2><div class="threshold-comparison"><div><span>Current</span><strong>HOLD ${policy.hold_threshold} · PURSUE ${policy.pursue_threshold}</strong></div><div><span>Simulated</span><strong>HOLD ${simulation.hold_threshold} · PURSUE ${simulation.pursue_threshold}</strong><small>${percentage(simulation.decision_accuracy)} accuracy</small></div></div></article>`;
}

function extractionFieldSummaryHtml(metrics) {
  const fields = Object.entries(metrics.extraction_accuracy_by_field || {});
  if (!fields.length) return "";
  return `<article class="card evaluation-diagnostic-card"><p class="section-kicker">Extraction fidelity</p><h2>Accuracy by reviewed field</h2><div class="diagnostic-grid">${fields.map(([field, value]) => `<div class="diagnostic-row"><span>${escapeHtml(humanise(field))}</span><strong>${percentage(value)}</strong></div>`).join("")}</div></article>`;
}

function downloadEvaluationReport() {
  if (!state.evaluationReport) return;
  const blob = new Blob([JSON.stringify(state.evaluationReport, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `opportunityos-evaluation-${state.evaluationReport.run_id}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function renderEvaluationReport(report) {
  state.evaluationReport = report;
  const target = $("#evaluation-report");
  const metrics = report.metrics;
  const extractionValue = metrics.extraction_accuracy == null ? "Not labelled" : percentage(metrics.extraction_accuracy);
  const extractionCaseValue = metrics.extraction_case_accuracy == null ? "Not labelled" : percentage(metrics.extraction_case_accuracy);
  target.innerHTML = `<article class="card evaluation-report-hero"><div class="card-heading"><div><p class="section-kicker">Latest benchmark run</p><h2>${escapeHtml(report.dataset_name)}</h2><p class="memory-value">Mode ${escapeHtml(report.mode)} · completed ${escapeHtml(formatDate(report.completed_at))}</p></div><button id="download-evaluation-report" class="button button-secondary" type="button">Download JSON</button></div><div class="evaluation-metrics"><div class="stat-box"><strong>${percentage(metrics.decision_accuracy)}</strong><span>decision accuracy</span></div><div class="stat-box"><strong>${extractionValue}</strong><span>extraction field accuracy</span></div><div class="stat-box"><strong>${extractionCaseValue}</strong><span>fully correct cases</span></div><div class="stat-box"><strong>${percentage(metrics.false_pursue_rate)}</strong><span>false pursue</span></div><div class="stat-box"><strong>${metrics.extraction_labelled_case_count}/${metrics.case_count}</strong><span>extraction-labelled</span></div><div class="stat-box"><strong>${metrics.total_model_calls}</strong><span>model calls</span></div></div></article>${predictionPatternHtml(metrics)}${extractionFieldSummaryHtml(metrics)}${thresholdSimulationHtml(report)}<article class="card"><p class="section-kicker">Case-by-case comparison</p><h2>Decision and extraction results</h2><div class="evaluation-cases">${report.cases.map(caseResultHtml).join("")}</div></article>`;
  target.classList.remove("is-hidden");
  $("#download-evaluation-report").addEventListener("click", downloadEvaluationReport);
  target.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runEvaluation(datasetId, button) {
  setBusy(button, true, "Running benchmark…");
  try {
    const report = await api(`/v1/users/${state.userId}/evaluation-datasets/${datasetId}/runs`, { method: "POST" });
    renderEvaluationReport(report);
    showNotice(`Evaluation completed: ${percentage(report.metrics.decision_accuracy)} decision accuracy.`);
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

function bindEvaluationEvents() {
  $("#refresh-evaluations-button").addEventListener("click", loadEvaluationDatasets);
  $("#toggle-evaluation-history-button").addEventListener("click", async () => {
    state.evaluationShowHistory = !state.evaluationShowHistory;
    closeDatasetCorrection();
    await loadEvaluationDatasets();
  });
  const form = $("#evaluation-dataset-form");
  setDatasetBuildMode();
  const reviewButton = document.createElement("button");
  reviewButton.className = "button button-secondary";
  reviewButton.type = "button";
  reviewButton.textContent = "Review new extraction labels";
  form.insertBefore(reviewButton, $("button[type='submit']", form));
  reviewButton.addEventListener("click", () => loadEvaluationCandidates(reviewButton));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!requireProfile()) return;
    if (!$("#evaluation-candidate-editor")) {
      showNotice("Review new extraction labels before creating or extending a benchmark.", "error");
      return;
    }
    if (hasUnresolvedPlaceholderTitle()) {
      showNotice("Replace generated placeholder titles, or explicitly confirm that the source has no role title.", "error");
      return;
    }
    const labels = collectExtractionLabels();
    if (!labels.length) {
      showNotice("Select at least one new reviewed opportunity.", "error");
      return;
    }
    const button = $("button[type='submit']", form);
    const name = String(new FormData(form).get("name") || "").trim();
    const baseDatasetId = state.evaluationBaseDatasetId;
    const endpoint = baseDatasetId
      ? `/v1/users/${state.userId}/evaluation-datasets/${baseDatasetId}/extend`
      : `/v1/users/${state.userId}/evaluation-datasets`;
    const payload = baseDatasetId
      ? { extraction_labels: labels }
      : { name, extraction_labels: labels };
    setBusy(button, true, baseDatasetId ? "Creating extended revision…" : "Freezing dataset…");
    try {
      const dataset = await api(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      showNotice(`Created ${dataset.name} revision ${dataset.revision} with ${dataset.cases.length} cases.`);
      $("#evaluation-candidate-editor").remove();
      state.evaluationCandidates = [];
      state.evaluationShowHistory = false;
      setDatasetBuildMode();
      form.reset();
      await loadEvaluationDatasets();
    } catch (error) {
      showNotice(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  });
}
