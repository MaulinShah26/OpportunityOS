function percentage(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function decisionLabelHtml(labels) {
  return ["pursue", "hold", "reject"]
    .map((key) => `<span class="decision-badge decision-${key}">${key}: ${labels?.[key] || 0}</span>`)
    .join("");
}

const evaluationOpportunityTypes = [
  "unknown",
  "consulting",
  "fractional",
  "contract",
  "full_time",
  "advisory",
  "partnership",
];

function optionsHtml(values, selected) {
  return values.map((value) => `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(humanise(value))}</option>`).join("");
}

function listText(values) {
  return (values || []).join(", ");
}

function candidateHtml(candidate) {
  const remoteValue = candidate.extracted_remote_allowed === null
    ? "unknown"
    : String(candidate.extracted_remote_allowed);
  return `
    <article class="evaluation-candidate" data-analysis-id="${escapeHtml(candidate.source_analysis_id)}">
      <div class="candidate-heading">
        <div>
          <strong>${escapeHtml(candidate.name)}</strong>
          <p>Decision label: ${escapeHtml(candidate.expected_decision)}</p>
        </div>
        <label class="toggle-label"><input class="candidate-include" type="checkbox"> Include in new dataset</label>
      </div>
      <details>
        <summary>Review and correct extraction</summary>
        <div class="candidate-grid">
          <label><span>Company</span><input data-field="company" value="${escapeHtml(candidate.extracted_company_name)}"></label>
          <label><span>Title</span><input data-field="title" value="${escapeHtml(candidate.extracted_title)}"></label>
          <label><span>Opportunity type</span><select data-field="opportunity_type">${optionsHtml(evaluationOpportunityTypes, candidate.extracted_opportunity_type)}</select></label>
          <label><span>Remote status</span><select data-field="remote_allowed">${optionsHtml(["unknown", "true", "false"], remoteValue)}</select></label>
          <label class="candidate-wide"><span>Location</span><input data-field="location" value="${escapeHtml(candidate.extracted_location || "")}" placeholder="Leave blank when unknown"></label>
          <label class="candidate-wide"><span>Required skills <small>comma-separated</small></span><textarea data-field="required_skills" rows="3">${escapeHtml(listText(candidate.extracted_required_skills))}</textarea></label>
          <label class="candidate-wide"><span>Problem areas <small>comma-separated</small></span><textarea data-field="problem_areas" rows="3">${escapeHtml(listText(candidate.extracted_problem_areas))}</textarea></label>
          <label class="candidate-wide"><span>Responsibilities <small>comma-separated</small></span><textarea data-field="responsibilities" rows="3">${escapeHtml(listText(candidate.extracted_responsibilities))}</textarea></label>
        </div>
        <label class="candidate-confirm-label"><input class="candidate-confirm" type="checkbox"> I checked these fields against the supplied opportunity source</label>
      </details>
    </article>`;
}

function renderEvaluationCandidates() {
  const target = $("#evaluation-candidates");
  const candidates = state.evaluationCandidates || [];
  if (!candidates.length) {
    target.innerHTML = `<div class="blocked-outreach"><strong>No eligible cases</strong><p>Analyse opportunities and record explicit decisions before creating benchmark v3.</p></div>`;
    return;
  }
  target.innerHTML = `
    <div class="explanation-box">
      <strong>${candidates.length} explicitly decided opportunities available</strong>
      <p>Select only new out-of-sample cases for benchmark v3. Expand each selected case, correct the extraction, and confirm it against the source.</p>
    </div>
    ${candidates.map(candidateHtml).join("")}`;
}

async function loadEvaluationCandidates() {
  const target = $("#evaluation-candidates");
  if (!state.userId || !target) return;
  target.innerHTML = `<div class="loading">Loading labelled opportunities…</div>`;
  try {
    const response = await api(`/v1/users/${state.userId}/evaluation-candidates`);
    state.evaluationCandidates = response.candidates || [];
    renderEvaluationCandidates();
  } catch (error) {
    target.innerHTML = `<div class="blocked-outreach"><strong>Cases unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
  }
}

function collectExtractionLabels() {
  const cards = $$(".evaluation-candidate");
  const selected = cards.filter((card) => $(".candidate-include", card).checked);
  if (!selected.length) throw new Error("Select at least one new opportunity for the dataset.");
  return selected.map((card) => {
    if (!$(".candidate-confirm", card).checked) {
      throw new Error("Confirm every selected extraction after checking it against the source.");
    }
    const remoteValue = $("[data-field='remote_allowed']", card).value;
    return {
      source_analysis_id: card.dataset.analysisId,
      confirmed: true,
      expected_company_name: $("[data-field='company']", card).value.trim() || null,
      expected_title: $("[data-field='title']", card).value.trim() || null,
      expected_opportunity_type: $("[data-field='opportunity_type']", card).value,
      expected_remote_allowed: remoteValue === "unknown" ? null : remoteValue === "true",
      expected_location: $("[data-field='location']", card).value.trim() || null,
      expected_required_skills: commaSeparated($("[data-field='required_skills']", card).value),
      expected_problem_areas: commaSeparated($("[data-field='problem_areas']", card).value),
      expected_responsibilities: commaSeparated($("[data-field='responsibilities']", card).value),
    };
  });
}

function renderEvaluationDatasets() {
  const target = $("#evaluation-datasets");
  if (!state.evaluationDatasets.length) {
    target.innerHTML = `
      <article class="card evaluation-empty">
        <p class="section-kicker">No frozen dataset</p>
        <h2>Label real opportunities first</h2>
        <p class="memory-value">Analyse opportunities, record decisions, and confirm their extraction before freezing a benchmark.</p>
      </article>`;
    return;
  }

  target.innerHTML = state.evaluationDatasets.map((dataset) => `
    <article class="card evaluation-dataset-card">
      <div class="card-heading">
        <div>
          <p class="section-kicker">Frozen dataset</p>
          <h2>${escapeHtml(dataset.name)}</h2>
          <p class="memory-value">Created ${escapeHtml(formatDate(dataset.created_at))} · ${dataset.case_count} cases</p>
        </div>
        <span class="${dataset.ready_for_comparison ? "privacy-badge" : "selective-badge"}">
          ${dataset.ready_for_comparison ? "Decision ready" : "Directional sample"}
        </span>
      </div>
      <div class="decision-row evaluation-labels">${decisionLabelHtml(dataset.decision_labels)}</div>
      <p class="memory-value">Extraction labels: ${dataset.extraction_labelled_case_count || 0}/${dataset.case_count} · ${dataset.extraction_ready ? "extraction ready" : "decision-only benchmark"}</p>
      <div class="feedback-actions">
        <button class="button button-primary evaluation-run-button" data-dataset-id="${escapeHtml(dataset.dataset_id)}" type="button">Run current mode</button>
      </div>
    </article>`).join("");

  $$(".evaluation-run-button", target).forEach((button) => {
    button.addEventListener("click", () => runEvaluation(button.dataset.datasetId, button));
  });
}

async function loadEvaluationDatasets() {
  if (!state.userId) return;
  const target = $("#evaluation-datasets");
  target.innerHTML = `<div class="loading">Loading frozen datasets…</div>`;
  await Promise.all([
    (async () => {
      try {
        const response = await api(`/v1/users/${state.userId}/evaluation-datasets`);
        state.evaluationDatasets = response.datasets || [];
        renderEvaluationDatasets();
      } catch (error) {
        target.innerHTML = `<div class="blocked-outreach"><strong>Evaluation unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
      }
    })(),
    loadEvaluationCandidates(),
  ]);
}

