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

function caseResultHtml(item) {
  if (item.error_type) {
    return `
      <div class="evaluation-case is-error">
        <div><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.error_type)}: ${escapeHtml(item.error_message)}</p></div>
        <span class="decision-badge decision-reject">failed</span>
      </div>`;
  }
  const predicted = item.predicted_decision || "unknown";
  return `
    <div class="evaluation-case ${item.correct ? "is-correct" : "is-mismatch"}">
      <div>
        <strong>${escapeHtml(item.name)}</strong>
        <p>Expected ${escapeHtml(item.expected_decision)} · predicted ${escapeHtml(predicted)} · fit ${item.fit_score}</p>
        <p>${item.evidence_count} evidence claims · ${item.hypothesis_count} hypotheses · critic ${item.critic_passed ? "passed" : "flagged"}</p>
      </div>
      <span class="decision-badge decision-${escapeHtml(predicted)}">${item.correct ? "match" : "mismatch"}</span>
    </div>`;
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
    <article class="card">
      <p class="section-kicker">Case-by-case comparison</p>
      <h2>Where the model agreed with you</h2>
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
