// The token lives in a JavaScript variable, not localStorage: storage survives
// refreshes but is readable by any script that ever runs in this page, which
// is exactly the theft target of an injection attack. Memory-only means a
// refresh asks you to log in again; that trade is deliberate.
let token = null;
let me = null;
let categories = [];
let sessionEndsAt = null;
let sessionTicker = null;

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  options.headers = Object.assign({}, options.headers, token ? { Authorization: "Bearer " + token } : {});
  const res = await fetch(path, options);
  // A 401 while signed in means the server no longer honors the token; the
  // display follows the server's decision rather than its own countdown.
  if (res.status === 401 && me) {
    endSession("Session expired. Log in again.");
    throw new Error("Session expired");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.status === 204 ? null : res.json();
}

// The countdown is display only; the server enforces expiry regardless. It
// exists so a session ends predictably instead of failing mid-action.
function startSessionTimer(expiresInSeconds) {
  sessionEndsAt = Date.now() + expiresInSeconds * 1000;
  clearInterval(sessionTicker);
  const tick = () => {
    const left = Math.max(0, Math.floor((sessionEndsAt - Date.now()) / 1000));
    const el = $("session-timer");
    el.textContent = `session ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
    el.classList.toggle("expiring", left < 300);
    if (left <= 0) endSession("Session expired. Log in again.");
  };
  tick();
  sessionTicker = setInterval(tick, 1000);
}

function endSession(message) {
  clearInterval(sessionTicker);
  sessionTicker = null;
  token = null; me = null; sessionEndsAt = null;
  $("app-view").classList.add("hidden");
  $("login-view").classList.remove("hidden");
  showError(message || "");
}

function showError(err) { $("error").textContent = err ? String(err.message || err) : ""; }

function dollars(cents) { return "$" + (cents / 100).toFixed(2); }

async function refreshList() {
  const expenses = await api("/expenses");
  $("list-title").textContent =
    me.role === "manager" ? "Pending expenses (all employees)" : "My expenses";
  // A summary line, not a chart: computed from the visible rows and rendered
  // as text, so it can never break and never introduces markup.
  const counts = { pending: 0, approved: 0, rejected: 0 };
  let totalCents = 0;
  for (const e of expenses) { counts[e.status] += 1; totalCents += e.amount_cents; }
  $("summary").textContent = expenses.length
    ? `${expenses.length} shown: ${counts.pending} pending, ${counts.approved} approved, ` +
      `${counts.rejected} rejected, ${dollars(totalCents)} total`
    : "No expenses yet";

  const rows = $("rows");
  rows.replaceChildren();
  for (const e of expenses) {
    const tr = document.createElement("tr");
    const cat = categories.find((c) => c.id === e.category_id);
    // Every value goes in through textContent: user-written text renders as
    // text, never as markup. This is the stored-XSS defense in one line.
    for (const value of [e.expense_date, cat ? cat.name : e.category_id,
                         e.description, dollars(e.amount_cents)]) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.appendChild(td);
    }
    const st = document.createElement("td");
    st.textContent = e.status;
    st.className = "status-" + e.status;
    tr.appendChild(st);

    const actions = document.createElement("td");
    if (me.role === "manager" && e.status === "pending" && e.user_id !== me.id) {
      for (const [label, path] of [["Approve", "approve"], ["Reject", "reject"]]) {
        const b = document.createElement("button");
        b.textContent = label;
        b.onclick = () =>
          api(`/expenses/${e.id}/${path}`, { method: "POST" })
            .then(refreshList).catch(showError);
        actions.appendChild(b);
      }
    }
    if (e.has_receipt) {
      const b = document.createElement("button");
      b.textContent = "Receipt";
      b.onclick = () => downloadReceipt(e.id).catch(showError);
      actions.appendChild(b);
    } else if (e.user_id === me.id && e.status === "pending") {
      actions.appendChild(attachControl(e.id));
    }
    tr.appendChild(actions);
    rows.appendChild(tr);
  }
}

// Upload goes as multipart form data; the browser sets the content type and
// boundary itself, which is why no Content-Type header is set here.
function attachControl(expenseId) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".png,.jpg,.jpeg,.pdf";
  input.className = "hidden";
  input.onchange = async () => {
    if (!input.files.length) return;
    showError("");
    const form = new FormData();
    form.append("file", input.files[0]);
    try {
      await api(`/expenses/${expenseId}/receipt`, { method: "POST", body: form });
      await refreshList();
    } catch (err) { showError(err); }
  };
  const b = document.createElement("button");
  b.textContent = "Attach";
  b.onclick = () => input.click();
  const wrap = document.createElement("span");
  wrap.append(b, input);
  return wrap;
}

// The download needs the Authorization header, so it goes through fetch and a
// temporary object URL rather than a plain link; the token never lands in a URL.
async function downloadReceipt(expenseId) {
  const res = await fetch(`/expenses/${expenseId}/receipt`, {
    headers: { Authorization: "Bearer " + token },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const match = /filename="?([^";]+)"?/.exec(res.headers.get("content-disposition") || "");
  a.download = match ? match[1] : `receipt-${expenseId}`;
  a.click();
  URL.revokeObjectURL(url);
}

async function enterApp() {
  me = await api("/auth/me");
  categories = await api("/categories");
  $("who").textContent = me.email;
  $("role").textContent = me.role;
  const sel = $("category");
  sel.replaceChildren();
  for (const c of categories) {
    const o = document.createElement("option");
    o.value = c.id;
    o.textContent = c.name;
    sel.appendChild(o);
  }
  $("login-view").classList.add("hidden");
  $("app-view").classList.remove("hidden");
  await refreshList();
}

$("login-form").onsubmit = async (ev) => {
  ev.preventDefault();
  showError("");
  try {
    const data = await api("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: $("email").value, password: $("password").value }),
    });
    token = data.access_token;
    $("password").value = "";
    startSessionTimer(data.expires_in);
    await enterApp();
  } catch (err) { showError(err); }
};

$("report-form").onsubmit = async (ev) => {
  ev.preventDefault();
  showError("");
  const [year, month] = $("report-month").value.split("-");
  try {
    // Same pattern as the receipt download: the token goes in a header via
    // fetch, never in a URL, and the file arrives through a temporary
    // object URL.
    const res = await fetch(`/reports/expenses.csv?year=${year}&month=${month}`, {
      headers: { Authorization: "Bearer " + token },
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || res.statusText);
    }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = `expenses-${year}-${month}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) { showError(err); }
};

$("expense-form").onsubmit = async (ev) => {
  ev.preventDefault();
  showError("");
  try {
    await api("/expenses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category_id: Number($("category").value),
        amount_cents: Math.round(parseFloat($("amount").value) * 100),
        description: $("description").value,
        expense_date: $("date").value,
      }),
    });
    $("expense-form").reset();
    await refreshList();
  } catch (err) { showError(err); }
};

$("logout").onclick = () => endSession();