function signedScore(value) {
  const numeric = Number(value || 0);
  return `${numeric >= 0 ? "+" : ""}${numeric}`;
}

function decisionGateHtml(item) {
  const gates = item.decision_gates || [];
  if (!gates.length) return `<p>Decision gates: none</p>`;
  const scoreDecision = item.score_based_decision || item.predicted_decision || "unknown";
  return `
    <div class="issue-card warning">
      <p><strong>Decision gate applied</strong></p>
      <p>Score policy said ${escapeHtml(scoreDecision)}; final decision became ${escapeHtml(item.predicted_decision)}.</p>
      <p>${gates.map((code) => escapeHtml(humanise(code))).join(", ")}</p>
    </div>`;
}

function extractionCaseHtml(item) {
  if (item.extraction_correct === null || item.extraction_correct === undefined) {
    return `<p>Extraction label: not supplied for this frozen case.</p>`;
  }
  const mismatches = Object.entries(item.extraction_field_results || {})
    .filter(([, passed]) => !passed)
    .map(([name]) => humanise(name));
  if (!mismatches.length) return `<p><strong>Extraction matched all ${item.extraction_checks} labelled fields.</strong></p>`;
  return `<div class="issue-card warning"><p><strong>Extraction mismatch</strong></p><p>${escapeHtml(mismatches.join(", "))}</p></div>`;
}

