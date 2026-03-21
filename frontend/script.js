const accountForm = document.getElementById("account-form");
const goalsForm = document.getElementById("goals-form");

function getStoredAccount() {
  const raw = localStorage.getItem("accountProfile");
  return raw ? JSON.parse(raw) : null;
}

if (accountForm) {
  accountForm.addEventListener("submit", (event) => {
    event.preventDefault();

    const firstName = document.getElementById("firstName").value.trim();
    const lastName = document.getElementById("lastName").value.trim();
    const phone = document.getElementById("phone").value.trim();

    if (!firstName || !lastName || !phone) {
      document.getElementById("account-message").textContent = "Please fill out all fields.";
      return;
    }

    const accountProfile = { firstName, lastName, phone };
    localStorage.setItem("accountProfile", JSON.stringify(accountProfile));

    const message = document.getElementById("account-message");
    message.textContent = "Account info saved. Moving to financial goals...";

    setTimeout(() => {
      window.location.href = "goals.html";
    }, 500);
  });
}

if (goalsForm) {
  const accountProfile = getStoredAccount();
  const greeting = document.getElementById("greeting");

  if (accountProfile && greeting) {
    greeting.textContent = `Hi ${accountProfile.firstName}, please complete your financial goals below.`;
  }

  goalsForm.addEventListener("submit", (event) => {
    event.preventDefault();

    const financialGoals = {
      monthlyIncome: Number(document.getElementById("monthlyIncome").value),
      monthlyExpenditures: Number(document.getElementById("monthlyExpenditures").value),
      savingsGoal: Number(document.getElementById("savingsGoal").value),
      debtAmount: Number(document.getElementById("debtAmount").value),
      currentSavings: Number(document.getElementById("currentSavings").value),
    };

    localStorage.setItem("financialGoals", JSON.stringify(financialGoals));

    const goalsMessage = document.getElementById("goals-message");
    goalsMessage.textContent = "Financial goals saved successfully.";
  });
}
