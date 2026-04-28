/* =====================================================
   Permear · IF Baiano — Frontend JS (vanilla)
   Mantém compatibilidade com todas as rotas Flask
   ===================================================== */

let nomePlanilha = "";
let modoAutomatico = false;
let casasDecimaisDisplay = 2;
let conexaoOnline = null;
let totalAmostras = 0;
let confirmCallback = null;
let medindo = false;          // controla se gráfico/contador estão ativos
let medicaoStartMs = 0;       // tempo de início da medição (para eixo X em segundos)

/* ==================== TOASTS ==================== */
function showToast(message, level = "info", title = null, timeout = 4200) {
  const stack = document.getElementById("toast-stack");
  if (!stack) return;
  const t = document.createElement("div");
  t.className = `toast ${level}`;
  const titles = { info: "Informação", success: "Sucesso", warning: "Atenção", error: "Erro" };
  t.innerHTML = `
    <div style="flex:1;min-width:0">
      <div class="toast__title">${title || titles[level] || "Aviso"}</div>
      <div class="toast__msg"></div>
    </div>`;
  t.querySelector(".toast__msg").textContent = message;
  stack.appendChild(t);
  setTimeout(() => {
    t.classList.add("is-leaving");
    setTimeout(() => t.remove(), 220);
  }, timeout);
}

/* ==================== CONFIRMAÇÃO ==================== */
function confirmarAcao(mensagem) {
  return new Promise((resolve) => {
    const modal = document.getElementById("modal-confirm");
    document.getElementById("confirm-message").textContent = mensagem;
    confirmCallback = resolve;
    modal.classList.add("is-open");
  });
}
function fecharConfirmacao(ok) {
  const modal = document.getElementById("modal-confirm");
  modal.classList.remove("is-open");
  if (confirmCallback) {
    confirmCallback(ok);
    confirmCallback = null;
  }
}

/* ==================== STATUS / FEEDBACK ==================== */
function atualizarFeedbackUI(mensagem, nivel = "info", horario = "") {
  const statusBox = document.getElementById("status-box");
  const statusText = document.getElementById("status-text");
  const statusTime = document.getElementById("status-time");
  if (!statusBox || !statusText) return;

  statusText.textContent = mensagem || "Sem mensagens no momento.";
  statusBox.className = `status-box ${nivel || "info"}`;
  if (statusTime && horario) statusTime.textContent = horario;
}

function setConexao(online) {
  if (conexaoOnline === online) return;
  conexaoOnline = online;
  const pill = document.getElementById("connection-pill");
  const label = document.getElementById("connection-label");
  if (!pill || !label) return;
  pill.classList.toggle("is-online", online);
  pill.classList.toggle("is-offline", !online);
  label.textContent = online ? "Conectado" : "Sem conexão";
}

/* ==================== MEDIÇÃO (modal) ==================== */
async function carregarPlanilhasNoSelect() {
  const res = await fetch("/planilhas");
  const planilhas = await res.json();
  const select = document.getElementById("planilhas-select");
  const input = document.getElementById("nova-planilha");
  const campoNome = document.getElementById("campo-nome-planilha");

  select.innerHTML = '<option value="">— criar nova planilha —</option>';
  planilhas.forEach(p => {
    const option = document.createElement("option");
    option.value = p; option.textContent = p;
    select.appendChild(option);
  });

  input.value = "";
  campoNome.style.display = "block";
  document.getElementById("responsavel").value = "";
  document.getElementById("coordenadas").value = "";
  document.getElementById("descricao").value = "";
}

function abrirModalMedicao() {
  document.getElementById("modal").classList.add("is-open");
  setTimeout(() => document.getElementById("nova-planilha").focus(), 80);
}

async function iniciarMedicao() {
  modoAutomatico = false;
  await carregarPlanilhasNoSelect();
  abrirModalMedicao();
}

async function iniciarMedicaoAutomatica() {
  modoAutomatico = true;
  await carregarPlanilhasNoSelect();
  abrirModalMedicao();
}

function alternarCampoNome() {
  const select = document.getElementById("planilhas-select");
  const campo = document.getElementById("campo-nome-planilha");
  campo.style.display = select.value ? "none" : "block";
}