function fitDiagnosticsHtml(item) {
  const contributions = Object.entries(item.fit_contributions || {})
    .sort((left, right) => right[1] - left[1])
    .map(([name, contribution]) => `
      <div class="diagnostic-row">
        <span>${escapeHtml(humanise(name))}</span>
        <strong>${Number(contribution).toFixed(1)} points</strong>
      </div>`)
    .join("");
  const issueCodes = (item.critic_issue_codes || []).length
    ? `<p>Critic issues: ${item.critic_issue_codes.map((code) => escapeHtml(humanise(code))).join(", ")}</p>`
    : `<p>Critic issues: none</p>`;
  return `
    <details class="evaluation-diagnostics">
      <summary>Why this score and decision?</summary>
      <div class="diagnostic-grid">
        <div class="diagnostic-row"><span>Extraction confidence</span><strong>${percentage(item.extraction_confidence)}</strong></div>
        <div class="diagnostic-row"><span>Margin above HOLD threshold</span><strong>${signedScore(item.distance_to_hold_threshold)}</strong></div>
        <div class="diagnostic-row"><span>Margin above PURSUE threshold</span><strong>${signedScore(item.distance_to_pursue_threshold)}</strong></div>
        ${contributions}
      </div>
      ${extractionCaseHtml(item)}
      ${decisionGateHtml(item)}
      ${issueCodes}
    </details>`;
}

function caseResultHtml(item) {
  if (item.error_type) {
    return `
      <div class="evaluation-case is-error">
        <div><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.error_type)}: ${escapeHtml(item.error_message)}</p></div>
        <span class="decision-badge decision-reject">failed</span>
      </div>`;
  }
  const predicted = item.predicted_decision || "unknown";
  const company = item.extracted_company_name || item.analysis?.opportunity?.company_name || "Unknown company";
  const title = item.extracted_title || item.analysis?.opportunity?.title || item.name;
  const opportunityType = item.extracted_opportunity_type || item.analysis?.opportunity?.opportunity_type;
  const currentIdentity = `${company} — ${title}`;
  const frozenLabel = currentIdentity !== item.name
    ? `<p class="memory-value">Frozen case label: ${escapeHtml(item.name)}</p>`
    : "";
  const extractionStatus = item.extraction_correct === null || item.extraction_correct === undefined
    ? "extraction unlabelled"
    : item.extraction_correct ? "extraction matched" : "extraction mismatched";
  return `
    <div class="evaluation-case ${item.correct ? "is-correct" : "is-mismatch"}">
      <div>
        <strong>${escapeHtml(currentIdentity)}</strong>
        ${frozenLabel}
        <p>Expected ${escapeHtml(item.expected_decision)} · predicted ${escapeHtml(predicted)} · fit ${item.fit_score}${opportunityType ? ` · ${escapeHtml(humanise(opportunityType))}` : ""}</p>
        <p>${escapeHtml(extractionStatus)} · ${item.evidence_count} evidence claims · critic ${item.critic_passed ? "passed" : "flagged"}</p>
        ${fitDiagnosticsHtml(item)}
      </div>
      <span class="decision-badge decision-${escapeHtml(predicted)}">${item.correct ? "match" : "mismatch"}</span>
    </div>`;
}

