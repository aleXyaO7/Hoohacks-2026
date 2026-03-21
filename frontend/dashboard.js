const API = "http://127.0.0.1:5001";
const userId = localStorage.getItem("userId");
const userName = localStorage.getItem("userName");

if (!userId) {
  window.location.href = "index.html";
}

// ── Init ───────────────────────────────────────────────────────────

document.getElementById("header-greeting").textContent =
  userName ? `Welcome back, ${userName}` : "";

loadDashboard();

document.getElementById("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendChat(text);
});

// ── Data Loading ───────────────────────────────────────────────────

async function loadDashboard() {
  await Promise.all([
    loadAccounts(),
    loadRisk(),
    loadTransactions(),
    loadAlerts(),
    loadChatHistory(),
  ]);
}

async function loadAccounts() {
  try {
    const resp = await fetch(`${API}/api/users/${userId}/accounts`);
    const accounts = await resp.json();

    const total = accounts.reduce((s, a) => s + Number(a.balance || 0), 0);
    document.getElementById("balance-amount").textContent = formatMoney(total);

    const list = document.getElementById("accounts-list");
    list.innerHTML = accounts.length
      ? accounts
          .map(
            (a) => `
          <div class="flex justify-between items-center py-2 border-t border-gray-100">
            <span class="text-sm text-gray-600">${a.type}</span>
            <span class="text-sm font-medium">${formatMoney(a.balance)}</span>
          </div>`
          )
          .join("")
      : '<p class="text-sm text-gray-400">No accounts linked yet.</p>';
  } catch {
    document.getElementById("balance-amount").textContent = "Error";
  }
}

async function loadRisk() {
  try {
    const resp = await fetch(`${API}/api/users/${userId}/risk`);
    if (!resp.ok) {
      setRiskEmpty();
      return;
    }
    const data = await resp.json();
    const risk = data.risk;
    if (!risk) {
      setRiskEmpty();
      return;
    }

    const badge = document.getElementById("risk-badge");
    badge.textContent = risk.risk_level.toUpperCase();
    badge.className = `px-2.5 py-0.5 rounded-full text-xs font-semibold ${riskColor(risk.risk_level)}`;

    document.getElementById("risk-score").textContent = risk.score;

    const factorsEl = document.getElementById("risk-factors");
    factorsEl.innerHTML = (risk.factors || [])
      .slice(0, 4)
      .map(
        (f) => `
        <div class="flex items-start gap-2">
          <span class="mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${severityDot(f.severity)}"></span>
          <span class="text-sm text-gray-700">${f.detail}</span>
        </div>`
      )
      .join("");

    const recsEl = document.getElementById("risk-recommendations");
    recsEl.innerHTML = (risk.recommendations || [])
      .slice(0, 3)
      .map(
        (r) =>
          `<p class="text-sm text-blue-700 bg-blue-50 rounded-lg px-3 py-2">${r}</p>`
      )
      .join("");
  } catch {
    setRiskEmpty();
  }
}

function setRiskEmpty() {
  document.getElementById("risk-score").textContent = "--";
  document.getElementById("risk-badge").textContent = "N/A";
  document.getElementById("risk-factors").innerHTML =
    '<p class="text-sm text-gray-400">Run Sync & Analyze to get your risk assessment.</p>';
}

async function loadTransactions() {
  try {
    const resp = await fetch(
      `${API}/api/users/${userId}/transactions?limit=20`
    );
    const txns = await resp.json();

    const list = document.getElementById("transactions-list");
    list.innerHTML = txns.length
      ? txns
          .map(
            (t) => `
          <div class="flex justify-between items-center py-2 border-b border-gray-50">
            <div>
              <p class="text-sm font-medium text-gray-800">${t.description || "Transaction"}</p>
              <p class="text-xs text-gray-400">${t.transaction_date || "N/A"} &middot; ${t.type}</p>
            </div>
            <span class="text-sm font-semibold ${t.type === "deposit" ? "text-green-600" : "text-gray-900"}">
              ${t.type === "deposit" ? "+" : "-"}${formatMoney(t.amount)}
            </span>
          </div>`
          )
          .join("")
      : '<p class="text-sm text-gray-400">No transactions yet. Run Sync & Analyze to pull from Nessie.</p>';
  } catch {
    document.getElementById("transactions-list").innerHTML =
      '<p class="text-sm text-red-500">Failed to load transactions.</p>';
  }
}

