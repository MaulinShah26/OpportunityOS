function bindGoButtons(root = document) {
  $$('[data-go]', root).forEach((button) => button.addEventListener("click", () => {
    if (button.dataset.go !== "profile-view" && !requireProfile()) return;
    activateView(button.dataset.go);
  }));
}

function bindEvents() {
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => {
    if (button.dataset.view !== "profile-view" && !requireProfile()) return;
    activateView(button.dataset.view);
  }));
  bindGoButtons();

  $("#change-profile-button").addEventListener("click", clearProfile);

  $("#onboarding-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("button[type='submit']", event.currentTarget);
    setBusy(button, true, "Building model…");
    try {
      const formData = new FormData(event.currentTarget);
      const response = await api("/v1/profiles/onboard-file", {
        method: "POST",
        body: formData,
      });
      const profile = enrichOnboardedProfile(response.profile, formData);
      const email = String(formData.get("email") || "").trim();
      const saved = await api(`/v1/profiles${email ? `?email=${encodeURIComponent(email)}` : ""}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      setActiveProfile(saved.profile);
      showNotice(`Profile created with ${response.inferred_capabilities.length} inferred capabilities.`);
      activateView("analyse-view");
    } catch (error) {
      showNotice(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  });

  $("#load-profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("button[type='submit']", event.currentTarget);
    setBusy(button, true, "Loading…");
    const loaded = await loadProfile(new FormData(event.currentTarget).get("user_id"));
    if (loaded) activateView("analyse-view");
    setBusy(button, false);
  });

  $("#analysis-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!requireProfile()) return;
    const button = $("button[type='submit']", event.currentTarget);
    const data = new FormData(event.currentTarget);
    const opportunity = {};
    ["company_hint", "source_url", "raw_text"].forEach((key) => {
      const value = String(data.get(key) || "").trim();
      if (value) opportunity[key] = value;
    });
    if (!opportunity.source_url && !opportunity.raw_text) {
      showNotice("Provide a public URL or paste the opportunity text.", "error");
      return;
    }
    setBusy(button, true, "Analysing…");
    try {
      const result = await api(`/v1/users/${state.userId}/analyses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ opportunity }),
      });
      renderAnalysis(result);
      activateView("result-view");
      showNotice("Analysis completed and saved to your profile.");
    } catch (error) {
      showNotice(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  });

  $("#refresh-memory-button").addEventListener("click", loadMemory);
  $("#include-inactive-toggle").addEventListener("change", loadMemory);
  $("#refresh-audit-button").addEventListener("click", loadAudit);
  $("#cancel-memory-edit").addEventListener("click", () => $("#memory-dialog").close());
  $("#close-memory-dialog").addEventListener("click", () => $("#memory-dialog").close());

  $("#memory-edit-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("button[type='submit']", event.currentTarget);
    let value;
    try {
      value = JSON.parse($("#memory-edit-value").value);
    } catch (error) {
      showNotice("The memory value must be valid JSON.", "error");
      return;
    }
    setBusy(button, true, "Saving…");
    try {
      await api(`/v1/users/${state.userId}/memory/${$("#memory-edit-id").value}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "update",
          key: $("#memory-edit-key").value.trim(),
          value,
          reason: $("#memory-edit-reason").value.trim() || "Corrected from the web interface",
        }),
      });
      $("#memory-dialog").close();
      await Promise.all([loadMemory(), loadProfile(state.userId, true)]);
      showNotice("Memory correction saved.");
    } catch (error) {
      showNotice(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  });
}

async function initialise() {
  bindEvents();
  await checkHealth();
  if (state.userId) {
    const loaded = await loadProfile(state.userId, true);
    if (!loaded) clearProfile();
  }
}

document.addEventListener("DOMContentLoaded", initialise);
