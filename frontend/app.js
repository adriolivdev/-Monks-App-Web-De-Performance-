// Estado/UI
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
const pageSizeEl = document.getElementById("page-size");
const applyBtn = document.getElementById("apply-filters");
const clearBtn = document.getElementById("clear-filters");

const thead = document.getElementById("table-head");
const tbody = document.getElementById("table-body");

const prevBtn = document.getElementById("prev-page");
const nextBtn = document.getElementById("next-page");
const pageInfo = document.getElementById("page-info");

const exportLink = document.getElementById("export-csv");
const fileInput  = document.getElementById("csv-file");

let currentSort = { by: null, dir: "asc" };
let pagination  = { page: 1, page_size: 50, total: 0 };

async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...opts
  });
  if (!res.ok) {
    let msg = "Erro";
    try { msg = (await res.json()).error || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function show(view) {
  if (view === "login") { loginView.classList.remove("hidden"); appView.classList.add("hidden"); }
  else { loginView.classList.add("hidden"); appView.classList.remove("hidden"); }
}

async function preloadDates() {
  try {
    const res = await fetch("/api/date-range", { credentials: "include" });
    if (!res.ok) return;
    const { min, max } = await res.json();
    if (min) dateFrom.value = min;
    if (max) dateTo.value   = max;
  } catch {}
}

async function init() {
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

// LOGIN / LOGOUT
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.textContent = "";
  try {
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
  } catch (err) {
    loginError.textContent = err.message || "Credenciais inválidas";
  }
});

logoutBtn.addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  show("login");
});

// FILTROS / PAGINAÇÃO / EXPORT / IMPORT
applyBtn.addEventListener("click", () => {
  pagination.page = 1;
  loadTable();
});
clearBtn.addEventListener("click", () => {
  dateFrom.value = "";
  dateTo.value   = "";
  pageSizeEl.value = 50;
  currentSort = { by: null, dir: "asc" };
  pagination  = { page: 1, page_size: 50, total: 0 };
  loadTable();
});

prevBtn.addEventListener("click", () => {
  if (pagination.page > 1) {
    pagination.page -= 1;
    loadTable();
  }
});
nextBtn.addEventListener("click", () => {
  const last = Math.max(1, Math.ceil(pagination.total / pagination.page_size));
  if (pagination.page < last) {
    pagination.page += 1;
    loadTable();
  }
});

exportLink.addEventListener("click", (e) => {
  e.preventDefault();
  const params = buildParams();
  window.open(`/api/export?${params}`, "_blank");
});

fileInput?.addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;

  const form = new FormData();
  form.append("file", file);

  try {
    const res = await fetch("/api/import", {
      method: "POST",
      credentials: "include",
      body: form
    });
    if (!res.ok) {
      let err = "Falha ao importar";
      try { err = (await res.json()).error || err; } catch {}
      alert(err);
      return;
    }
    const json = await res.json();
    alert(json.message || "Importação concluída.");
    pagination.page = 1;
    await preloadDates();
    await loadTable();
  } catch (err) {
    alert("Erro ao enviar arquivo.");
  } finally {
    e.target.value = "";
  }
});

function buildParams() {
  const params = new URLSearchParams();
  if (dateFrom.value) params.set("date_from", dateFrom.value);
  if (dateTo.value)   params.set("date_to",   dateTo.value);
  if (currentSort.by) {
    params.set("sort_by",  currentSort.by);
    params.set("sort_dir", currentSort.dir);
  }
  const ps = parseInt(pageSizeEl.value || "50", 10);
  pagination.page_size = isNaN(ps) ? 50 : Math.max(1, Math.min(200, ps));
  params.set("page", pagination.page);
  params.set("page_size", pagination.page_size);
  return params.toString();
}

async function loadTable() {
  const params = buildParams();
  try {
    const data = await api(`/api/data?${params}`);
    pagination.total = data.total || 0;
    renderTable(data.rows || []);
    const last = Math.max(1, Math.ceil(pagination.total / pagination.page_size));
    pageInfo.textContent = `Página ${data.page} de ${last} · ${pagination.total} itens`;
  } catch (err) {
    console.error("Erro ao carregar dados:", err);
    thead.innerHTML = "";
    tbody.innerHTML = `<tr><td class="error">Erro ao carregar dados: ${err.message || err}</td></tr>`;
    pageInfo.textContent = "";
  }
}

function renderTable(rows) {
  tbody.innerHTML = "";
  thead.innerHTML = "";

  if (!rows || rows.length === 0) {
    tbody.innerHTML = "<tr><td>Nenhum dado</td></tr>";
    return;
  }

  const columns = Object.keys(rows[0]);

  const trHead = document.createElement("tr");
  columns.forEach(col => {
    const th = document.createElement("th");
    th.textContent = col;
    th.addEventListener("click", () => {
      if (currentSort.by === col) {
        currentSort.dir = currentSort.dir === "asc" ? "desc" : "asc";
      } else {
        currentSort.by = col;
        currentSort.dir = "asc";
      }
      loadTable();
    });
    if (currentSort.by === col) {
      th.classList.add(currentSort.dir === "asc" ? "sort-asc" : "sort-desc");
    }
    trHead.appendChild(th);
  });
  thead.appendChild(trHead);

  rows.forEach(row => {
    const tr = document.createElement("tr");
    columns.forEach(col => {
      const td = document.createElement("td");
      let value = row[col];

      if (col === "cost_micros" && value !== undefined && value !== null) {
        const num = Number(value);
        if (!isNaN(num)) {
          const brl = num / 1_000_000;
          value = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(brl);
        }
      }

      td.textContent = value;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}