async function loadAlerts() {
  try {
    const resp = await fetch(`${API}/api/users/${userId}/alerts?limit=10`);
    const alerts = await resp.json();

    const list = document.getElementById("alerts-list");
    list.innerHTML = alerts.length
      ? alerts
          .map(
            (a) => `
          <div class="p-3 rounded-lg border ${alertBorder(a.risk_level)}">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-xs font-semibold ${riskColor(a.risk_level)} px-2 py-0.5 rounded-full">
                ${(a.risk_level || "info").toUpperCase()}
              </span>
              <span class="text-xs text-gray-400">${formatTime(a.sent_at)}</span>
            </div>
            <p class="text-sm text-gray-700">${a.message}</p>
          </div>`
          )
          .join("")
      : '<p class="text-sm text-gray-400">No alerts yet.</p>';
  } catch {
    document.getElementById("alerts-list").innerHTML =
      '<p class="text-sm text-red-500">Failed to load alerts.</p>';
  }
}

async function loadChatHistory() {
  try {
    const resp = await fetch(
      `${API}/api/users/${userId}/messages?channel=web&limit=50`
    );
    const messages = await resp.json();
    const container = document.getElementById("chat-messages");
    container.innerHTML = "";
    messages.forEach((m) => appendChatBubble(m.role, m.content));
    scrollChat();
  } catch {
    /* ignore */
  }
}

// ── Actions ────────────────────────────────────────────────────────

async function triggerPipeline() {
  const btn = document.getElementById("sync-btn");
  btn.disabled = true;
  btn.textContent = "Syncing...";

  try {
    const resp = await fetch(`${API}/api/users/${userId}/pipeline`, {
      method: "POST",
    });
    const result = await resp.json();

    if (result.error) {
      alert("Sync error: " + result.error);
    }

    await loadDashboard();
  } catch (err) {
    alert("Sync failed: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Sync & Analyze";
  }
}

async function sendChat(text) {
  appendChatBubble("user", text);
  showTypingIndicator();
  scrollChat();

  try {
    const resp = await fetch(`${API}/api/users/${userId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, channel: "web" }),
    });
    const data = await resp.json();
    removeTypingIndicator();
    appendChatBubble("assistant", data.response || data.error || "No response");
  } catch (err) {
    removeTypingIndicator();
    appendChatBubble("assistant", "Sorry, something went wrong. Please try again.");
  }
  scrollChat();
}

function logout() {
  localStorage.clear();
  window.location.href = "index.html";
}

// ── Chat UI helpers ────────────────────────────────────────────────

function appendChatBubble(role, content) {
  const container = document.getElementById("chat-messages");
  const isUser = role === "user";
  const bubble = document.createElement("div");
  bubble.className = `flex ${isUser ? "justify-end" : "justify-start"}`;
  bubble.innerHTML = `
    <div class="max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed
      ${isUser
        ? "bg-blue-600 text-white rounded-br-md"
        : "bg-gray-100 text-gray-800 rounded-bl-md"}">
      ${escapeHtml(content)}
    </div>`;
  container.appendChild(bubble);
}

function showTypingIndicator() {
  const container = document.getElementById("chat-messages");
  const el = document.createElement("div");
  el.id = "typing-indicator";
  el.className = "flex justify-start";
  el.innerHTML = `
    <div class="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-3 flex gap-1.5">
      <span class="typing-dot w-2 h-2 bg-gray-400 rounded-full"></span>
      <span class="typing-dot w-2 h-2 bg-gray-400 rounded-full"></span>
      <span class="typing-dot w-2 h-2 bg-gray-400 rounded-full"></span>
    </div>`;
  container.appendChild(el);
}

function removeTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

function scrollChat() {
  const c = document.getElementById("chat-messages");
  c.scrollTop = c.scrollHeight;
}

// ── Formatting helpers ─────────────────────────────────────────────

function formatMoney(n) {
  return "$" + Number(n || 0).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
    " " + d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function riskColor(level) {
  const map = {
    critical: "bg-red-100 text-red-700",
    high: "bg-orange-100 text-orange-700",
    medium: "bg-yellow-100 text-yellow-700",
    low: "bg-green-100 text-green-700",
  };
  return map[level] || "bg-gray-100 text-gray-600";
}

function severityDot(severity) {
  const map = {
    critical: "bg-red-500",
    high: "bg-orange-500",
    medium: "bg-yellow-500",
    low: "bg-green-500",
  };
  return map[severity] || "bg-gray-400";
}

function alertBorder(level) {
  const map = {
    critical: "border-red-200 bg-red-50",
    high: "border-orange-200 bg-orange-50",
    medium: "border-yellow-200 bg-yellow-50",
    low: "border-green-200 bg-green-50",
  };
  return map[level] || "border-gray-200";
}
