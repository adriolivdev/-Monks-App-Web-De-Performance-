// frontend/app.js
// ============================================================================
// SPA leve em JS vanilla. Responsivo, com loading overlay, toasts,
// atalhos de período, autocomplete via datalist e totais no rodapé.
// ============================================================================

// -------------------- Elements --------------------
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
const accountsDL = document.getElementById("accounts");
const campaignsDL = document.getElementById("campaigns");

const overlay = document.getElementById("loading-overlay");
const toastEl = document.getElementById("toast");

// -------------------- State --------------------
let currentSort = { by: null, dir: "asc" };
let pagination  = { page: 1, page_size: 50, total: 0 };
let dateBounds  = { min: null, max: null };

// -------------------- Utils --------------------
function show(view){ if(view==="login"){ loginView.classList.remove("hidden"); appView.classList.add("hidden"); } else { loginView.classList.add("hidden"); appView.classList.remove("hidden"); } }
function fmtISO(d){ return d.toISOString().slice(0,10); }
function startOfMonth(d){ return new Date(d.getFullYear(), d.getMonth(), 1); }
function endOfMonth(d){ return new Date(d.getFullYear(), d.getMonth()+1, 0); }
function addDays(d, n){ const x = new Date(d); x.setDate(x.getDate()+n); return x; }
function debounce(fn, ms=250){ let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; }

function setLoading(on=true){
  overlay.classList.toggle("hidden", !on);
  overlay.setAttribute("aria-hidden", on ? "false":"true");
  for(const btn of document.querySelectorAll("button, .upload, a.btn")) btn.disabled = on;
}
let toastTimer=null;
function toast(msg, ms=2600){
  toastEl.textContent = msg;
  toastEl.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=> toastEl.classList.add("hidden"), ms);
}

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

// -------------------- Bootstrap --------------------
async function preloadDates(){
  try {
    const res = await fetch("/api/date-range", { credentials:"include" });
    if(!res.ok) return;
    const { min, max } = await res.json();
    dateBounds.min = min || null; dateBounds.max = max || null;
    if(min) dateFrom.min=min, dateTo.min=min;
    if(max) dateFrom.max=max, dateTo.max=max;
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

// -------------------- Auth --------------------
loginForm.addEventListener("submit", async (e)=>{
  e.preventDefault(); loginError.textContent = "";
  setLoading(true);
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
  } finally { setLoading(false); }
});

logoutBtn.addEventListener("click", async ()=>{
  setLoading(true);
  try { await api("/api/logout", { method:"POST" }); show("login"); toast("Sessão encerrada"); }
  finally { setLoading(false); }
});

// -------------------- Filtros / UX --------------------
applyBtn.addEventListener("click", ()=>{ pagination.page=1; loadTable(); });
clearBtn.addEventListener("click", ()=>{
  dateFrom.value=""; dateTo.value="";
  accountIdEl.value=""; campaignIdEl.value="";
  pageSizeEl.value=50; currentSort={by:null, dir:"asc"};
  pagination={ page:1, page_size:50, total:0 };
  loadTable();
});

// chips (atalhos de data)
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

// autocomplete com datalist
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

// Enter aplica filtros
document.addEventListener("keydown",(e)=>{
  if(e.key==="Enter" && !loginView.classList.contains("hidden")){
    e.preventDefault(); pagination.page=1; loadTable();
  }
});

// -------------------- Paginação --------------------
prevBtn.addEventListener("click", ()=>{ if(pagination.page>1){ pagination.page--; loadTable(); }});
nextBtn.addEventListener("click", ()=>{
  const last=Math.max(1, Math.ceil(pagination.total / pagination.page_size));
  if(pagination.page<last){ pagination.page++; loadTable(); }
});

// -------------------- Export / Import --------------------
exportLink.addEventListener("click",(e)=>{
  e.preventDefault();
  const params=buildParams();
  window.open(`/api/export?${params}`, "_blank");
});

fileInput?.addEventListener("change", async (e)=>{
  const file=e.target.files?.[0]; if(!file) return;
  const form=new FormData(); form.append("file", file);
  setLoading(true);
  try{
    const res=await fetch("/api/import",{ method:"POST", credentials:"include", body:form });
    const json=await res.json().catch(()=> ({}));
    if(!res.ok){ toast(json.error || "Falha ao importar CSV. Verifique o cabeçalho."); return; }
    toast(json.message || "Importação concluída.");
    pagination.page=1;
    await preloadDates();
    await loadTable();
  } catch{ toast("Erro ao enviar arquivo."); }
  finally{ e.target.value=""; setLoading(false); }
});

// -------------------- Data Loading --------------------
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
  setLoading(true);
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
  } finally { setLoading(false); }
}

function renderTable(rows, totals){
  tbody.innerHTML=""; thead.innerHTML=""; tfoot.innerHTML="";

  if(!rows || rows.length===0){ tbody.innerHTML="<tr><td>Nenhum dado</td></tr>"; return; }

  const columns = Object.keys(rows[0]);

  // Cabeçalho com ordenação
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

  // Linhas
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

  // Rodapé (totais do filtro)
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