function fecharModal() {
  document.getElementById("modal").classList.remove("is-open");
}

function confirmarEscolha() {
  const select = document.getElementById("planilhas-select");
  const input = document.getElementById("nova-planilha");
  const valor = input.value.trim();
  nomePlanilha = select.value || (valor ? valor + ".ods" : "");

  if (!nomePlanilha || nomePlanilha === ".ods") {
    showToast("Informe um nome válido para a planilha.", "warning");
    return;
  }

  fecharModal();

  if (modoAutomatico) {
    iniciarMedicaoAutomaticaBackend(nomePlanilha);
  } else {
    iniciarMedicaoBackend(nomePlanilha);
  }
}

async function iniciarMedicaoBackend(planilha) {
  const responsavel = document.getElementById("responsavel").value.trim();
  const coordenadas = document.getElementById("coordenadas").value.trim();
  const descricao = document.getElementById("descricao").value.trim();

  try {
    const res = await fetch('/start', {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ planilha, responsavel, coordenadas, descricao })
    });
    const data = await res.json();
    showToast(data.status || "Medição iniciada.", "success");
    setReadingMode("manual");
    iniciarColetaGrafico();
  } catch (e) {
    showToast("Falha ao iniciar a medição manual.", "error");
  }
}

async function iniciarMedicaoAutomaticaBackend(planilha) {
  const responsavel = document.getElementById("responsavel").value.trim();
  const coordenadas = document.getElementById("coordenadas").value.trim();
  const descricao = document.getElementById("descricao").value.trim();

  try {
    const res = await fetch('/start_auto', {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ planilha, responsavel, coordenadas, descricao })
    });
    const data = await res.json();
    showToast(data.status || "Medição automática iniciada.", "success");
    setReadingMode("auto");
    iniciarColetaGrafico();
  } catch (e) {
    showToast("Falha ao iniciar a medição automática.", "error");
  }
}

async function finalizarMedicao() {
  try {
    const res = await fetch("/stop", { method: "POST" });
    const data = await res.json();
    showToast(data.status || "Medição finalizada e planilha salva.", "success");
    setReadingMode("idle");
    pararColetaGrafico();
  } catch (e) {
    showToast("Erro ao finalizar a medição.", "error");
  }
}

async function pararMedicaoAutomatica() {
  try {
    const res = await fetch("/stop_auto", { method: "POST" });
    const data = await res.json();
    showToast(data.status || "Medição automática parada.", "warning");
    setReadingMode("idle");
    pararColetaGrafico();
  } catch (e) {
    showToast("Erro ao parar a medição automática.", "error");
  }
}

/* ==================== HARDWARE ==================== */
async function ajustarOffset() {
  showToast("Ajustando offset do sensor...", "info");
  try {
    const res = await fetch("/ajustar_offset", { method: "POST", headers: { "Content-Type": "application/json" } });
    const data = await res.json();
    showToast(data.status, "success");
  } catch (e) {
    showToast("Erro ao ajustar o offset.", "error");
  }
}

function calibrarCilindro() {
  const btn = document.getElementById("calibrar-btn");
  if (btn) btn.disabled = true;
  fetch("/calibrar_cilindro", { method: "POST", headers: { "Content-Type": "application/json" } })
    .then(r => r.json())
    .then(d => showToast(d.status, "info"))
    .catch(() => showToast("Erro ao iniciar a calibração.", "error"))
    .finally(() => { if (btn) btn.disabled = false; });
}

function esvaziarCilindro() {
  const btn = document.getElementById("esvaziar-btn");
  if (btn) btn.disabled = true;
  fetch("/esvaziar_cilindro", { method: "POST", headers: { "Content-Type": "application/json" } })
    .then(r => r.json())
    .then(d => showToast(d.status, "info"))
    .catch(() => showToast("Erro ao esvaziar o cilindro.", "error"))
    .finally(() => { if (btn) btn.disabled = false; });
}

