function dimensionHtml(item) {
  const percent = Math.round(item.score * 100);
  return `
    <div class="dimension">
      <div class="dimension-heading"><strong>${escapeHtml(humanise(item.name))}</strong><span>${percent}%</span></div>
      <div class="progress"><span style="width:${percent}%"></span></div>
      <p>${escapeHtml(item.explanation)}</p>
    </div>`;
}

function criticHtml(critic) {
  if (critic.passed && !critic.issues.length) {
    return `<div class="critic-pass"><strong>Guardrails passed</strong><span>No blocking evidence or outreach issues were detected.</span></div>`;
  }
  return renderList(
    critic.issues,
    (issue) => `
      <div class="issue-card ${escapeHtml(issue.severity)}">
        <div class="issue-heading"><strong>${escapeHtml(humanise(issue.code))}</strong><span class="issue-severity">${escapeHtml(issue.severity)}</span></div>
        <p>${escapeHtml(issue.message)}</p>
        ${issue.claim ? `<p><strong>Claim:</strong> ${escapeHtml(issue.claim)}</p>` : ""}
      </div>`,
    "No critic details are available.",
  );
}

function outreachHtml(result) {
  if (result.outreach) {
    return `
      <div class="outreach-box">
        <div class="outreach-heading">Safe outreach preview</div>
        ${result.outreach.subject ? `<div class="outreach-subject">Subject: ${escapeHtml(result.outreach.subject)}</div>` : ""}
        <div class="outreach-body">${escapeHtml(result.outreach.body)}</div>
      </div>`;
  }
  if (result.critic?.block_outreach) {
    return `<div class="blocked-outreach"><strong>Outreach blocked</strong><p>The critic found unsupported claims. Review the issues and evidence before drafting a message.</p></div>`;
  }
  return `<p class="memory-value">No outreach was generated for this decision.</p>`;
}

function renderAnalysis(result) {
  state.analysis = result;
  $("#analysis-empty").classList.add("is-hidden");
  const target = $("#analysis-result");
  const decision = result.recommendation.decision;
  const evidence = result.opportunity.evidence || [];
  const hypotheses = result.hypotheses || [];
  target.innerHTML = `
    <article class="card result-hero">
      <div class="score-ring" style="--score:${result.fit_score.total}">
        <div class="score-value"><strong>${result.fit_score.total}</strong><span>personal fit</span></div>
      </div>
      <div>
        <div class="decision-row">
          <span class="decision-badge decision-${escapeHtml(decision)}">${escapeHtml(decision)}</span>
          <span class="tag">${escapeHtml(humanise(result.opportunity.opportunity_type))}</span>
          ${result.opportunity.location ? `<span class="tag">${escapeHtml(result.opportunity.location)}</span>` : ""}
        </div>
        <h2 class="result-title">${escapeHtml(result.opportunity.title)}</h2>
        <p class="result-subtitle">${escapeHtml(result.opportunity.company_name)}</p>
        <p class="result-rationale">${escapeHtml(result.recommendation.rationale)}</p>
        <p class="result-rationale"><strong>Next action:</strong> ${escapeHtml(result.recommendation.next_action)}</p>
        <div class="feedback-actions">
          <button class="button button-primary feedback-button" data-action="pursue" type="button">Worth pursuing</button>
          <button class="button button-secondary feedback-button" data-action="save" type="button">Save signal</button>
          <button class="button button-danger feedback-button" data-action="reject" type="button">Not relevant</button>
        </div>
      </div>
    </article>
    <div class="result-grid">
      <div class="result-column">
        <article class="card">
          <p class="section-kicker">Personal fit</p>
          <h2>Why it scored this way</h2>
          <div style="margin-top:22px">${result.fit_score.dimensions.map(dimensionHtml).join("")}</div>
          ${result.fit_score.hard_constraint_breaches.length ? `<div class="blocked-outreach" style="margin-top:18px"><strong>Hard constraints</strong><p>${escapeHtml(result.fit_score.hard_constraint_breaches.join("; "))}</p></div>` : ""}
        </article>
        <article class="card">
          <p class="section-kicker">Reasoning</p>
          <h2>Business hypotheses</h2>
          <div style="margin-top:18px">${renderList(hypotheses, (item) => `
            <div class="hypothesis-card">
              <div class="issue-heading"><strong>${escapeHtml(humanise(item.claim_type))}</strong><span>${Math.round(item.confidence * 100)}% confidence</span></div>
              <p>${escapeHtml(item.statement)}</p><p>${escapeHtml(item.rationale)}</p>
            </div>`, "No hypotheses were generated.")}</div>
        </article>
        <article class="card">
          <p class="section-kicker">Evidence</p>
          <h2>What the analysis is grounded in</h2>
          <div style="margin-top:18px">${renderList(evidence, (item) => `
            <div class="evidence-card">
              <div class="issue-heading"><strong>${escapeHtml(humanise(item.claim_type))}</strong><span>${Math.round(item.confidence * 100)}%</span></div>
              <p>${escapeHtml(item.claim)}</p>
              <p>${escapeHtml(item.supporting_excerpt)}</p>
            </div>`, "No evidence was captured.")}</div>
        </article>
      </div>
      <div class="result-column">
        <article class="card">
          <p class="section-kicker">Critic</p>
          <h2>Evidence and claim guardrails</h2>
          <div style="margin-top:18px">${criticHtml(result.critic)}</div>
        </article>
        <article class="card">
          <p class="section-kicker">Communication</p>
          <h2>Outreach</h2>
          <div style="margin-top:18px">${outreachHtml(result)}</div>
        </article>
        <article class="card">
          <p class="section-kicker">Risks</p>
          <h2>What to watch</h2>
          <div style="margin-top:16px">${renderList(result.recommendation.risks, (risk) => `<div class="issue-card warning"><p>${escapeHtml(risk)}</p></div>`, "No specific risks were recorded.")}</div>
        </article>
      </div>
    </div>`;
  target.classList.remove("is-hidden");
  $$(".feedback-button", target).forEach((button) => button.addEventListener("click", () => submitFeedback(button.dataset.action, button)));
}

async function submitFeedback(action, button) {
  if (!state.userId || !state.analysis) return;
  const reasons = action === "pursue" ? ["strong_fit"] : [];
  const apiAction = action === "reject" ? "reject" : action;
  setBusy(button, true, "Saving…");
  try {
    await api(`/v1/users/${state.userId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        feedback: {
          analysis_id: state.analysis.analysis_id,
          action: apiAction,
          reasons,
          explicit: true,
        },
      }),
    });
    await loadProfile(state.userId, true);
    showNotice("Feedback saved and the personal model was updated.");
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}
