const API = "http://127.0.0.1:5001";
const userId = localStorage.getItem("userId");

if (!userId) window.location.href = "index.html";

loadTransactions();

// ── Settings popover ─────────────────────────────────────────────

function openSettings() {
  document.getElementById("settings-backdrop")?.classList.remove("hidden");
  document.getElementById("settings-panel")?.classList.remove("hidden");
  const t = document.getElementById("settings-trigger");
  if (t) t.setAttribute("aria-expanded", "true");
  setDefaultBudgetFormDates();
  loadBudgets();
}

function closeSettings() {
  document.getElementById("settings-backdrop")?.classList.add("hidden");
  document.getElementById("settings-panel")?.classList.add("hidden");
  const t = document.getElementById("settings-trigger");
  if (t) t.setAttribute("aria-expanded", "false");
}

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const panel = document.getElementById("settings-panel");
  if (panel && !panel.classList.contains("hidden")) closeSettings();
});

// ── Budgets (Settings) ────────────────────────────────────────────

function defaultBudgetDateRange() {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  const iso = (d) => d.toISOString().slice(0, 10);
  return { start: iso(start), end: iso(end) };
}

function setDefaultBudgetFormDates() {
  const startEl = document.getElementById("budget-start");
  const endEl = document.getElementById("budget-end");
  if (!startEl || !endEl) return;
  if (!startEl.value || !endEl.value) {
    const { start, end } = defaultBudgetDateRange();
    if (!startEl.value) startEl.value = start;
    if (!endEl.value) endEl.value = end;
  }
}

async function loadBudgets() {
  const listEl = document.getElementById("budget-list");
  if (!listEl) return;
  listEl.innerHTML = '<p class="text-xs text-zinc-500 p-2">Loading…</p>';
  try {
    const resp = await fetch(`${API}/api/users/${userId}/budgets`);
    const data = await resp.json();
    if (!resp.ok) {
      listEl.innerHTML = `<p class="text-xs text-red-400 p-2">${esc(data.error || "Could not load budgets")}</p>`;
      return;
    }
    renderBudgetList(Array.isArray(data) ? data : []);
  } catch {
    listEl.innerHTML = '<p class="text-xs text-red-400 p-2">Could not load budgets.</p>';
  }
}

function renderBudgetList(budgets) {
  const listEl = document.getElementById("budget-list");
  if (!listEl) return;
  if (!budgets.length) {
    listEl.innerHTML = '<p class="text-xs text-zinc-500 p-2">No budgets yet. Add one below.</p>';
    return;
  }
  listEl.innerHTML = "";
  budgets.forEach((b) => {
    const row = document.createElement("div");
    row.className = "flex items-start justify-between gap-2 p-2 font-sans text-sm";
    const amt = Number(b.amount);
    const amountStr = Number.isFinite(amt) ? amt.toFixed(2) : String(b.amount ?? "");
    row.innerHTML = `
      <div class="min-w-0">
        <p class="font-semibold text-zinc-900 truncate">${esc(b.category)}</p>
        <p class="text-zinc-600 text-xs">$${esc(amountStr)} · ${esc(b.start_date || "")} → ${esc(b.end_date || "")}</p>
      </div>`;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "shrink-0 text-xs text-zinc-500 hover:text-red-400 uppercase tracking-wide";
    btn.textContent = "Remove";
    btn.addEventListener("click", () => deleteBudget(b.category));
    row.appendChild(btn);
    listEl.appendChild(row);
  });
}

async function deleteBudget(category) {
  if (!category || !confirm(`Remove budget “${category}”?`)) return;
  try {
    const resp = await fetch(
      `${API}/api/users/${userId}/budgets/${encodeURIComponent(category)}`,
      { method: "DELETE" }
    );
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      alert(data.error || "Could not remove budget");
      return;
    }
    await loadBudgets();
  } catch {
    alert("Could not remove budget.");
  }
}

