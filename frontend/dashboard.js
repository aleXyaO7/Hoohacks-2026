const API = "http://127.0.0.1:5001";
const userId = localStorage.getItem("userId");
const userName = localStorage.getItem("userName");

if (!userId) window.location.href = "index.html";

document.getElementById("header-greeting").textContent =
  userName ? `Welcome back, ${userName}` : "";

loadTransactions();
loadChatHistory();

document.getElementById("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendChat(text);
});

// ── Transactions ──────────────────────────────────────────────────

async function loadTransactions() {
  const container = document.getElementById("txn-list");
  const balancePill = document.getElementById("txn-balance");

  try {
    const resp = await fetch(`${API}/api/users/${userId}/transactions?limit=50`);
    const txns = await resp.json();

    if (!txns.length) {
      container.innerHTML = '<p class="text-sm text-gray-400 py-8 text-center">No transactions yet.</p>';
      balancePill.classList.add("hidden");
      return;
    }

    let totalDeposits = 0;
    let totalPurchases = 0;

    container.innerHTML = "";
    txns.forEach((t) => {
      const amt = parseFloat(t.amount) || 0;
      const isDeposit = t.type === "deposit";
      if (isDeposit) totalDeposits += amt; else totalPurchases += amt;

      const row = document.createElement("div");
      row.className =
        "flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-gray-50 transition group";
      row.innerHTML = `
        <div class="flex items-center gap-3 min-w-0">
          <div class="w-8 h-8 rounded-full flex items-center justify-center shrink-0
            ${isDeposit ? "bg-emerald-100 text-emerald-600" : "bg-red-100 text-red-500"}">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="${isDeposit
                  ? "M12 19V5m0 0l-4 4m4-4l4 4"
                  : "M12 5v14m0 0l4-4m-4 4l-4-4"}" />
            </svg>
          </div>
          <div class="min-w-0">
            <p class="text-sm font-medium text-gray-800 truncate">${esc(t.description || t.type)}</p>
            <p class="text-xs text-gray-400">${formatDate(t.transaction_date)}</p>
          </div>
        </div>
        <span class="text-sm font-semibold tabular-nums shrink-0
          ${isDeposit ? "text-emerald-600" : "text-gray-800"}">
          ${isDeposit ? "+" : "-"}$${amt.toFixed(2)}
        </span>`;
      container.appendChild(row);
    });

    const net = totalDeposits - totalPurchases;
    balancePill.textContent = `Net: ${net >= 0 ? "+" : ""}$${net.toFixed(2)}`;
    balancePill.className = `text-xs font-semibold px-2.5 py-1 rounded-full ${
      net >= 0
        ? "bg-emerald-50 text-emerald-700"
        : "bg-red-50 text-red-600"
    }`;
    balancePill.classList.remove("hidden");
  } catch {
    container.innerHTML =
      '<p class="text-sm text-red-500 py-8 text-center">Failed to load transactions.</p>';
  }
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ── Chat ───────────────────────────────────────────────────────────

async function loadChatHistory() {
  try {
    const resp = await fetch(`${API}/api/users/${userId}/messages?channel=web&limit=50`);
    const messages = await resp.json();
    const container = document.getElementById("chat-messages");
    container.innerHTML = "";
    messages.forEach((m) => appendChatBubble(m.role, m.content));
    scrollChat();
  } catch { /* ignore */ }
}

async function sendChat(text) {
  appendChatBubble("user", text);
  showTypingIndicator();
  scrollChat();

  const panel = document.getElementById("tool-calls-panel");
  panel.innerHTML = `
    <div class="flex items-center gap-3 text-sm text-gray-500">
      <svg class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
      </svg>
      Thinking...
    </div>`;

  try {
    const resp = await fetch(`${API}/api/users/${userId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, channel: "web" }),
    });
    const data = await resp.json();
    removeTypingIndicator();
    appendChatBubble("assistant", data.response || data.error || "No response");

    renderToolCalls(data.tool_calls || []);
  } catch {
    removeTypingIndicator();
    appendChatBubble("assistant", "Sorry, something went wrong.");
    panel.innerHTML = '<p class="text-sm text-red-500">Failed to retrieve tool calls.</p>';
  }
  scrollChat();
}

// ── Tool Calls Panel ───────────────────────────────────────────────

function renderToolCalls(toolCalls) {
  const panel = document.getElementById("tool-calls-panel");

  if (!toolCalls.length) {
    panel.innerHTML = '<p class="text-sm text-gray-400">No tools were called for this response.</p>';
    return;
  }

  panel.innerHTML = "";
  toolCalls.forEach((tc, i) => {
    const el = buildToolCallCard(i + 1, tc);
    panel.appendChild(el);
    setTimeout(() => el.classList.add("visible"), i * 200);
  });
}

function buildToolCallCard(num, tc) {
  const toolName = tc.tool.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  const argsStr = Object.keys(tc.args).length
    ? Object.entries(tc.args).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ")
    : "no arguments";

  const resultSummary = summarizeResult(tc.tool, tc.result);
  const resultJson = JSON.stringify(tc.result, null, 2);

  const wrapper = document.createElement("div");
  wrapper.className = "tool-step border border-gray-200 rounded-lg bg-white shadow-sm";
  wrapper.innerHTML = `
    <div class="px-4 py-3 cursor-pointer select-none" onclick="toggleToolDetail(this)">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-xs font-bold text-gray-400 w-5">${num}</span>
          <svg class="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
          </svg>
          <span class="text-sm font-semibold text-gray-800">${esc(toolName)}</span>
          <span class="text-[10px] font-semibold bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">tool</span>
        </div>
        <svg class="w-4 h-4 text-gray-400 transition-transform tool-chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
        </svg>
      </div>
      <p class="text-xs text-gray-500 mt-1 ml-7">Args: ${esc(argsStr)}</p>
      <p class="text-sm text-gray-700 mt-1 ml-7">${esc(resultSummary)}</p>
    </div>
    <div class="tool-detail-body" style="max-height: 0; overflow: hidden; transition: max-height 0.3s ease;">
      <div class="px-4 pb-3 ml-7 border-t border-gray-100 pt-3">
        <p class="text-xs text-gray-500 font-semibold mb-1">Full result:</p>
        <pre class="text-xs text-gray-600 bg-gray-50 rounded p-3 overflow-x-auto max-h-64 overflow-y-auto">${esc(resultJson)}</pre>
      </div>
    </div>`;
  return wrapper;
}

function summarizeResult(toolName, result) {
  if (result.error) return `Error: ${result.error}`;

  switch (toolName) {
    case "get_transaction_history": {
      const n = result.count || (result.transactions || []).length;
      return `Returned ${n} transaction(s)`;
    }
    case "get_account_balances": {
      const total = result.total_balance || 0;
      return `Total balance: $${total.toLocaleString("en-US", { minimumFractionDigits: 2 })} across ${(result.accounts || []).length} account(s)`;
    }
    case "get_budgets": {
      const b = result.budgets || [];
      return b.length ? `${b.length} budget(s): ${b.map(x => x.category).join(", ")}` : "No budgets set";
    }
    case "get_spending_by_category": {
      const cats = Object.keys(result.categories || {});
      const total = result.total_spending || 0;
      return `$${total.toLocaleString("en-US", { minimumFractionDigits: 2 })} across ${cats.length} categor${cats.length === 1 ? "y" : "ies"}`;
    }
    case "get_financial_summary": {
      return `Income: $${(result.monthly_income || 0).toLocaleString()}, Savings goal: $${(result.savings_goal || 0).toLocaleString()}`;
    }
    default:
      return "Completed";
  }
}

function toggleToolDetail(header) {
  const body = header.nextElementSibling;
  const chevron = header.querySelector(".tool-chevron");
  const isOpen = body.style.maxHeight !== "0px" && body.style.maxHeight !== "";
  body.style.maxHeight = isOpen ? "0px" : "500px";
  chevron.style.transform = isOpen ? "" : "rotate(180deg)";
}

// ── Chat UI helpers ────────────────────────────────────────────────

function appendChatBubble(role, content) {
  const container = document.getElementById("chat-messages");
  const isUser = role === "user";
  const div = document.createElement("div");
  div.className = `flex ${isUser ? "justify-end" : "justify-start"}`;
  div.innerHTML = `
    <div class="max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed
      ${isUser ? "bg-blue-600 text-white rounded-br-md" : "bg-gray-100 text-gray-800 rounded-bl-md"}">
      ${esc(content)}
    </div>`;
  container.appendChild(div);
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

function logout() {
  localStorage.clear();
  window.location.href = "index.html";
}

function esc(str) {
  const d = document.createElement("div");
  d.textContent = String(str || "");
  return d.innerHTML;
}
