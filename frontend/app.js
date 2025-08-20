// frontend/app.js
// ============================================================================
// SPA leve em JS puro.
// Ajustes deste commit:
// - Overlay/Progress BAR apenas na importação de CSV.
// - Busy leve para outras ações (desabilita botões, sem overlay).
// - Botão "Limpar comparação".
// - Toast avisando quando arquivo foi importado.
// ============================================================================

// ------------- Elements -------------
const loginView  = document.getElementById("login-view");
const appView    = document.getElementById("app-view");
const loginForm  = document.getElementById("login-form");
const emailEl    = document.getElementById("email");
const passEl     = document.getElementById("password");
const loginError = document.getElementById("login-error");

const meName = document.getElementById("me-name");
const meRole = document.getElementById("me-role");
const logoutBtn = document.getElementById("logout");

const dateFrom = document.getElementById("date-from");
const dateTo   = document.getElementById("date-to");
const accountIdEl  = document.getElementById("account-id");
const campaignIdEl = document.getElementById("campaign-id");
const pageSizeEl = document.getElementById("page-size");
const applyBtn = document.getElementById("apply-filters");
const clearBtn = document.getElementById("clear-filters");

const thead = document.getElementById("table-head");
const tbody = document.getElementById("table-body");
const tfoot = document.getElementById("table-foot");

const prevBtn = document.getElementById("prev-page");
const nextBtn = document.getElementById("next-page");
const pageInfo = document.getElementById("page-info");

const exportLink = document.getElementById("export-csv");
const fileInput  = document.getElementById("csv-file");

const chips = document.querySelectorAll(".chipbar .chip");
const accountsDL  = document.getElementById("accounts");
const campaignsDL = document.getElementById("campaigns");

const toastEl = document.getElementById("toast");

// overlay EXCLUSIVO da importação
const importOverlay = document.getElementById("import-overlay");
const progressText  = document.getElementById("progress-text");
const progressBar   = document.getElementById("progress-bar");

// comparação
const dateFromA = document.getElementById("date-from-a");
const dateToA   = document.getElementById("date-to-a");
const dateFromB = document.getElementById("date-from-b");
const dateToB   = document.getElementById("date-to-b");
const compareBtn = document.getElementById("compare-btn");
const clearCompareBtn = document.getElementById("clear-compare");
const compareResult = document.getElementById("compare-result");

// ------------- State -------------
let currentSort = { by: null, dir: "asc" };
let pagination  = { page: 1, page_size: 50, total: 0 };
let dateBounds  = { min: null, max: null };

// ------------- Utils -------------
function show(view){ if(view==="login"){ loginView.classList.remove("hidden"); appView.classList.add("hidden"); } else { loginView.classList.add("hidden"); appView.classList.remove("hidden"); } }
function fmtISO(d){ return d.toISOString().slice(0,10); }
function startOfMonth(d){ return new Date(d.getFullYear(), d.getMonth(), 1); }
function endOfMonth(d){ return new Date(d.getFullYear(), d.getMonth()+1, 0); }
function addDays(d, n){ const x = new Date(d); x.setDate(x.getDate()+n); return x; }
function debounce(fn, ms=250){ let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; }

// Busy leve (sem overlay)
function setBusy(on=true){
  document.body.style.cursor = on ? "progress" : "default";
  for(const el of document.querySelectorAll("button, .upload, a.btn")) el.disabled = on;
}
let toastTimer=null;
function toast(msg, ms=2600){
  toastEl.textContent = msg;
  toastEl.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=> toastEl.classList.add("hidden"), ms);
}

// API helper
async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const j = await res.json(); if (j && j.error) msg = j.error; }
    catch { try { msg = `${msg} · ${(await res.text()).slice(0, 300)}`; } catch{} }
    throw new Error(msg);
  }
  return res.json();
}

// ------------- Bootstrap -------------
async function preloadDates(){
  try {
    const res = await fetch("/api/date-range", { credentials:"include" });
    if (!res.ok) return;
    const { min, max } = await res.json();
    dateBounds.min = min || null; dateBounds.max = max || null;

    const allInputs = [dateFrom, dateTo, dateFromA, dateToA, dateFromB, dateToB];
    if(min) allInputs.forEach(i => i.min=min);
    if(max) allInputs.forEach(i => i.max=max);

    if(min) dateFrom.value=min;
    if(max) dateTo.value=max;
  } catch {}
}

async function init(){
  try {
    const data = await api("/api/me");
    if (data.user) {
      meName.textContent = data.user.username || data.user.email || "";
      meRole.textContent = data.user.role || "";
      show("app");
      await preloadDates();
      await loadTable();
      return;
    }
  } catch {}
  show("login");
}
init();

