(function () {
  const appConfig = window.TherapInHandApp || {};
  const logoutBtn = document.getElementById("logoutBtn");

  function csrfHeaders(extra = {}) {
    return {
      ...extra,
      "X-CSRF-Token": appConfig.csrfToken || "",
    };
  }

  logoutBtn?.addEventListener("click", async () => {
    const logoutUrl = logoutBtn.dataset.logoutUrl;
    if (!logoutUrl) return;
    logoutBtn.disabled = true;
    try {
      await fetch(logoutUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({}),
      });
      window.location.href = "/chat";
    } catch (error) {
      logoutBtn.disabled = false;
    }
  });

  window.TherapInHandFetch = {
    csrfHeaders,
  };
})();
