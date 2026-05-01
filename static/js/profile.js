(function () {
  const config = window.TherapInHandProfileConfig;
  const authHelpers = window.TherapInHandFetch;
  if (!config || !authHelpers) return;

  const solidCards = Array.from(document.querySelectorAll("[data-accent]"));
  const gradientCards = Array.from(document.querySelectorAll("[data-gradient]"));
  const modePills = Array.from(document.querySelectorAll("[data-mode]"));
  const saveBtn = document.getElementById("saveThemeBtn");
  const summaryEl = document.getElementById("profileThemeSummary");
  const usernameInput = document.getElementById("profileUsername");
  const emailInput = document.getElementById("profileEmail");

  const state = {
    theme_name: config.user.theme_name || config.defaults.theme_name,
    accent_color: config.user.accent_color || config.defaults.accent_color,
    gradient_theme: config.user.gradient_theme || config.defaults.gradient_theme,
    theme_mode: config.user.theme_mode || config.defaults.theme_mode,
  };

  function persistLocal() {
    localStorage.setItem("therapinhand-theme-prefs", JSON.stringify(state));
  }

  function resolveMode(mode) {
    return mode === "system"
      ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
      : mode;
  }

  function applyTheme() {
    document.documentElement.dataset.accent = state.accent_color;
    document.documentElement.dataset.gradient = state.gradient_theme;
    document.documentElement.dataset.mode = state.theme_mode;
    document.documentElement.dataset.modeResolved = resolveMode(state.theme_mode);

    solidCards.forEach((card) => {
      card.classList.toggle("selected", card.dataset.accent === state.accent_color);
      card.setAttribute("aria-pressed", card.dataset.accent === state.accent_color ? "true" : "false");
    });
    gradientCards.forEach((card) => {
      card.classList.toggle("selected", card.dataset.gradient === state.gradient_theme);
      card.setAttribute("aria-pressed", card.dataset.gradient === state.gradient_theme ? "true" : "false");
    });
    modePills.forEach((pill) => {
      pill.classList.toggle("selected", pill.dataset.mode === state.theme_mode);
      pill.setAttribute("aria-pressed", pill.dataset.mode === state.theme_mode ? "true" : "false");
    });
    if (summaryEl) {
      summaryEl.textContent = `${state.accent_color} accent | ${state.gradient_theme} gradient | ${state.theme_mode} mode`;
      summaryEl.title = summaryEl.textContent;
    }
  }

  solidCards.forEach((card) => {
    card.addEventListener("click", () => {
      state.theme_name = card.dataset.themeName || card.dataset.accent;
      state.accent_color = card.dataset.accent;
      persistLocal();
      applyTheme();
    });
  });

  gradientCards.forEach((card) => {
    card.addEventListener("click", () => {
      state.gradient_theme = card.dataset.gradient;
      persistLocal();
      applyTheme();
    });
  });

  modePills.forEach((pill) => {
    pill.addEventListener("click", () => {
      state.theme_mode = pill.dataset.mode;
      persistLocal();
      applyTheme();
    });
  });

  saveBtn?.addEventListener("click", async () => {
    persistLocal();
    saveBtn.disabled = true;
    saveBtn.setAttribute("aria-busy", "true");
    saveBtn.textContent = "Saving...";
    try {
      const themeResponse = await fetch(config.saveUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: authHelpers.csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(state),
      });
      if (!themeResponse.ok) {
        const data = await themeResponse.json();
        throw new Error(data.error || "Could not save preferences.");
      }

      if (config.user.id) {
        const profilePayload = {
          username: usernameInput?.value || config.user.username || config.user.name,
          email: emailInput?.value || config.user.email,
          ...state,
        };
        const response = await fetch(config.profileUrl, {
          method: "PATCH",
          credentials: "same-origin",
          headers: authHelpers.csrfHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(profilePayload),
        });
        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.error || "Could not save profile.");
        }
      }

      saveBtn.textContent = config.user.id ? "Saved" : "Saved Locally";
    } catch (error) {
      saveBtn.textContent = "Retry Save";
    } finally {
      window.setTimeout(() => {
        saveBtn.disabled = false;
        saveBtn.setAttribute("aria-busy", "false");
        saveBtn.textContent = "Save Preferences";
      }, 1200);
    }
  });

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (state.theme_mode === "system") {
      applyTheme();
    }
  });

  persistLocal();
  applyTheme();
})();