// ------------- Auth -------------
loginForm.addEventListener("submit", async (e)=>{
  e.preventDefault(); loginError.textContent = "";
  setBusy(true);
  try{
    const res = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ email: emailEl.value, password: passEl.value })
    });
    meName.textContent = res.user.username || res.user.email;
    meRole.textContent = res.user.role;
    show("app");
    pagination.page = 1;
    await preloadDates();
    await loadTable();
    toast("Login efetuado");
  } catch(err){
    loginError.textContent = err.message || "Credenciais inválidas";
  } finally { setBusy(false); }
});

logoutBtn.addEventListener("click", async ()=>{
  setBusy(true);
  try { await api("/api/logout", { method:"POST" }); show("login"); toast("Sessão encerrada"); }
  finally { setBusy(false); }
});

// ------------- Filtros -------------
applyBtn.addEventListener("click", ()=>{ pagination.page=1; loadTable(); });
clearBtn.addEventListener("click", ()=>{
  dateFrom.value=""; dateTo.value="";
  accountIdEl.value=""; campaignIdEl.value="";
  pageSizeEl.value=50; currentSort={by:null, dir:"asc"};
  pagination={ page:1, page_size:50, total:0 };
  loadTable();
});

chips.forEach(btn=>{
  btn.addEventListener("click", ()=>{
    const kind = btn.dataset.range;
    const today = new Date();
    switch(kind){
      case "all": if(dateBounds.min) dateFrom.value=dateBounds.min; if(dateBounds.max) dateTo.value=dateBounds.max; break;
      case "today": const t=fmtISO(today); dateFrom.value=t; dateTo.value=t; break;
      case "7d": dateTo.value=fmtISO(today); dateFrom.value=fmtISO(addDays(today,-6)); break;
      case "30d": dateTo.value=fmtISO(today); dateFrom.value=fmtISO(addDays(today,-29)); break;
      case "thisMonth": dateFrom.value=fmtISO(startOfMonth(today)); dateTo.value=fmtISO(endOfMonth(today)); break;
      case "lastMonth":
        const lmEnd=new Date(today.getFullYear(), today.getMonth(), 0);
        const lmStart=new Date(lmEnd.getFullYear(), lmEnd.getMonth(), 1);
        dateFrom.value=fmtISO(lmStart); dateTo.value=fmtISO(lmEnd); break;
    }
    pagination.page=1; loadTable();
  });
});

// autocomplete (datalist)
async function fillDatalist(field, q, targetDL){
  const params = new URLSearchParams({ field, q, limit:"50" }).toString();
  const res = await fetch(`/api/options?${params}`, { credentials:"include" });
  if(!res.ok) return;
  const { values } = await res.json();
  targetDL.innerHTML = "";
  (values || []).forEach(v => {
    const opt=document.createElement("option"); opt.value=v; targetDL.appendChild(opt);
  });
}
const debouncedAcc  = debounce(()=> fillDatalist("account_id",  accountIdEl.value.trim(),  accountsDL), 250);
const debouncedCamp = debounce(()=> fillDatalist("campaign_id", campaignIdEl.value.trim(), campaignsDL), 250);
accountIdEl.addEventListener("input", debouncedAcc);
campaignIdEl.addEventListener("input", debouncedCamp);

// Enter aplica filtros na view logada
document.addEventListener("keydown",(e)=>{
  if(e.key==="Enter" && !loginView.classList.contains("hidden")){
    e.preventDefault(); pagination.page=1; loadTable();
  }
});

// ------------- Paginação -------------
prevBtn.addEventListener("click", ()=>{ if(pagination.page>1){ pagination.page--; loadTable(); }});
nextBtn.addEventListener("click", ()=>{
  const last=Math.max(1, Math.ceil(pagination.total / pagination.page_size));
  if(pagination.page<last){ pagination.page++; loadTable(); }
});

// ------------- Export / Import -------------
exportLink.addEventListener("click",(e)=>{
  e.preventDefault();
  const params=buildParams();
  window.open(`/api/export?${params}`, "_blank");
});

// overlay exclusivo da importação
function showImportProgress(label, pct){
  importOverlay.classList.remove("hidden");
  importOverlay.setAttribute("aria-hidden","false");
  progressText.textContent = label + (typeof pct === "number" ? ` ${pct}%` : "");
  progressBar.style.width = typeof pct === "number" ? `${Math.max(1, Math.min(100, pct))}%` : "15%";
}
function hideImportProgress(){
  importOverlay.classList.add("hidden");
  importOverlay.setAttribute("aria-hidden","true");
  progressBar.style.width = "0%";
}

