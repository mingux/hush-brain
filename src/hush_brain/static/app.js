/* HUSH BRAIN — the construct. Digital rain, boot sequence, live WebSocket feed. */

// ---------- digital rain ----------
const canvas = document.getElementById("rain");
const ctx = canvas.getContext("2d");
const GLYPHS = "アイウエオカキクケコサシスセソタチツテトナニヌネノ0123456789HUSHBRAIN";
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let columns = [];
let rainTimer = null;

function resizeRain() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  const count = Math.floor(canvas.width / 16);
  columns = Array.from({ length: count }, () => Math.floor(Math.random() * canvas.height / 16));
}
window.addEventListener("resize", resizeRain);
resizeRain();

function rainFrame() {
  ctx.fillStyle = "rgba(0, 5, 2, 0.08)";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.font = "14px monospace";
  columns.forEach((y, i) => {
    const glyph = GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
    ctx.fillStyle = Math.random() > 0.975 ? "#c8ffdb" : "#00ff41";
    ctx.fillText(glyph, i * 16, y * 16);
    columns[i] = y * 16 > canvas.height && Math.random() > 0.975 ? 0 : y + 1;
  });
}

function startRain() {
  if (reducedMotion || rainTimer) return;
  rainTimer = setInterval(rainFrame, 55);
}
function stopRain() {
  clearInterval(rainTimer);
  rainTimer = null;
}
startRain();
document.addEventListener("visibilitychange", () => (document.hidden ? stopRain() : startRain()));

// ---------- boot sequence ----------
const BOOT_LINES = [
  "wake up...",
  "the construct is loading",
  "> mounting brain vault .......... ok",
  "> starting event bus ............ ok",
  "> resolving provider ............ ok",
  "> opening the feed .............. ok",
  "",
  "follow the white rabbit.",
];
const bootText = document.getElementById("boot-text");

function finishBoot() {
  document.getElementById("boot").classList.add("fade");
  document.getElementById("construct").classList.remove("hidden");
  sessionStorage.setItem("hush-booted", "1");
}

if (reducedMotion || sessionStorage.getItem("hush-booted")) {
  finishBoot(); // boot plays once per tab session; skippable, never a toll
} else {
  let bootLine = 0;
  const bootTimer = setInterval(() => {
    if (bootLine >= BOOT_LINES.length) {
      clearInterval(bootTimer);
      finishBoot();
      return;
    }
    bootText.textContent += BOOT_LINES[bootLine] + "\n";
    bootLine++;
  }, 220);
  const skip = () => {
    clearInterval(bootTimer);
    finishBoot();
  };
  document.getElementById("boot").addEventListener("click", skip);
  document.addEventListener("keydown", skip, { once: true });
}

// ---------- state ----------
const $ = (id) => document.getElementById(id);
let eventCount = 0;
let tokens = { input_tokens: 0, output_tokens: 0 };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtTime(ts) {
  return new Date(ts * 1000).toTimeString().slice(0, 8);
}

// ---------- agents ----------
async function refreshAgents() {
  const agents = await fetch("/api/agents").then((r) => r.json());
  $("agents").innerHTML = agents
    .map((a) => {
      const stop = ["running", "sleeping", "spawning"].includes(a.status)
        ? `<button class="stop" onclick="stopAgent(${a.id})">stop</button>` : "";
      const err = a.error ? `<div class="meta" style="color:#ff4444">${esc(a.error)}</div>` : "";
      const sched = a.mode === "scheduled"
        ? ` · cycle ${a.cycles}${a.next_run ? " · next " + fmtTime(a.next_run) : ""}` : "";
      return `<div class="agent">
        <div class="row"><span class="name">${esc(a.name)}</span>
          <span><span class="status ${esc(a.status)}">${esc(a.status)}</span> ${stop}</span></div>
        <div class="meta">${esc(a.mode)}${sched} · tokens ${a.input_tokens + a.output_tokens} · ${esc(JSON.stringify(a.params)).slice(0, 60)}</div>
        ${err}</div>`;
    })
    .join("") || '<div class="meta" style="color:#00b32d">no programs loaded. spawn one.</div>';
}
window.stopAgent = async (id) => {
  await fetch(`/api/agents/${id}/stop`, { method: "POST" });
  refreshAgents();
};