function predictionPatternHtml(metrics) {
  return `
    <article class="card evaluation-diagnostic-card">
      <p class="section-kicker">Decision pattern</p>
      <h2>Is the system too aggressive or too conservative?</h2>
      <div class="evaluation-metrics compact-metrics">
        <div class="stat-box"><strong>${metrics.prediction_labels?.pursue || 0}</strong><span>predicted pursue</span></div>
        <div class="stat-box"><strong>${metrics.prediction_labels?.hold || 0}</strong><span>predicted hold</span></div>
        <div class="stat-box"><strong>${metrics.prediction_labels?.reject || 0}</strong><span>predicted reject</span></div>
        <div class="stat-box"><strong>${percentage(metrics.underprediction_rate)}</strong><span>underprediction</span></div>
        <div class="stat-box"><strong>${percentage(metrics.overprediction_rate)}</strong><span>overprediction</span></div>
        <div class="stat-box"><strong>${metrics.gated_case_count || 0}</strong><span>gated cases</span></div>
      </div>
    </article>`;
}

function extractionPatternHtml(metrics) {
  if (metrics.extraction_accuracy === null || metrics.extraction_accuracy === undefined) {
    return `
      <article class="card evaluation-diagnostic-card">
        <p class="section-kicker">Extraction quality</p>
        <h2>This dataset has no confirmed extraction labels</h2>
        <p class="memory-value">Decision agreement can still be measured, but it cannot prove that titles, types, skills, or problem areas were extracted correctly.</p>
      </article>`;
  }
  const fields = Object.entries(metrics.extraction_field_accuracy || {})
    .map(([name, value]) => `<div class="diagnostic-row"><span>${escapeHtml(humanise(name))}</span><strong>${percentage(value)}</strong></div>`)
    .join("");
  return `
    <article class="card evaluation-diagnostic-card">
      <p class="section-kicker">Extraction quality</p>
      <h2>Did the system read the opportunities correctly?</h2>
      <div class="evaluation-metrics compact-metrics">
        <div class="stat-box"><strong>${percentage(metrics.extraction_accuracy)}</strong><span>field accuracy</span></div>
        <div class="stat-box"><strong>${percentage(metrics.extraction_case_accuracy)}</strong><span>fully correct cases</span></div>
        <div class="stat-box"><strong>${metrics.extraction_labelled_case_count}/${metrics.case_count}</strong><span>labelled cases</span></div>
        <div class="stat-box"><strong>${metrics.extraction_field_count}</strong><span>checked fields</span></div>
      </div>
      <div class="diagnostic-grid">${fields}</div>
    </article>`;
}

