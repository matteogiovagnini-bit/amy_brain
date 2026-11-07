// Pannello «Progetto»: sola lettura del repository locale.
// Modulo locale senza bundler. app.js passa i pochi helper condivisi.
(function () {
  "use strict";

  function render(payload, ui) {
    const isObject = ui.isObject;
    const statusResult = isObject(payload && payload.status) ? payload.status : {};
    const diffResult = isObject(payload && payload.diff) ? payload.diff : {};
    const status = isObject(statusResult.data) ? statusResult.data : {};
    const diff = isObject(diffResult.data) ? diffResult.data : {};
    const available = Boolean(payload && payload.available) && Boolean(statusResult.ok);
    if (!available) {
      ui.tag("projectTag", "non disponibile", "muted");
      ui.text("projectBranch", "Non disponibile");
      ui.text("projectModified", "Non disponibile");
      ui.text("projectCommit", "Non disponibile");
      const container = ui.$("projectDiff");
      if (container) {
        container.textContent = String(
          statusResult.message || (payload && payload.error) || "Modulo Developer non disponibile."
        );
      }
      return;
    }
    const changes = Number(status.modified || 0) + Number(status.untracked || 0);
    ui.tag("projectTag", status.clean ? "pulito" : changes + " modifiche", status.clean ? "ok" : "warn");
    ui.text("projectBranch", status.branch || "non disponibile");
    ui.text("projectModified",
      Number(status.modified || 0) + " modificati · " + Number(status.untracked || 0) + " non tracciati");
    const commit = isObject(status.last_commit) ? status.last_commit : {};
    ui.text("projectCommit",
      (commit.hash ? String(commit.hash) + " · " : "") + String(commit.subject || "non disponibile"));
    const container = ui.$("projectDiff");
    if (!container) return;
    const stat = String(diff.stat || "").trim();
    container.textContent = stat || "Nessuna modifica da mostrare.";
  }

  async function load(force, ui) {
    const app = ui.app;
    if (app.projectLoading) return;
    const now = Date.now();
    if (!force && app.projectLastFetch && now - app.projectLastFetch < 60000) return;
    app.projectLoading = true;
    try {
      const data = await ui.api("/api/dev/status");
      app.projectLastFetch = Date.now();
      render(data, ui);
    } catch (error) {
      render({ available: false, status: { ok: false, message: error.message } }, ui);
    } finally {
      app.projectLoading = false;
    }
  }

  window.AmyProject = { render: render, load: load };
})();