$("spawn-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const kind = $("spawn-kind").value;
  const arg = $("spawn-arg").value.trim();
  const keyByKind = { oracle: "question", seeker: "topic", sentinel: "path", architect: "goal" };
  const params = arg ? { [keyByKind[kind]]: arg } : {};
  const every = $("spawn-every").value.trim();
  if (every) params.every = every;
  const res = await fetch("/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, params }),
  });
  const errBox = $("spawn-error");
  if (res.ok) {
    $("spawn-arg").value = "";
    $("spawn-every").value = "";
    errBox.textContent = "";
  } else {
    errBox.textContent = "✕ " + ((await res.json()).detail || "spawn failed");
  }
  refreshAgents();
});

// ---------- feed ----------
function eventLine(ev) {
  const p = ev.payload || {};
  let body = p.text || p.title || p.query || p.error || p.hook_event || "";
  if (ev.kind === "llm.call") body = `${p.provider} · in ${p.input_tokens} / out ${p.output_tokens} tok`;
  if (ev.kind === "brain.recall" && p.hits) body = `"${p.query}" → ${p.hits.length ? p.hits.map((h) => `[[${h}]]`).join(" ") : "no hits"}`;
  if (ev.kind === "hook.claude") body = `${p.hook_event}${p.tool_name ? " · " + p.tool_name : ""}`;
  const kindClass = "kind-" + ev.kind.replace(/\./g, "-");
  return `<div class="ev ${kindClass}" data-agent="${esc(ev.agent)}" data-kind="${esc(ev.kind)}">
    <span class="t">${fmtTime(ev.ts)}</span><span class="a">${esc(ev.agent)}</span><span class="k">${esc(ev.kind)}</span>
    <span class="body">${esc(body).slice(0, 400)}</span></div>`;
}

function applyFilter() {
  const q = $("feed-filter").value.trim().toLowerCase();
  document.querySelectorAll("#feed .ev").forEach((el) => {
    const match = !q || el.dataset.agent.toLowerCase().includes(q) || el.dataset.kind.toLowerCase().includes(q);
    el.style.display = match ? "" : "none";
  });
}
$("feed-filter").addEventListener("input", applyFilter);

function pushEvent(ev) {
  const feed = $("feed");
  feed.insertAdjacentHTML("afterbegin", eventLine(ev));
  while (feed.children.length > 300) feed.removeChild(feed.lastChild);
  applyFilter();
  eventCount++;
  $("sys-events").textContent = eventCount;
  if (ev.kind === "llm.call") {
    tokens.input_tokens += ev.payload.input_tokens || 0;
    tokens.output_tokens += ev.payload.output_tokens || 0;
    $("sys-tokens").textContent = tokens.input_tokens + tokens.output_tokens;
  }
  if (ev.kind.startsWith("agent.")) refreshAgents();
  if (ev.kind.startsWith("brain.")) refreshBrain();
}

// ---------- brain ----------
async function refreshBrain() {
  const data = await fetch("/api/brain/hot").then((r) => r.json());
  $("hot-cache").textContent = data.hot;
  $("brain-memories").textContent = data.stats.memories;
  $("brain-hotwords").textContent = data.stats.hot_words;
}

$("recall-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("recall-q").value.trim();
  if (!q) return;
  const hits = await fetch(`/api/brain/recall?q=${encodeURIComponent(q)}`).then((r) => r.json());
  $("recall-results").innerHTML = hits.length
    ? hits.map((h) => `<div class="hit"><span class="slug">[[${esc(h.slug)}]]</span> ${esc(h.title)}<br>${esc(h.excerpt)}</div>`).join("")
    : '<div class="hit">the brain holds nothing on that. yet.</div>';
});

$("remember-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const title = $("mem-title").value.trim();
  const content = $("mem-content").value.trim();
  if (!title || !content) return;
  await fetch("/api/brain/remember", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, content }),
  });
  $("mem-title").value = "";
  $("mem-content").value = "";
  refreshBrain();
});

// ---------- websocket ----------
function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => {
    const link = $("sys-link");
    link.textContent = "JACKED IN";
    link.classList.remove("bad");
  };
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    if (data.type === "snapshot") {
      $("sys-provider").textContent = data.provider;
      $("sys-version").textContent = data.version;
      tokens = data.tokens;
      $("sys-tokens").textContent = tokens.input_tokens + tokens.output_tokens;
      eventCount = data.event_count;
      $("sys-events").textContent = eventCount;
      $("feed").innerHTML = data.events.map(eventLine).join("");
      refreshAgents();
      refreshBrain();
    } else if (data.type === "event") {
      pushEvent(data.event);
    }
  };
  ws.onclose = () => {
    const link = $("sys-link");
    link.textContent = "OFFLINE";
    link.classList.add("bad");
    setTimeout(connect, 2000); // reconnect with backoff
  };
}
connect();