const budgetForm = document.getElementById("budget-form");
if (budgetForm) {
  budgetForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msgEl = document.getElementById("budget-form-message");
    const category = document.getElementById("budget-category").value.trim();
    const amount = document.getElementById("budget-amount").value;
    const start_date = document.getElementById("budget-start").value;
    const end_date = document.getElementById("budget-end").value;
    if (!category) {
      if (msgEl) {
        msgEl.textContent = "Enter a category.";
        msgEl.className = "text-xs mt-2 min-h-[1.25em] text-red-400";
      }
      return;
    }
    if (msgEl) {
      msgEl.textContent = "Saving…";
      msgEl.className = "text-xs mt-2 min-h-[1.25em] text-zinc-600";
    }
    try {
      const resp = await fetch(`${API}/api/users/${userId}/budgets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category,
          amount: Number(amount),
          start_date,
          end_date,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        if (msgEl) {
          msgEl.textContent = data.error || "Save failed";
          msgEl.className = "text-xs mt-2 min-h-[1.25em] text-red-400";
        }
        return;
      }
      if (msgEl) {
        msgEl.textContent = "Saved to Supabase.";
        msgEl.className = "text-xs mt-2 min-h-[1.25em] text-emerald-400";
      }
      budgetForm.reset();
      setDefaultBudgetFormDates();
      await loadBudgets();
    } catch {
      if (msgEl) {
        msgEl.textContent = "Network error.";
        msgEl.className = "text-xs mt-2 min-h-[1.25em] text-red-400";
      }
    }
  });
}

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

function displayCategory(t, isDeposit) {
  const raw = (t.category || "").trim();
  if (raw) return raw;
  if (isDeposit) return "Income";
  return "Uncategorized";
}

async function loadTransactions() {
  const container = document.getElementById("txn-list");

  try {
    const resp = await fetch(`${API}/api/users/${userId}/transactions?limit=50`);
    const data = await resp.json();

    if (!resp.ok) {
      const msg = data && data.error ? String(data.error) : `Error ${resp.status}`;
      container.innerHTML = `<p class="text-sm text-red-600 py-8 text-center font-sans">${esc(msg)}</p>`;
      return;
    }

    if (!Array.isArray(data) || !data.length) {
      container.innerHTML = '<p class="text-sm text-zinc-500 py-8 text-center font-sans">No transactions yet.</p>';
      return;
    }

    const txns = data;
    container.innerHTML = "";
    txns.forEach((t) => {
      const amt = parseFloat(t.amount) || 0;
      const isDeposit = t.type === "deposit";
      const categoryLabel = displayCategory(t, isDeposit);

      const row = document.createElement("div");
      row.className =
        "flex items-center justify-between gap-3 px-3 py-2.5 rounded-none hover:bg-zinc-100 transition group font-sans";
      row.innerHTML = `
        <div class="flex items-center gap-3 min-w-0 flex-1">
          <div class="w-8 h-8 rounded-none flex items-center justify-center shrink-0
            ${isDeposit ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-600"}">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="${isDeposit
                  ? "M12 19V5m0 0l-4 4m4-4l4 4"
                  : "M12 5v14m0 0l4-4m-4 4l-4-4"}" />
            </svg>
          </div>
          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium text-zinc-900 truncate">${esc(t.description || t.type)}</p>
            <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
              <span class="text-[11px] font-medium uppercase tracking-wide text-zinc-600 bg-zinc-100 px-1.5 py-0.5 rounded-none">
                ${esc(categoryLabel)}
              </span>
              <span class="text-xs text-zinc-500">${formatDate(t.transaction_date)}</span>
            </div>
          </div>
        </div>
        <span class="text-sm font-semibold tabular-nums shrink-0
          ${isDeposit ? "text-emerald-700" : "text-zinc-900"}">
          ${isDeposit ? "+" : "-"}$${amt.toFixed(2)}
        </span>`;
      container.appendChild(row);
    });
  } catch {
    container.innerHTML =
      '<p class="text-sm text-red-600 py-8 text-center font-sans">Failed to load transactions.</p>';
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
    <div class="flex items-center gap-3 text-sm text-zinc-500 font-sans">
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
    panel.innerHTML = '<p class="text-sm text-red-600 font-sans">Couldn’t load reasoning details.</p>';
  }
  scrollChat();
}

// ── Tool Calls Panel ───────────────────────────────────────────────

function renderToolCalls(toolCalls) {
  const panel = document.getElementById("tool-calls-panel");

  if (!toolCalls.length) {
    panel.innerHTML = '<p class="text-sm text-zinc-500 font-sans">No tools were used for this response.</p>';
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
  wrapper.className = "tool-step border border-zinc-200 rounded-none bg-zinc-50 shadow-sm font-sans";
  wrapper.innerHTML = `
    <div class="px-4 py-3 cursor-pointer select-none" onclick="toggleToolDetail(this)">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-xs font-bold text-zinc-400 w-5">${num}</span>
          <svg class="w-4 h-4 text-zinc-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
          </svg>
          <span class="text-sm font-semibold text-zinc-900">${esc(toolName)}</span>
          <span class="text-[10px] font-semibold bg-zinc-200 text-zinc-800 px-1.5 py-0.5 rounded-none">tool</span>
        </div>
        <svg class="w-4 h-4 text-zinc-400 transition-transform tool-chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
        </svg>
      </div>
      <p class="text-xs text-zinc-500 mt-1 ml-7">Args: ${esc(argsStr)}</p>
      <p class="text-sm text-zinc-800 mt-1 ml-7">${esc(resultSummary)}</p>
    </div>
    <div class="tool-detail-body" style="max-height: 0; overflow: hidden; transition: max-height 0.3s ease;">
      <div class="px-4 pb-3 ml-7 border-t border-zinc-200 pt-3">
        <p class="text-xs text-zinc-500 font-semibold mb-1">Full result:</p>
        <pre class="text-xs text-zinc-700 bg-white border border-zinc-100 rounded-none p-3 overflow-x-auto max-h-64 overflow-y-auto">${esc(resultJson)}</pre>
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
    case "get_budgets":
    case "get_budget_history": {
      const b = result.budgets || [];
      return b.length ? `${b.length} budget(s): ${b.map(x => x.category).join(", ")}` : "No budgets set";
    }
    case "set_budget": {
      if (result.saved && result.budget) {
        const a = Number(result.budget.amount);
        return `Saved ${result.budget.category}: $${a.toLocaleString("en-US", { minimumFractionDigits: 2 })} (${result.budget.start_date} → ${result.budget.end_date})`;
      }
      return result.saved ? "Budget saved" : "Completed";
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
    <div class="max-w-[80%] px-4 py-2.5 text-sm leading-relaxed font-sans rounded-lg
      ${isUser ? "bg-zinc-800 text-white rounded-br-md" : "bg-white text-zinc-900 border border-zinc-200 shadow-sm rounded-bl-md"}">
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
    <div class="bg-white border border-zinc-200 rounded-lg rounded-bl-md px-4 py-3 flex gap-1.5 shadow-sm">
      <span class="typing-dot w-2 h-2 bg-zinc-400 rounded-full"></span>
      <span class="typing-dot w-2 h-2 bg-zinc-400 rounded-full"></span>
      <span class="typing-dot w-2 h-2 bg-zinc-400 rounded-full"></span>
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
