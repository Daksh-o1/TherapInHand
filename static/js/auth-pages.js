(function () {
  const authHelpers = window.TherapInHandFetch;
  if (!authHelpers) return;

  const guestBtn = document.getElementById("guestContinueBtn");
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");

  async function submitAuthForm(form, feedbackId) {
    const feedbackEl = document.getElementById(feedbackId);
    const submitBtn = form.querySelector('button[type="submit"]');
    const formData = new FormData(form);
    const payload = Object.fromEntries(formData.entries());
    payload.remember_me = formData.get("remember_me") === "on";
    if (feedbackEl) feedbackEl.textContent = "";
    submitBtn.disabled = true;
    submitBtn.textContent = "Please wait...";
    try {
      const response = await fetch(form.dataset.submitUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: authHelpers.csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Something went wrong.");
      }
      window.location.href = form.dataset.redirectUrl || "/chat";
    } catch (error) {
      if (feedbackEl) feedbackEl.textContent = error.message;
      submitBtn.disabled = false;
      submitBtn.textContent = form.id === "registerForm" ? "Create Account" : "Login";
    }
  }

  loginForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    submitAuthForm(loginForm, "loginFeedback");
  });

  registerForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    submitAuthForm(registerForm, "registerFeedback");
  });

  guestBtn?.addEventListener("click", async () => {
    guestBtn.disabled = true;
    try {
      await fetch(guestBtn.dataset.guestUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: authHelpers.csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({}),
      });
      window.location.href = "/chat";
    } catch (error) {
      guestBtn.disabled = false;
    }
  });
})();
