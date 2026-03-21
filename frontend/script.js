const API = "http://127.0.0.1:5001";

const signinForm = document.getElementById("signin-form");
const accountForm = document.getElementById("account-form");
const goalsForm = document.getElementById("goals-form");

// ── Auto-redirect if already signed in ─────────────────────────────

if ((signinForm || accountForm) && localStorage.getItem("userId")) {
  window.location.href = "dashboard.html";
}

// ── Sign In ────────────────────────────────────────────────────────

if (signinForm) {
  signinForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.getElementById("signin-message");
    const btn = signinForm.querySelector("button");

    const firstName = document.getElementById("signinFirst").value.trim();
    const lastName = document.getElementById("signinLast").value.trim();

    if (!firstName || !lastName) {
      message.textContent = "Please enter your first and last name.";
      message.style.color = "#dc2626";
      return;
    }

    btn.disabled = true;
    btn.textContent = "Signing in...";
    message.textContent = "";

    try {
      const resp = await fetch(`${API}/api/users/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ first_name: firstName, last_name: lastName }),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || "Account not found");
      }

      const user = await resp.json();
      localStorage.setItem("userId", user.id);
      localStorage.setItem("userName", user.first_name);

      message.textContent = "Welcome back! Redirecting...";
      message.style.color = "#059669";

      setTimeout(() => {
        window.location.href = "dashboard.html";
      }, 500);
    } catch (err) {
      message.textContent = err.message;
      message.style.color = "#dc2626";
      btn.disabled = false;
      btn.textContent = "Sign In";
    }
  });
}

// ── Onboarding: Create Account ─────────────────────────────────────

if (accountForm) {
  accountForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.getElementById("account-message");
    const btn = accountForm.querySelector("button");

    const firstName = document.getElementById("firstName").value.trim();
    const lastName = document.getElementById("lastName").value.trim();
    const phone = document.getElementById("phone").value.trim();

    if (!firstName || !lastName || !phone) {
      message.textContent = "Please fill out all fields.";
      return;
    }

    btn.disabled = true;
    btn.textContent = "Creating account...";
    message.textContent = "";

    try {
      const resp = await fetch(`${API}/api/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          phone: phone,
          initial_balance: 1000,
        }),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || "Failed to create account");
      }

      const user = await resp.json();
      localStorage.setItem("userId", user.id);
      localStorage.setItem("userName", user.first_name);

      message.textContent = "Account created! Redirecting...";
      message.style.color = "#059669";

      setTimeout(() => {
        window.location.href = "goals.html";
      }, 600);
    } catch (err) {
      message.textContent = err.message;
      message.style.color = "#dc2626";
      btn.disabled = false;
      btn.textContent = "Continue";
    }
  });
}

// ── Onboarding: Financial Goals ────────────────────────────────────

if (goalsForm) {
  const userId = localStorage.getItem("userId");
  const userName = localStorage.getItem("userName");
  const greeting = document.getElementById("greeting");

  if (!userId) {
    window.location.href = "index.html";
  }

  if (userName && greeting) {
    greeting.textContent = `Hi ${userName}, please complete your financial goals below.`;
  }

  goalsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = document.getElementById("goals-message");
    const btn = goalsForm.querySelector("button");

    const goals = {
      monthly_income: Number(document.getElementById("monthlyIncome").value),
      monthly_expenses: Number(document.getElementById("monthlyExpenditures").value),
      savings_goal: Number(document.getElementById("savingsGoal").value),
      debt: Number(document.getElementById("debtAmount").value),
      current_savings: Number(document.getElementById("currentSavings").value),
    };

    btn.disabled = true;
    btn.textContent = "Saving...";
    message.textContent = "";

    try {
      const resp = await fetch(`${API}/api/users/${userId}/goals`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(goals),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || "Failed to save goals");
      }

      message.textContent = "Goals saved! Opening your dashboard...";
      message.style.color = "#059669";

      setTimeout(() => {
        window.location.href = "dashboard.html";
      }, 600);
    } catch (err) {
      message.textContent = err.message;
      message.style.color = "#dc2626";
      btn.disabled = false;
      btn.textContent = "Save Goals";
    }
  });
}