fileInput?.addEventListener("change", async (e)=>{
  const file = e.target.files?.[0];
  if (!file) return;

  try {
    // 1) inicia job_id
    const start = await fetch("/api/import-start", { method:"POST", credentials:"include" });
    const { job_id } = await start.json();
    if (!start.ok || !job_id) throw new Error("Falha ao iniciar importação.");

    // 2) envia com XHR para ter onprogress de upload
    const form = new FormData();
    form.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/import?job_id=${job_id}`);
    xhr.withCredentials = true;

    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) {
        const pct = Math.round((ev.loaded / ev.total) * 100);
        showImportProgress("Enviando arquivo…", pct);
      } else {
        showImportProgress("Enviando arquivo…", null);
      }
    };

    // 3) poll do backend para progresso de import
    let pollTimer = setInterval(async ()=>{
      try {
        const r = await fetch(`/api/import-progress?job_id=${job_id}`, { credentials:"include" });
        if (!r.ok) return;
        const s = await r.json();
        if (s.stage === "importing")       showImportProgress("Importando CSV…", s.pct ?? 0);
        else if (s.stage === "finalizing") showImportProgress("Finalizando…", 100);
        else if (s.stage === "done")       showImportProgress("Concluído", 100);
        else if (s.stage === "error")      showImportProgress("Erro na importação", 0);
      } catch {}
    }, 500);

    xhr.onload = async () => {
      clearInterval(pollTimer);
      try {
        const resp = JSON.parse(xhr.responseText || "{}");
        if (xhr.status >= 200 && xhr.status < 300) {
          await preloadDates();
          await loadTable();
          hideImportProgress();
          toast(resp.message || "Arquivo importado com sucesso.");
        } else {
          hideImportProgress();
          alert(resp.error || "Falha ao importar CSV.");
        }
      } catch {
        hideImportProgress();
        if (xhr.status < 200 || xhr.status >= 300) alert("Falha ao importar CSV.");
      }
      e.target.value = "";
    };

    xhr.onerror = () => {
      hideImportProgress();
      alert("Erro de rede ao enviar arquivo.");
      e.target.value = "";
    };

    showImportProgress("Preparando…", 0);
    xhr.send(form);

  } catch (err) {
    hideImportProgress();
    alert(err.message || "Erro ao iniciar importação.");
    e.target.value = "";
  }
});

// ------------- Data Loading -------------
function buildParams(){
  const params=new URLSearchParams();
  if(dateFrom.value) params.set("date_from", dateFrom.value);
  if(dateTo.value)   params.set("date_to",   dateTo.value);
  if(accountIdEl.value)  params.set("account_id",  accountIdEl.value.trim());
  if(campaignIdEl.value) params.set("campaign_id", campaignIdEl.value.trim());
  if(currentSort.by){ params.set("sort_by", currentSort.by); params.set("sort_dir", currentSort.dir); }
  const ps=parseInt(pageSizeEl.value||"50", 10);
  pagination.page_size = isNaN(ps) ? 50 : Math.max(1, Math.min(200, ps));
  params.set("page", pagination.page); params.set("page_size", pagination.page_size);
  return params.toString();
}

async function loadTable(){
  const params=buildParams();
  setBusy(true);
  try{
    const data=await api(`/api/data?${params}`);
    pagination.total=data.total||0;
    renderTable(data.rows||[], data.totals||{});
    const last=Math.max(1, Math.ceil(pagination.total / pagination.page_size));
    pageInfo.textContent = `Página ${data.page} de ${last} · ${pagination.total} itens`;
  } catch(err){
    console.error("Erro ao carregar dados:", err);
    thead.innerHTML=""; tfoot.innerHTML="";
    tbody.innerHTML=`<tr><td class="error">Erro ao carregar dados: ${err.message||err}</td></tr>`;
    pageInfo.textContent="";
  } finally { setBusy(false); }
}

function renderTable(rows, totals){
  tbody.innerHTML=""; thead.innerHTML=""; tfoot.innerHTML="";
  if(!rows || rows.length===0){ tbody.innerHTML="<tr><td>Nenhum dado</td></tr>"; return; }

  const columns = Object.keys(rows[0]);

  const trHead=document.createElement("tr");
  columns.forEach(col=>{
    const th=document.createElement("th"); th.textContent=col;
    th.addEventListener("click", ()=>{
      if(currentSort.by===col){ currentSort.dir = (currentSort.dir==="asc"?"desc":"asc"); }
      else { currentSort.by=col; currentSort.dir="asc"; }
      loadTable();
    });
    if(currentSort.by===col){ th.classList.add(currentSort.dir==="asc"?"sort-asc":"sort-desc"); }
    trHead.appendChild(th);
  });
  thead.appendChild(trHead);

  rows.forEach(row=>{
    const tr=document.createElement("tr");
    columns.forEach(col=>{
      const td=document.createElement("td");
      let value=row[col];
      if(col==="cost_micros" && value!=null){
        const num=Number(value);
        if(!isNaN(num)){
          const brl=num/1_000_000;
          value=new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(brl);
        }
      }
      td.textContent = value;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  const trFoot=document.createElement("tr");
  columns.forEach((col, idx)=>{
    const td=document.createElement("td");
    if(idx===0){ td.textContent="TOTAL (filtro)"; td.style.fontWeight="700"; }
    else if(["clicks","conversions","impressions","interactions"].includes(col)){
      const num=Number(totals[col]??0);
      td.textContent=new Intl.NumberFormat("pt-BR",{maximumFractionDigits:2}).format(num);
      td.style.fontWeight="700";
    } else if(col==="cost_micros" && totals.cost_micros!==undefined){
      const brl=(Number(totals.cost_micros||0))/1_000_000;
      td.textContent=new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(brl);
      td.style.fontWeight="700";
    } else { td.textContent=""; }
    trFoot.appendChild(td);
  });
  tfoot.appendChild(trFoot);
}

// ------------- Comparação -------------
compareBtn.addEventListener("click", async ()=>{
  if(!dateFromB.value || !dateToB.value){
    dateFromB.value = dateFrom.value || dateBounds.min || "";
    dateToB.value   = dateTo.value   || dateBounds.max || "";
  }
  if(!dateFromA.value || !dateToA.value){
    const bFrom = new Date(dateFromB.value);
    const bTo   = new Date(dateToB.value);
    if(!isNaN(bFrom) && !isNaN(bTo)){
      const days = Math.max(0, Math.round((bTo - bFrom)/(1000*60*60*24)));
      const aTo  = new Date(bFrom); aTo.setDate(aTo.getDate()-1);
      const aFrom= new Date(aTo);   aFrom.setDate(aFrom.getDate()-days);
      dateFromA.value = fmtISO(aFrom);
      dateToA.value   = fmtISO(aTo);
    }
  }

  const qs = new URLSearchParams({
    date_from_a: dateFromA.value || "",
    date_to_a:   dateToA.value   || "",
    date_from_b: dateFromB.value || "",
    date_to_b:   dateToB.value   || "",
  });
  if(accountIdEl.value)  qs.set("account_id",  accountIdEl.value.trim());
  if(campaignIdEl.value) qs.set("campaign_id", campaignIdEl.value.trim());

  setBusy(true);
  try{
    const res = await api(`/api/compare?${qs.toString()}`);
    renderCompare(res);
  } catch(err){
    compareResult.innerHTML = `<div class="error">Erro ao comparar: ${err.message||err}</div>`;
  } finally { setBusy(false); }
});

clearCompareBtn.addEventListener("click", ()=>{
  dateFromA.value=""; dateToA.value="";
  dateFromB.value=""; dateToB.value="";
  compareResult.innerHTML = "";
});

function renderCompare({ total_a, total_b, diff_abs, diff_pct }){
  const keys = ["clicks","conversions","impressions","interactions"]
    .concat(("cost_micros" in (total_a||{})) ? ["cost_micros"] : []);

  const fmtNum = n => new Intl.NumberFormat("pt-BR",{ maximumFractionDigits: 2 }).format(n||0);
  const fmtPct = n => (n===null || n===undefined) ? "—" :
    `${(n>=0?"+":"")}${new Intl.NumberFormat("pt-BR",{ maximumFractionDigits:1 }).format(n)}%`;
  const fmtBRL = micros => {
    const brl = (Number(micros||0))/1_000_000;
    return new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(brl);
  };

  let html = `
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Métrica</th>
            <th>Período A</th>
            <th>Período B</th>
            <th>Δ</th>
            <th>Δ%</th>
          </tr>
        </thead>
        <tbody>
  `;
  keys.forEach(k=>{
    const a = total_a?.[k] ?? 0;
    const b = total_b?.[k] ?? 0;
    const d = diff_abs?.[k] ?? 0;
    const p = diff_pct?.[k];
    const render = (k==="cost_micros") ? fmtBRL : fmtNum;
    const renderD = (k==="cost_micros") ? fmtBRL : fmtNum;
    const classDelta = d>0 ? 'pos' : (d<0 ? 'neg' : '');
    html += `
      <tr>
        <td>${k}</td>
        <td>${render(a)}</td>
        <td>${render(b)}</td>
        <td class="${classDelta}">${d>=0?"+":""}${renderD(d)}</td>
        <td class="${classDelta}">${fmtPct(p)}</td>
      </tr>
    `;
  });
  html += `</tbody></table></div>`;
  compareResult.innerHTML = html;
}
