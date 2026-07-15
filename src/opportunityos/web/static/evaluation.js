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
    target.innerHTML = `
      <article class="card evaluation-empty">
        <p class="section-kicker">No frozen dataset</p>
        <h2>Label real opportunities first</h2>
        <p class="memory-value">Analyse opportunities and record Worth pursuing, Save signal, or Not relevant. Then return here to freeze those decisions into a benchmark.</p>
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
          ${dataset.ready_for_comparison ? "Comparison ready" : "Directional sample"}
        </span>
      </div>
      <div class="decision-row evaluation-labels">${decisionLabelHtml(dataset.decision_labels)}</div>
      <p class="memory-value">${dataset.ready_for_comparison
        ? "This snapshot meets the minimum size and label-balance rule."
        : "Add more explicit decisions, then create a new frozen version for reliable model comparison."}</p>
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
  try {
    const response = await api(`/v1/users/${state.userId}/evaluation-datasets`);
    state.evaluationDatasets = response.datasets || [];
    renderEvaluationDatasets();
  } catch (error) {
    target.innerHTML = `<div class="blocked-outreach"><strong>Evaluation unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
  }
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
  return `
    <div class="evaluation-case ${item.correct ? "is-correct" : "is-mismatch"}">
      <div>
        <strong>${escapeHtml(currentIdentity)}</strong>
        ${frozenLabel}
        <p>Expected ${escapeHtml(item.expected_decision)} · predicted ${escapeHtml(predicted)} · fit ${item.fit_score}${opportunityType ? ` · ${escapeHtml(humanise(opportunityType))}` : ""}</p>
        <p>${item.evidence_count} evidence claims · ${item.hypothesis_count} hypotheses · critic ${item.critic_passed ? "passed" : "flagged"}</p>
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
      <p class="memory-value">Underprediction means the system chose a more conservative action than your frozen label. Overprediction means it chose a more aggressive action. Gates can cap a high score when identity or work-style evidence is unsafe.</p>
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
        <div class="stat-box"><strong>${percentage(metrics.false_pursue_rate)}</strong><span>false pursue rate</span></div>
        <div class="stat-box"><strong>${percentage(metrics.critic_pass_rate)}</strong><span>critic pass rate</span></div>
        <div class="stat-box"><strong>${metrics.completed_count}/${metrics.case_count}</strong><span>completed cases</span></div>
        <div class="stat-box"><strong>${metrics.total_model_calls}</strong><span>model calls</span></div>
        <div class="stat-box"><strong>${metrics.total_reported_input_tokens + metrics.total_reported_output_tokens}</strong><span>reported tokens</span></div>
      </div>
      ${metrics.case_count < 5 ? `<div class="issue-card warning"><p>This run is directional because the frozen dataset contains fewer than five cases.</p></div>` : ""}
    </article>
    ${predictionPatternHtml(metrics)}
    ${thresholdSimulationHtml(report)}
    <article class="card">
      <p class="section-kicker">Case-by-case comparison</p>
      <h2>Where predictions matched or differed from your decisions</h2>
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
    showNotice(`Evaluation completed: ${percentage(report.metrics.decision_accuracy)} decision accuracy.`);
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
    setBusy(button, true, "Freezing dataset…");
    try {
      const dataset = await api(`/v1/users/${state.userId}/evaluation-datasets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      showNotice(`Frozen dataset created with ${dataset.cases.length} explicitly labelled cases.`);
      await loadEvaluationDatasets();
    } catch (error) {
      showNotice(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  });
}