/* ==================== PLANILHAS ==================== */
function abrirModalPlanilhas() {
  fetch('/planilhas')
    .then(res => res.json())
    .then(planilhas => {
      const lista = document.getElementById("lista-planilhas");
      lista.innerHTML = "";
      if (!planilhas.length) {
        lista.innerHTML = "<li class='lista-vazia'>Nenhuma planilha encontrada.</li>";
      } else {
        planilhas.forEach(p => {
          const item = document.createElement("li");
          item.className = "planilha-item";
          const link = document.createElement("a");
          link.href = `/download/${encodeURIComponent(p)}`;
          link.textContent = p;
          link.className = "planilha-link";
          link.target = "_blank";
          link.rel = "noopener";
          item.appendChild(link);
          lista.appendChild(item);
        });
      }
      document.getElementById("modal-planilhas").classList.add("is-open");
    })
    .catch(() => showToast("Não foi possível carregar a lista de planilhas.", "error"));
}
function fecharModalPlanilhas() {
  document.getElementById("modal-planilhas").classList.remove("is-open");
}

/* ==================== CONFIG ==================== */
function abrirModalConfig() {
  fetch("/config")
    .then(res => res.json())
    .then(config => {
      const set = (id, v) => { const el = document.getElementById(id); if (el != null && v != null) el.value = v; };
      set("config-cilindroAr", config.cilindroAr);
      set("config-alturaCilindro", config.alturaCilindro);
      set("config-diametroCilindro", config.diametroCilindro);
      set("config-pressao", config.pressaoAtmosferica);
      set("config-pressao-calibracao-max", config.pressaoCalibracaoMaxima);
      document.getElementById("config-modo-compressor").value = config.modoCompressorCalibracao || "intervalado";
      set("config-tempo-intervalo-compressor", config.tempoIntervaloCompressor ?? 0.3);
      set("config-pressao-final", config.pressaoFinalMedicao);
      set("config-pressao-auto-min", config.pressaoAutoMinima);
      set("config-pressao-auto-max", config.pressaoAutoMaxima);
      set("config-janela-estabilizacao", config.janelaLeituraEstabilizacao);
      set("config-variacao-estabilizacao", config.variacaoEstabilizacaoPa);
      set("config-timeout-estabilizacao", config.timeoutEstabilizacao);
      set("config-tempo-esvaziamento", config.tempoEsvaziamentoCilindro);
      set("config-casas-decimais", config.casasDecimaisDisplay);
      set("config-tempo-offset", config.tempoCalculoOffset);
      atualizarCampoIntervaloCompressor();
    });
  document.getElementById("modal-config").classList.add("is-open");
}

function atualizarCampoIntervaloCompressor() {
  const modo = document.getElementById("config-modo-compressor").value;
  const campoIntervalo = document.getElementById("config-tempo-intervalo-compressor");
  const ativo = modo === "intervalado";
  campoIntervalo.disabled = !ativo;
  campoIntervalo.style.opacity = ativo ? "1" : "0.55";
}

function fecharModalConfig() {
  document.getElementById("modal-config").classList.remove("is-open");
}

function salvarConfiguracoes() {
  const num = id => parseFloat(document.getElementById(id).value);
  const int = id => parseInt(document.getElementById(id).value, 10);
  const config = {
    cilindroAr: num("config-cilindroAr"),
    alturaCilindro: num("config-alturaCilindro"),
    diametroCilindro: num("config-diametroCilindro"),
    pressaoAtmosferica: num("config-pressao"),
    pressaoCalibracaoMaxima: num("config-pressao-calibracao-max"),
    modoCompressorCalibracao: document.getElementById("config-modo-compressor").value,
    tempoIntervaloCompressor: num("config-tempo-intervalo-compressor"),
    pressaoFinalMedicao: num("config-pressao-final"),
    pressaoAutoMinima: num("config-pressao-auto-min"),
    pressaoAutoMaxima: num("config-pressao-auto-max"),
    janelaLeituraEstabilizacao: int("config-janela-estabilizacao"),
    variacaoEstabilizacaoPa: num("config-variacao-estabilizacao"),
    timeoutEstabilizacao: int("config-timeout-estabilizacao"),
    tempoEsvaziamentoCilindro: num("config-tempo-esvaziamento"),
    casasDecimaisDisplay: int("config-casas-decimais"),
    tempoCalculoOffset: num("config-tempo-offset")
  };

  fetch("/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config)
  })
    .then(r => r.json())
    .then(d => {
      casasDecimaisDisplay = Number.isInteger(config.casasDecimaisDisplay) ? config.casasDecimaisDisplay : 2;
      showToast(d.status || "Configurações salvas.", "success");
      fecharModalConfig();
    })
    .catch(() => showToast("Erro ao salvar as configurações.", "error"));
}

