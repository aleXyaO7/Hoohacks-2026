const API = "http://127.0.0.1:5001";
const userId = localStorage.getItem("userId");
const userName = localStorage.getItem("userName");

if (!userId) window.location.href = "index.html";

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
    loadTransactions(),
    loadRisk(),
    loadChatHistory(),
  ]);
}

async function loadTransactions() {
  try {
    const [acctResp, txnResp] = await Promise.all([
      fetch(`${API}/api/users/${userId}/accounts`),
      fetch(`${API}/api/users/${userId}/transactions?limit=30`),
    ]);
    const accounts = await acctResp.json();
    const txns = await txnResp.json();

    const total = accounts.reduce((s, a) => s + Number(a.balance || 0), 0);
    document.getElementById("balance-pill").textContent = formatMoney(total);

    const list = document.getElementById("transactions-list");
    list.innerHTML = txns.length
      ? txns.map((t) => `
          <div class="flex justify-between items-center py-2.5 px-2 rounded-lg hover:bg-gray-50 transition">
            <div class="min-w-0">
              <p class="text-sm font-medium text-gray-800 truncate">${esc(t.description || "Transaction")}</p>
              <p class="text-xs text-gray-400">${t.transaction_date || "N/A"}</p>
            </div>
            <span class="text-sm font-semibold whitespace-nowrap ml-3 ${t.type === "deposit" ? "text-green-600" : "text-gray-900"}">
              ${t.type === "deposit" ? "+" : "-"}${formatMoney(t.amount)}
            </span>
          </div>`).join("")
      : '<p class="text-sm text-gray-400 py-4 text-center">No transactions yet. Click Sync & Analyze.</p>';
  } catch {
    document.getElementById("transactions-list").innerHTML =
      '<p class="text-sm text-red-500 text-center py-4">Failed to load.</p>';
  }
}

async function loadRisk() {
  try {
    const resp = await fetch(`${API}/api/users/${userId}/risk`);
    if (!resp.ok) { setRiskEmpty(); return; }
    const data = await resp.json();
    const risk = data.risk;
    if (!risk) { setRiskEmpty(); return; }
    renderRisk(risk);
  } catch { setRiskEmpty(); }
}

// ── Risk Gauge ─────────────────────────────────────────────────────

function renderRisk(risk, animate = false) {
  const score = risk.score;
  const level = risk.risk_level;

  document.getElementById("risk-score").textContent = animate ? "0" : score;

  const badge = document.getElementById("risk-badge");
  badge.textContent = level.toUpperCase();
  badge.className = `ml-2 px-2.5 py-0.5 rounded-full text-xs font-semibold ${riskBadgeColor(level)}`;

  // Gauge arc: 157 is the full arc length
  const arc = document.getElementById("gauge-arc");
  const offset = 157 - (score / 100) * 157;
  arc.style.stroke = gaugeColor(score);
  if (animate) {
    arc.style.transition = "none";
    arc.style.strokeDashoffset = "157";
    requestAnimationFrame(() => {
      arc.style.transition = "stroke-dashoffset 1.2s ease-out";
      arc.style.strokeDashoffset = offset;
    });
    animateNumber("risk-score", 0, score, 1200);
  } else {
    arc.style.strokeDashoffset = offset;
  }

  // Factors
  const factorsEl = document.getElementById("risk-factors");
  factorsEl.innerHTML = (risk.factors || []).slice(0, 4).map((f) => `
    <div class="flex items-start gap-2">
      <span class="mt-1 w-2 h-2 rounded-full flex-shrink-0 ${severityDot(f.severity)}"></span>
      <span class="text-sm text-gray-700">${esc(f.detail)}</span>
    </div>`).join("");
}

function setRiskEmpty() {
  document.getElementById("risk-score").textContent = "--";
  const badge = document.getElementById("risk-badge");
  badge.textContent = "N/A";
  badge.className = "ml-2 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-500";
  document.getElementById("gauge-arc").style.strokeDashoffset = "157";
  document.getElementById("risk-factors").innerHTML =
    '<p class="text-sm text-gray-400">Run Sync & Analyze to get your risk assessment.</p>';
}