function thresholdSimulationHtml(report) {
  const policy = report.decision_policy || { hold_threshold: 45, pursue_threshold: 72 };
  const simulation = report.threshold_simulation;
  if (!simulation) {
    return `
      <article class="card evaluation-diagnostic-card">
        <p class="section-kicker">Threshold calibration</p>
        <h2>No better safe threshold candidate yet</h2>
        <p class="memory-value">Current policy: HOLD at ${policy.hold_threshold}, PURSUE at ${policy.pursue_threshold}. Add more balanced cases before interpreting score thresholds.</p>
      </article>`;
  }
  return `
    <article class="card evaluation-diagnostic-card">
      <p class="section-kicker">Exploratory threshold simulation</p>
      <h2>A candidate policy fits this frozen sample better</h2>
      <div class="threshold-comparison">
        <div><span>Current</span><strong>HOLD ${policy.hold_threshold} · PURSUE ${policy.pursue_threshold}</strong><small>${percentage(report.metrics.decision_accuracy)} accuracy</small></div>
        <div><span>Simulated</span><strong>HOLD ${simulation.hold_threshold} · PURSUE ${simulation.pursue_threshold}</strong><small>${percentage(simulation.decision_accuracy)} accuracy · ${percentage(simulation.false_pursue_rate)} false pursue</small></div>
      </div>
      <div class="issue-card warning"><p>${escapeHtml(simulation.sample_warning)} The simulated values are not applied to production decisions.</p></div>
    </article>`;
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
  target.innerHTML = `
    <article class="card evaluation-report-hero">
      <div class="card-heading">
        <div>
          <p class="section-kicker">Latest benchmark run</p>
          <h2>${escapeHtml(report.dataset_name)}</h2>
          <p class="memory-value">Mode ${escapeHtml(report.mode)} · providers ${escapeHtml(report.provider_order)} · completed ${escapeHtml(formatDate(report.completed_at))}</p>
        </div>
        <button id="download-evaluation-report" class="button button-secondary" type="button">Download JSON</button>
      </div>
      <div class="evaluation-metrics">
        <div class="stat-box"><strong>${percentage(metrics.decision_accuracy)}</strong><span>decision accuracy</span></div>
        <div class="stat-box"><strong>${metrics.extraction_accuracy === null || metrics.extraction_accuracy === undefined ? "—" : percentage(metrics.extraction_accuracy)}</strong><span>extraction accuracy</span></div>
        <div class="stat-box"><strong>${percentage(metrics.false_pursue_rate)}</strong><span>false pursue rate</span></div>
        <div class="stat-box"><strong>${percentage(metrics.critic_pass_rate)}</strong><span>critic pass rate</span></div>
        <div class="stat-box"><strong>${metrics.completed_count}/${metrics.case_count}</strong><span>completed cases</span></div>
        <div class="stat-box"><strong>${metrics.total_model_calls}</strong><span>model calls</span></div>
      </div>
      ${metrics.case_count < 5 ? `<div class="issue-card warning"><p>This run is directional because the frozen dataset contains fewer than five cases.</p></div>` : ""}
    </article>
    ${extractionPatternHtml(metrics)}
    ${predictionPatternHtml(metrics)}
    ${thresholdSimulationHtml(report)}
    <article class="card">
      <p class="section-kicker">Case-by-case comparison</p>
      <h2>Decision and extraction results</h2>
      <div class="evaluation-cases">${report.cases.map(caseResultHtml).join("")}</div>
    </article>`;
  target.classList.remove("is-hidden");
  $("#download-evaluation-report").addEventListener("click", downloadEvaluationReport);
  target.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runEvaluation(datasetId, button) {
  setBusy(button, true, "Running benchmark…");
  try {
    const report = await api(`/v1/users/${state.userId}/evaluation-datasets/${datasetId}/runs`, {
      method: "POST",
    });
    renderEvaluationReport(report);
    const extraction = report.metrics.extraction_accuracy;
    const suffix = extraction === null || extraction === undefined ? "" : ` · ${percentage(extraction)} extraction accuracy`;
    showNotice(`Evaluation completed: ${percentage(report.metrics.decision_accuracy)} decision accuracy${suffix}.`);
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

function bindEvaluationEvents() {
  $("#refresh-evaluations-button").addEventListener("click", loadEvaluationDatasets);
  $("#evaluation-dataset-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!requireProfile()) return;
    const button = $("button[type='submit']", event.currentTarget);
    const name = String(new FormData(event.currentTarget).get("name") || "").trim();
    let extractionLabels;
    try {
      extractionLabels = collectExtractionLabels();
    } catch (error) {
      showNotice(error.message, "error");
      return;
    }
    setBusy(button, true, "Freezing labelled dataset…");
    try {
      const dataset = await api(`/v1/users/${state.userId}/evaluation-datasets-labelled`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, extraction_labels: extractionLabels }),
      });
      showNotice(`Frozen dataset created with ${dataset.cases.length} extraction-labelled cases.`);
      await loadEvaluationDatasets();
    } catch (error) {
      showNotice(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  });
}