/* ==================== SISTEMA ==================== */
async function reiniciarPermeametro() {
  const ok = await confirmarAcao("Deseja reiniciar o serviço do permeâmetro agora?");
  if (!ok) return;
  fetch("/restart_service", { method: "POST", headers: { "Content-Type": "application/json" } })
    .then(r => r.json())
    .then(d => showToast(d.status, "warning"))
    .catch(() => showToast("Erro ao reiniciar o serviço.", "error"));
}

async function desligarSistema() {
  const ok = await confirmarAcao("Deseja desligar o sistema agora? Esta ação encerrará o Raspberry Pi.");
  if (!ok) return;
  fetch("/shutdown", { method: "POST", headers: { "Content-Type": "application/json" } })
    .then(r => r.json())
    .then(d => showToast(d.status, "warning"))
    .catch(() => showToast("Erro ao desligar o sistema.", "error"));
}

/* ==================== LEITURA + GRÁFICO ==================== */
function setReadingMode(mode) {
  const chip = document.getElementById("reading-mode-chip");
  const kpi = document.getElementById("kpi-modo");
  const map = {
    manual: { txt: "Medindo · Manual", k: "Manual" },
    auto:   { txt: "Medindo · Automático", k: "Automático" },
    idle:   { txt: "Aguardando", k: "—" }
  };
  const m = map[mode] || map.idle;
  if (chip) chip.textContent = m.txt;
  if (kpi)  kpi.textContent  = m.k;
}

/* ==================== GRÁFICO ==================== */
const chartState = {
  ctx: null, canvas: null, dpr: 1,
  points: [],          // { t: segundos, p: pressão Pa }
  maxPoints: 600,      // até 10 minutos a 1 Hz
};

function setupChart() {
  const c = document.getElementById("liveChart");
  if (!c) return;
  chartState.canvas = c;
  chartState.ctx = c.getContext("2d");
  resizeChart();
  window.addEventListener("resize", resizeChart);
}
function resizeChart() {
  const c = chartState.canvas; if (!c) return;
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth; const h = c.clientHeight || 200;
  c.width = Math.round(w * dpr);
  c.height = Math.round(h * dpr);
  chartState.dpr = dpr;
  drawChart();
}
function resetChart() { chartState.points = []; drawChart(); }

function iniciarColetaGrafico() {
  medindo = true;
  totalAmostras = 0;
  medicaoStartMs = Date.now();
  chartState.points = [];
  const ka = document.getElementById("kpi-amostras");
  if (ka) ka.textContent = "0";
  const item = document.getElementById("kpi-amostras-item");
  if (item) item.hidden = false;
  drawChart();
}
function pararColetaGrafico() {
  medindo = false;
  const item = document.getElementById("kpi-amostras-item");
  if (item) item.hidden = true;
  // mantém os pontos no gráfico após parar; serão limpos no próximo iniciar
}

function pushChart(value) {
  if (!Number.isFinite(value)) return;
  const t = (Date.now() - medicaoStartMs) / 1000;
  chartState.points.push({ t, p: value });
  if (chartState.points.length > chartState.maxPoints) chartState.points.shift();
  drawChart();
}

function getCssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function drawChart() {
  const ctx = chartState.ctx; const c = chartState.canvas;
  if (!ctx || !c) return;
  const dpr = chartState.dpr;
  const W = c.width, H = c.height;
  ctx.clearRect(0, 0, W, H);

  const padL = 56 * dpr, padR = 14 * dpr, padT = 14 * dpr, padB = 38 * dpr;
  const w = W - padL - padR, h = H - padT - padB;

  const colGrid  = getCssVar("--chart-grid",  "rgba(255,255,255,0.07)");
  const colAxis  = getCssVar("--chart-axis",  "rgba(154,167,192,0.85)");
  const colLine  = getCssVar("--chart-line",  "#4ea1ff");
  const colFill0 = getCssVar("--chart-fill-top", "rgba(78,161,255,0.35)");
  const colFill1 = getCssVar("--chart-fill-bot", "rgba(78,161,255,0.02)");

  const data = chartState.points;
  const empty = data.length === 0;

  // Domínios
  const ps = data.map(d => d.p);
  const ts = data.map(d => d.t);
  const pMin = empty ? 0    : Math.min(...ps);
  const pMax = empty ? 1000 : Math.max(...ps);
  const pSpan = Math.max(1, pMax - pMin);
  const yMin = empty ? 0    : pMin - pSpan * 0.1;
  const yMax = empty ? 1000 : pMax + pSpan * 0.1;
  const tMin = empty ? 0 : ts[0];
  const tMax = empty ? 60 : Math.max(ts[ts.length - 1], tMin + 1);
  const tSpan = tMax - tMin;

  // Grid horizontal
  ctx.strokeStyle = colGrid;
  ctx.lineWidth = 1 * dpr;
  for (let i = 0; i <= 4; i++) {
    const y = padT + (h * i / 4);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + w, y); ctx.stroke();
  }
  // Grid vertical (5 divisões)
  for (let i = 0; i <= 5; i++) {
    const x = padL + (w * i / 5);
    ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, padT + h); ctx.stroke();
  }

  // Labels eixo Y (pressão)
  ctx.fillStyle = colAxis;
  ctx.font = `${11 * dpr}px "JetBrains Mono", monospace`;
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (let i = 0; i <= 4; i++) {
    const v = yMax - ((yMax - yMin) * i / 4);
    ctx.fillText(v.toFixed(0), padL - 8 * dpr, padT + (h * i / 4));
  }

  // Labels eixo X (tempo)
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  for (let i = 0; i <= 5; i++) {
    const tv = tMin + (tSpan * i / 5);
    ctx.fillText(tv.toFixed(0), padL + (w * i / 5), padT + h + 6 * dpr);
  }

  // Títulos dos eixos
  ctx.font = `${11 * dpr}px "Inter", sans-serif`;
  ctx.fillStyle = colAxis;
  ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
  ctx.fillText("tempo (s)", padL + w / 2, H - 8 * dpr);

  // Eixo Y rotacionado
  ctx.save();
  ctx.translate(14 * dpr, padT + h / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText("pressão (Pa)", 0, 0);
  ctx.restore();

  if (empty) {
    ctx.fillStyle = colAxis;
    ctx.font = `${12 * dpr}px "Inter", sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("Aguardando início da medição…", padL + w / 2, padT + h / 2);
    return;
  }

  if (data.length < 1) return;

  const xOf = (t) => padL + ((t - tMin) / (tSpan || 1)) * w;
  const yOf = (p) => padT + ((yMax - p) / (yMax - yMin)) * h;
  const points = data.map(d => ({ x: xOf(d.t), y: yOf(d.p) }));

  // Área
  if (points.length >= 2) {
    const grad = ctx.createLinearGradient(0, padT, 0, padT + h);
    grad.addColorStop(0, colFill0);
    grad.addColorStop(1, colFill1);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.moveTo(points[0].x, padT + h);
    points.forEach(p => ctx.lineTo(p.x, p.y));
    ctx.lineTo(points[points.length - 1].x, padT + h);
    ctx.closePath(); ctx.fill();

    // Linha
    ctx.strokeStyle = colLine;
    ctx.lineWidth = 2 * dpr;
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    ctx.beginPath();
    points.forEach((p, i) => i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y));
    ctx.stroke();
  }

  // Pontos individuais (bolinhas em cada amostra)
  ctx.fillStyle = colLine;
  const r = (points.length > 120 ? 1.5 : 2.5) * dpr;
  points.forEach(p => {
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fill();
  });

  // Halo no último ponto
  const last = points[points.length - 1];
  ctx.fillStyle = colLine;
  ctx.beginPath(); ctx.arc(last.x, last.y, 3.5 * dpr, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = colLine + "55";
  ctx.lineWidth = 1.5 * dpr;
  ctx.beginPath(); ctx.arc(last.x, last.y, 7 * dpr, 0, Math.PI * 2); ctx.stroke();
}

/* ==================== POLLING ==================== */
function atualizarPressao() {
  fetch("/get_pressure")
    .then(r => { if (!r.ok) throw new Error("offline"); return r.json(); })
    .then(data => {
      setConexao(true);
      if (typeof data.pressao !== "number") return;
      const casas = Number.isInteger(casasDecimaisDisplay) ? casasDecimaisDisplay : 2;
      document.getElementById("pressure").textContent = data.pressao.toFixed(casas);
      const k = document.getElementById("kpi-ultima");
      if (k) k.textContent = data.pressao.toFixed(casas) + " Pa";

      // Gráfico e contador de amostras só durante medição
      if (medindo) {
        pushChart(data.pressao);
        totalAmostras++;
        const ka = document.getElementById("kpi-amostras");
        if (ka) ka.textContent = totalAmostras.toString();
      }
    })
    .catch(() => setConexao(false));
}

function atualizarStatusSistema() {
  fetch("/status")
    .then(r => r.json())
    .then(d => atualizarFeedbackUI(d.mensagem, d.nivel, d.atualizado_em))
    .catch(() => {});
}

function carregarConfiguracaoDisplay() {
  fetch("/config")
    .then(res => res.json())
    .then(config => {
      const casas = parseInt(config.casasDecimaisDisplay, 10);
      casasDecimaisDisplay = Number.isInteger(casas) ? casas : 2;
    })
    .catch(() => { casasDecimaisDisplay = 2; });
}

/* ==================== TEMA (claro/escuro) ==================== */
const THEME_KEY = "permeametro-theme";
function aplicarTema(theme) {
  const t = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", t);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", t === "light" ? "#f4f6fb" : "#0b1220");
  // Troca a logo conforme o tema (branca no escuro, colorida no claro)
  const logo = document.getElementById("brand-logo");
  if (logo) {
    logo.src = t === "light"
      ? "/static/img/logo_ifbaiano_colorida.png"
      : "/static/img/logo_ifbaiano_branca.png";
  }
  try { localStorage.setItem(THEME_KEY, t); } catch(e) {}
  // Redesenha o gráfico para pegar as novas cores via CSS vars
  if (typeof drawChart === "function") drawChart();
}
function alternarTema() {
  const atual = document.documentElement.getAttribute("data-theme") || "dark";
  aplicarTema(atual === "light" ? "dark" : "light");
}
function inicializarTema() {
  let saved = null;
  try { saved = localStorage.getItem(THEME_KEY); } catch(e) {}
  if (saved === "light" || saved === "dark") {
    aplicarTema(saved);
  } else {
    const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
    aplicarTema(prefersLight ? "light" : "dark");
  }
}

/* ==================== INIT ==================== */
document.addEventListener("DOMContentLoaded", () => {
  inicializarTema();
  setupChart();
  carregarConfiguracaoDisplay();
  document.getElementById("config-modo-compressor")?.addEventListener("change", atualizarCampoIntervaloCompressor);
  document.getElementById("theme-toggle")?.addEventListener("click", alternarTema);

  // Fecha modais com ESC
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      ["modal", "modal-planilhas", "modal-config", "modal-confirm"].forEach(id => {
        const m = document.getElementById(id);
        if (m && m.classList.contains("is-open")) {
          if (id === "modal-confirm") fecharConfirmacao(false);
          else m.classList.remove("is-open");
        }
      });
    }
  });

  setReadingMode("idle");
  // Garante que KPI de amostras começa oculto
  const item = document.getElementById("kpi-amostras-item");
  if (item) item.hidden = true;

  atualizarStatusSistema();
  atualizarPressao();
  setInterval(atualizarPressao, 1000);
  setInterval(atualizarStatusSistema, 1000);
});