function animateNumber(elId, from, to, duration) {
  const el = document.getElementById(elId);
  const start = performance.now();
  function tick(now) {
    const p = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(from + (to - from) * eased);
    if (p < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ── Pipeline + Animated Reasoning ──────────────────────────────────

async function triggerPipeline() {
  const btn = document.getElementById("sync-btn");
  const icon = document.getElementById("sync-icon");
  btn.disabled = true;
  document.getElementById("sync-text").textContent = "Running...";
  icon.classList.add("animate-spin");

  // Clear timeline, show running state
  const timeline = document.getElementById("reasoning-timeline");
  timeline.innerHTML = `
    <div class="flex items-center gap-3 text-sm text-gray-500">
      <svg class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
      </svg>
      Running agent pipeline...
    </div>`;

  try {
    const resp = await fetch(`${API}/api/users/${userId}/pipeline`, { method: "POST" });
    const result = await resp.json();

    if (result.error) {
      timeline.innerHTML = `<p class="text-sm text-red-500">Error: ${esc(result.error)}</p>`;
      return;
    }

    // Render trace steps with staggered animation
    const trace = result.trace || [];
    timeline.innerHTML = "";

    for (let i = 0; i < trace.length; i++) {
      const step = trace[i];
      const el = buildTraceStep(i + 1, step);
      timeline.appendChild(el);
      // Stagger: each step appears 400ms after the previous
      setTimeout(() => el.classList.add("visible"), i * 400);
    }

    // Animate risk gauge after trace finishes
    if (result.risk) {
      const riskDelay = trace.length * 400;
      setTimeout(() => renderRisk(result.risk, true), riskDelay);
    }

    // Refresh transactions
    await loadTransactions();

  } catch (err) {
    timeline.innerHTML = `<p class="text-sm text-red-500">Pipeline failed: ${esc(err.message)}</p>`;
  } finally {
    btn.disabled = false;
    document.getElementById("sync-text").textContent = "Sync & Analyze";
    icon.classList.remove("animate-spin");
  }
}

function buildTraceStep(num, step) {
  const isLLM = step.agent_type === "llm";
  const isSkipped = step.status === "skipped";
  const isError = step.status === "error";

  const statusIcon = isError
    ? `<span class="text-red-500">&#10007;</span>`
    : isSkipped
    ? `<span class="text-gray-400">&#8212;</span>`
    : `<span class="text-green-600">&#10003;</span>`;

  const statusBorder = isError ? "border-red-200" : isSkipped ? "border-gray-200" : "border-green-200";

  const llmBadge = isLLM
    ? `<span class="ml-2 text-[10px] font-semibold bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">${esc(step.model || "LLM")}</span>`
    : `<span class="ml-2 text-[10px] font-semibold bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">deterministic</span>`;

  const durationStr = step.duration_ms > 0 ? `${step.duration_ms}ms` : "";

  const detailsHtml = buildDetailsHtml(step);

  const wrapper = document.createElement("div");
  wrapper.className = `trace-step border-l-4 ${statusBorder} rounded-lg bg-white shadow-sm`;
  wrapper.innerHTML = `
    <div class="px-4 py-3 cursor-pointer select-none" onclick="toggleDetail(this)">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-xs font-bold text-gray-400 w-5">${num}</span>
          ${statusIcon}
          <span class="text-sm font-semibold text-gray-800">${esc(step.agent)}</span>
          ${llmBadge}
        </div>
        <div class="flex items-center gap-3">
          <span class="text-xs text-gray-400">${durationStr}</span>
          <svg class="w-4 h-4 text-gray-400 transition-transform detail-chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
          </svg>
        </div>
      </div>
      <p class="text-sm text-gray-600 mt-1 ml-7">${esc(step.output_summary)}</p>
    </div>
    <div class="detail-body">
      <div class="px-4 pb-3 ml-7 border-t border-gray-100 pt-3 space-y-2">
        <p class="text-xs text-gray-500"><span class="font-semibold">Input:</span> ${esc(step.input_summary)}</p>
        ${detailsHtml}
      </div>
    </div>`;
  return wrapper;
}

function buildDetailsHtml(step) {
  const d = step.details || {};
  const lines = [];

  // Sync agent
  if (d.events_detected && d.events_detected.length) {
    lines.push(`<span class="font-semibold">Events:</span> ${d.events_detected.map(e => `<span class="inline-block bg-blue-50 text-blue-700 text-[11px] px-1.5 py-0.5 rounded mr-1">${esc(e)}</span>`).join("")}`);
  }

  // Risk agent
  if (d.score !== undefined) {
    lines.push(`<span class="font-semibold">Score:</span> ${d.score}/100 → ${esc(d.risk_level || "").toUpperCase()}`);
  }
  if (d.factors && d.factors.length) {
    const factorStrs = d.factors.map(f => `<span class="${severityText(f.severity)}">[${f.severity.toUpperCase()}]</span> ${esc(f.detail)}`);
    lines.push(`<span class="font-semibold">Factors:</span><br/>${factorStrs.join("<br/>")}`);
  }
  if (d.recommendations && d.recommendations.length) {
    lines.push(`<span class="font-semibold">Recommendations:</span><br/>${d.recommendations.map(r => "• " + esc(r)).join("<br/>")}`);
  }

  // Notification agent
  if (d.decision) {
    lines.push(`<span class="font-semibold">Decision:</span> ${esc(d.decision)}`);
  }
  if (d.reason) {
    lines.push(`<span class="font-semibold">Reason:</span> ${esc(d.reason)}`);
  }
  if (d.suppressed_reasons && d.suppressed_reasons.length) {
    lines.push(`<span class="font-semibold">Suppressed:</span> ${d.suppressed_reasons.map(r => esc(r)).join("; ")}`);
  }

  // Messaging agent
  if (d.messages && d.messages.length) {
    d.messages.forEach(m => {
      lines.push(`<span class="font-semibold">${esc(m.channel)} message:</span><br/><span class="text-gray-700 italic">"${esc(m.message)}"</span>`);
    });
  }

  // Context gathering agent
  if (d.balance !== undefined) {
    lines.push(`<span class="font-semibold">Balance:</span> $${Number(d.balance).toLocaleString("en-US", {minimumFractionDigits: 2})}`);
  }
  if (d.transactions !== undefined) {
    lines.push(`<span class="font-semibold">Data loaded:</span> ${d.accounts} account(s), ${d.transactions} transaction(s), ${d.budgets} budget(s)`);
  }

  // Goals agent
  if (d.aligned !== undefined) {
    const alignBadge = d.aligned
      ? '<span class="inline-block bg-green-50 text-green-700 text-[11px] px-1.5 py-0.5 rounded">ALIGNED</span>'
      : '<span class="inline-block bg-red-50 text-red-700 text-[11px] px-1.5 py-0.5 rounded">CONFLICTS</span>';
    lines.push(`<span class="font-semibold">Goal alignment:</span> ${alignBadge}`);
  }
  if (d.goal_impacts && d.goal_impacts.length) {
    d.goal_impacts.forEach(g => {
      lines.push(`<span class="font-semibold">${esc(g.goal)}:</span> ${esc(g.status)} — ${esc(g.detail)}`);
    });
  }
  if (d.analysis) {
    lines.push(`<span class="font-semibold">Analysis:</span> <span class="italic">${esc(d.analysis)}</span>`);
  }

  // Tradeoffs agent
  if (d.cuts && d.cuts.length) {
    lines.push(`<span class="font-semibold">Potential cuts:</span>`);
    d.cuts.forEach(c => {
      lines.push(`&nbsp;&nbsp;• ${esc(c.category)}: cut $${c.suggested_cut.toLocaleString("en-US", {minimumFractionDigits: 2})} from $${c.current_spend.toLocaleString("en-US", {minimumFractionDigits: 2})}`);
    });
  }
  if (d.lowest_impact) {
    lines.push(`<span class="font-semibold">Lowest impact:</span> ${esc(d.lowest_impact)}`);
  }
  if (d.alternatives && d.alternatives.length) {
    lines.push(`<span class="font-semibold">Alternatives:</span>`);
    d.alternatives.forEach(a => {
      lines.push(`&nbsp;&nbsp;• ${esc(a)}`);
    });
  }

  // Response synthesis agent
  if (d.response_length !== undefined) {
    lines.push(`<span class="font-semibold">Response:</span> ${d.response_length} chars, channel: ${esc(d.channel)}, using ${d.history_messages} history message(s)`);
  }

  return lines.map(l => `<p class="text-xs text-gray-600">${l}</p>`).join("");
}

function toggleDetail(header) {
  const body = header.nextElementSibling;
  const chevron = header.querySelector(".detail-chevron");
  body.classList.toggle("open");
  chevron.style.transform = body.classList.contains("open") ? "rotate(180deg)" : "";
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

  // Show running state in chat reasoning panel
  const chatReasoning = document.getElementById("chat-reasoning");
  chatReasoning.innerHTML = `
    <div class="flex items-center gap-3 text-sm text-gray-500">
      <svg class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
      </svg>
      Agents reasoning...
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

    // Render chat reasoning trace
    const trace = data.trace || [];
    chatReasoning.innerHTML = "";
    for (let i = 0; i < trace.length; i++) {
      const el = buildTraceStep(i + 1, trace[i]);
      chatReasoning.appendChild(el);
      setTimeout(() => el.classList.add("visible"), i * 300);
    }
  } catch {
    removeTypingIndicator();
    appendChatBubble("assistant", "Sorry, something went wrong.");
    chatReasoning.innerHTML = '<p class="text-sm text-red-500">Reasoning trace unavailable.</p>';
  }
  scrollChat();
}

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

// ── Helpers ────────────────────────────────────────────────────────

function formatMoney(n) {
  return "$" + Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function esc(str) {
  const d = document.createElement("div");
  d.textContent = String(str || "");
  return d.innerHTML;
}

function gaugeColor(score) {
  if (score >= 75) return "#ef4444";
  if (score >= 50) return "#f97316";
  if (score >= 25) return "#eab308";
  return "#22c55e";
}

function riskBadgeColor(level) {
  const m = { critical: "bg-red-100 text-red-700", high: "bg-orange-100 text-orange-700", medium: "bg-yellow-100 text-yellow-700", low: "bg-green-100 text-green-700" };
  return m[level] || "bg-gray-100 text-gray-600";
}

function severityDot(s) {
  const m = { critical: "bg-red-500", high: "bg-orange-500", medium: "bg-yellow-500", low: "bg-green-500" };
  return m[s] || "bg-gray-400";
}

function severityText(s) {
  const m = { critical: "text-red-600", high: "text-orange-600", medium: "text-yellow-600", low: "text-green-600" };
  return m[s] || "text-gray-500";
}
