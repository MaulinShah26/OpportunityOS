function percentage(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function decisionLabelHtml(labels) {
  return ["pursue", "hold", "reject"]
    .map((key) => `<span class="decision-badge decision-${key}">${key}: ${labels?.[key] || 0}</span>`)
    .join("");
}

function renderEvaluationDatasets() {
  const target = $("#evaluation-datasets");
  if (!state.evaluationDatasets.length) {
    target.innerHTML = `<article class="card evaluation-empty"><p class="section-kicker">No frozen dataset</p><h2>Label real opportunities first</h2><p class="memory-value">Analyse opportunities and record Worth pursuing, Save signal, or Not relevant.</p></article>`;
    return;
  }
  target.innerHTML = state.evaluationDatasets.map((dataset) => `
    <article class="card evaluation-dataset-card">
      <div class="card-heading"><div><p class="section-kicker">Frozen dataset</p><h2>${escapeHtml(dataset.name)}</h2><p class="memory-value">Created ${escapeHtml(formatDate(dataset.created_at))} · ${dataset.case_count} cases · ${dataset.extraction_label_count || 0} extraction-labelled</p></div><span class="${dataset.ready_for_comparison ? "privacy-badge" : "selective-badge"}">${dataset.ready_for_comparison ? "Comparison ready" : "Directional sample"}</span></div>
      <div class="decision-row evaluation-labels">${decisionLabelHtml(dataset.decision_labels)}</div>
      <div class="feedback-actions"><button class="button button-primary evaluation-run-button" data-dataset-id="${escapeHtml(dataset.dataset_id)}" type="button">Run current mode</button></div>
    </article>`).join("");
  $$(".evaluation-run-button", target).forEach((button) => button.addEventListener("click", () => runEvaluation(button.dataset.datasetId, button)));
}

async function loadEvaluationDatasets() {
  if (!state.userId) return;
  const target = $("#evaluation-datasets");
  target.innerHTML = `<div class="loading">Loading frozen datasets…</div>`;
  try {
    const response = await api(`/v1/users/${state.userId}/evaluation-datasets`);
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
  return `
    <article class="card extraction-candidate" data-analysis-id="${escapeHtml(candidate.source_analysis_id)}">
      <div class="card-heading">
        <div>
          <p class="section-kicker">Expected ${escapeHtml(candidate.expected_decision)}</p>
          <h3>${escapeHtml(candidate.name)}</h3>
        </div>
        <label class="toggle-label"><input data-field="selected" type="checkbox" checked> Include in v3</label>
      </div>
      <div class="issue-card info"><p>Confirm these values against the original source. Remove inferred or irrelevant items rather than accepting them automatically.</p></div>
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
      ? `<div class="issue-card info"><p>${priorCount} calibration case${priorCount === 1 ? " was" : "s were"} excluded because they already appear in an earlier frozen dataset.</p></div>`
      : "";
    target.innerHTML = newCandidates.length
      ? `${exclusionNote}<div class="issue-card warning"><p>Benchmark v3 must contain only new cases. Review each extraction label before freezing; do not tune the system after seeing its first v3 results.</p></div>${newCandidates.map(candidateEditorHtml).join("")}`
      : `${exclusionNote}<div class="blocked-outreach"><strong>No new decided opportunities</strong><p>Analyse and explicitly decide new opportunities before building benchmark v3.</p></div>`;
    showNotice(`${newCandidates.length} new cases loaded; ${priorCount} prior cases excluded.`);
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

function collectExtractionLabels() {
  return $$(".extraction-candidate").filter((card) => $("[data-field='selected']", card)?.checked).map((card) => {
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
  const contributions = Object.entries(item.fit_contributions || {}).sort((a, b) => b[1] - a[1]).map(([name, contribution]) => `<div class="diagnostic-row"><span>${escapeHtml(humanise(name))}</span><strong>${Number(contribution).toFixed(1)} points</strong></div>`).join("");
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
  const form = $("#evaluation-dataset-form");
  const reviewButton = document.createElement("button");
  reviewButton.className = "button button-secondary";
  reviewButton.type = "button";
  reviewButton.textContent = "Review new extraction labels";
  form.insertBefore(reviewButton, $("button[type='submit']", form));
  reviewButton.addEventListener("click", () => loadEvaluationCandidates(reviewButton));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!requireProfile()) return;
    const labels = collectExtractionLabels();
    if (!$("#evaluation-candidate-editor")) {
      showNotice("Review new extraction labels before creating benchmark v3.", "error");
      return;
    }
    if (!labels.length) {
      showNotice("Select at least one new reviewed opportunity for this frozen dataset.", "error");
      return;
    }
    const button = $("button[type='submit']", form);
    const name = String(new FormData(form).get("name") || "").trim();
    setBusy(button, true, "Freezing dataset…");
    try {
      const dataset = await api(`/v1/users/${state.userId}/evaluation-datasets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, extraction_labels: labels }),
      });
      showNotice(`Frozen ${dataset.cases.length} new decisions with complete reviewed extraction labels.`);
      $("#evaluation-candidate-editor").remove();
      state.evaluationCandidates = [];
      await loadEvaluationDatasets();
    } catch (error) {
      showNotice(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  });
}
