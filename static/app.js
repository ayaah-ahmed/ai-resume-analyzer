// Vanilla JavaScript frontend for the AI Resume Analyzer (no frameworks).
const $ = (id) => document.getElementById(id);
const state = { token: localStorage.getItem("token"), user: null, resumeId: null };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const chips = (arr, cls = "") => (arr && arr.length ? arr.map((x) => `<span class="chip ${cls}">${esc(x)}</span>`).join("") : '<span class="muted">None detected</span>');
const list = (arr) => (arr && arr.length ? `<ul>${arr.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : '<p class="muted">—</p>');

let toastTimer;
function toast(msg, ok = false) {
  const t = $("toast");
  t.textContent = msg; t.className = ok ? "ok" : ""; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 4500);
}

async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let payload;
  if (form) payload = form;
  else if (body) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res;
  try { res = await fetch(path, { method, headers, body: payload }); }
  catch { throw new Error("Cannot reach the server. Is it running?"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && state.token) { logout(false); }
    throw new Error(typeof data.detail === "string" ? data.detail : "Request failed.");
  }
  return data;
}

async function busy(btn, fn) {
  btn.disabled = true;
  try { await fn(); } catch (e) { toast(e.message); } finally { btn.disabled = false; }
}

// ---------------------------------------------------------------- auth
function showApp(user) {
  state.user = user;
  $("authView").hidden = true; $("appView").hidden = false; $("nav").hidden = false;
  $("userName").textContent = user.name;
  loadResumes(); searchJobs(); loadStatus();
}
function logout(callApi = true) {
  if (callApi && state.token) api("/api/auth/logout", { method: "POST" }).catch(() => {});
  localStorage.removeItem("token"); state.token = null; state.user = null; state.resumeId = null;
  $("appView").hidden = true; $("nav").hidden = true; $("authView").hidden = false;
}
$("showLogin").onclick = () => { $("loginForm").hidden = false; $("registerForm").hidden = true; $("showLogin").classList.add("active"); $("showRegister").classList.remove("active"); };
$("showRegister").onclick = () => { $("loginForm").hidden = true; $("registerForm").hidden = false; $("showRegister").classList.add("active"); $("showLogin").classList.remove("active"); };
async function authenticate(path, body, btn) {
  await busy(btn, async () => {
    const data = await api(path, { method: "POST", body });
    state.token = data.token; localStorage.setItem("token", data.token); showApp(data.user);
  });
}
$("loginForm").onsubmit = (e) => { e.preventDefault(); authenticate("/api/auth/login", { email: $("loginEmail").value, password: $("loginPassword").value }, e.submitter); };
$("registerForm").onsubmit = (e) => { e.preventDefault(); authenticate("/api/auth/register", { name: $("regName").value, email: $("regEmail").value, password: $("regPassword").value }, e.submitter); };
$("logoutBtn").onclick = () => logout();

// ---------------------------------------------------------------- tabs
document.querySelectorAll("#nav [data-tab]").forEach((b) => (b.onclick = () => {
  document.querySelectorAll("#nav [data-tab]").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".tab").forEach((t) => (t.hidden = t.id !== `tab-${b.dataset.tab}`));
}));

// ---------------------------------------------------------------- resumes
async function loadResumes() {
  const resumes = await api("/api/resumes").catch(() => []);
  $("resumeList").innerHTML = resumes.map((r) => `<span class="chip resume ${r.id === state.resumeId ? "active" : ""}" data-id="${r.id}">📎 ${esc(r.filename)}</span>`).join("");
  document.querySelectorAll(".chip.resume").forEach((c) => (c.onclick = () => selectResume(Number(c.dataset.id))));
  if (!state.resumeId && resumes.length) selectResume(resumes[0].id);
}
async function selectResume(id) {
  state.resumeId = id; $("resultBox").innerHTML = "";
  const r = await api(`/api/resumes/${id}`).catch((e) => toast(e.message));
  if (!r) return;
  document.querySelectorAll(".chip.resume").forEach((c) => c.classList.toggle("active", Number(c.dataset.id) === id));
  renderAnalysis(r);
}
function renderAnalysis(r) {
  const a = r.analysis; if (!a) return;
  const c = a.contact, ex = a.experience;
  $("analysisBox").hidden = false; $("actionsBox").hidden = false;
  $("analysisBox").innerHTML = `
    <div class="row" style="align-items:center"><h2>Analysis: ${esc(r.filename)}</h2>
      <button id="delBtn" class="danger" style="flex:0">Delete</button></div>
    <h3>Summary</h3><p>${esc(a.summary)}</p>
    <h3>Contact</h3><p>${["name", "email", "phone", "github", "linkedin"].filter((k) => c[k]).map((k) => `<b>${k}:</b> ${esc(c[k])}`).join(" · ") || '<span class="muted">Not found</span>'}</p>
    <h3>Technical skills</h3><div class="chips">${chips(a.technical_skills)}</div>
    <h3>Soft skills</h3><div class="chips">${chips(a.soft_skills, "soft")}</div>
    <h3>Education</h3>${list(a.education)}
    <h3>Experience (~${esc(ex.estimated_years)} years)</h3>${list(ex.roles)}`;
  $("delBtn").onclick = async () => {
    if (!confirm("Delete this resume?")) return;
    await api(`/api/resumes/${r.id}`, { method: "DELETE" }).catch((e) => toast(e.message));
    state.resumeId = null; $("analysisBox").hidden = true; $("actionsBox").hidden = true; $("resultBox").innerHTML = ""; loadResumes();
  };
}
$("uploadForm").onsubmit = (e) => {
  e.preventDefault();
  const file = $("resumeFile").files[0];
  if (!file) return toast("Please choose a file first.");
  busy(e.submitter, async () => {
    const form = new FormData(); form.append("file", file);
    const r = await api("/api/resumes", { method: "POST", form });
    state.resumeId = r.id; toast("Resume analyzed successfully.", true); $("uploadForm").reset();
    await loadResumes(); renderAnalysis(r);
  });
};

const scoreClass = (s) => (s >= 70 ? "hi" : s >= 45 ? "mid" : "lo");
$("recBtn").onclick = (e) => busy(e.target, async () => {
  const d = await api(`/api/resumes/${state.resumeId}/recommendations?top_n=5`);
  $("resultBox").innerHTML = `<div class="card"><h2>🎯 Recommended jobs</h2>${d.recommendations.map((r) => `
    <div style="border-top:1px solid var(--line);padding:12px 0">
      <div class="job"><div><b>${esc(r.job.title)}</b> — ${esc(r.job.company)} <span class="muted">(${esc(r.job.location)}, ${esc(r.job.job_type)})</span></div>
      <span class="score ${scoreClass(r.score)}">${r.score}%</span></div>
      <div class="bar"><div style="width:${r.score}%"></div></div>
      <p>${esc(r.explanation)}</p>
      <div class="chips">${chips(r.matched_skills, "soft")}${chips(r.missing_skills, "miss").replace('<span class="muted">None detected</span>', "")}</div>
    </div>`).join("")}</div>`;
});
$("impBtn").onclick = (e) => busy(e.target, async () => {
  const role = $("targetRole").value.trim();
  const d = await api(`/api/resumes/${state.resumeId}/improvements${role ? "?target_role=" + encodeURIComponent(role) : ""}`);
  $("resultBox").innerHTML = `<div class="card"><h2>🛠 Improvement plan for: ${esc(d.target_role)}</h2>
    <p>Skill coverage for this role: <b>${d.match_percent}%</b></p><div class="bar"><div style="width:${d.match_percent}%"></div></div>
    <h3>Advice</h3><p>${esc(d.ai_advice)}</p>
    <h3>Missing skills</h3><div class="chips">${chips(d.missing_skills, "miss")}</div>
    <h3>Weaknesses</h3>${list(d.weaknesses)}<h3>How to improve</h3>${list(d.improvements)}
    <h3>Recommended certifications</h3>${list(d.certifications)}
    <h3>Learning resources</h3>${d.learning_resources.map((x) => `<p><b>${esc(x.skill)}:</b> ${x.resources.map((r) => `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>`).join(", ")}</p>`).join("") || '<p class="muted">—</p>'}
    <h3>Roadmap</h3><p>${esc(d.roadmap)}</p></div>`;
});

// ---------------------------------------------------------------- jobs
async function searchJobs() {
  const p = new URLSearchParams();
  [["q", "sQ"], ["location", "sLocation"], ["job_type", "sType"], ["skill", "sSkill"]].forEach(([k, id]) => { if ($(id).value.trim()) p.set(k, $(id).value.trim()); });
  const jobs = await api(`/api/jobs?${p}`).catch((e) => { toast(e.message); return []; });
  $("jobsList").innerHTML = jobs.length ? jobs.map((j) => `
    <div class="card job"><div style="flex:1"><b>${esc(j.title)}</b> — ${esc(j.company)}
      <div class="muted">${esc(j.location)} · ${esc(j.job_type)}</div><p>${esc(j.description)}</p><div class="chips">${chips(j.required_skills)}</div></div>
      <div class="actions"><button class="ghost" data-edit="${j.id}">Edit</button><button class="danger" data-del="${j.id}">Delete</button></div></div>`).join("")
    : '<div class="card muted">No jobs match your search.</div>';
  document.querySelectorAll("[data-edit]").forEach((b) => (b.onclick = () => editJob(jobs.find((j) => j.id === Number(b.dataset.edit)))));
  document.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => {
    if (!confirm("Delete this job?")) return;
    await api(`/api/jobs/${b.dataset.del}`, { method: "DELETE" }).then(() => { toast("Job deleted.", true); searchJobs(); }).catch((e) => toast(e.message));
  }));
}
function editJob(j) {
  $("jobFormBox").hidden = false; $("jobFormTitle").textContent = j ? "Edit job" : "Add job";
  $("jobId").value = j ? j.id : ""; $("jTitle").value = j?.title ?? ""; $("jCompany").value = j?.company ?? "";
  $("jLocation").value = j?.location ?? ""; $("jType").value = j?.job_type ?? "Full-time";
  $("jSkills").value = j ? j.required_skills.join(", ") : ""; $("jDesc").value = j?.description ?? "";
  $("jobFormBox").scrollIntoView({ behavior: "smooth" });
}
$("newJobBtn").onclick = () => editJob(null);
$("cancelJob").onclick = () => ($("jobFormBox").hidden = true);
$("searchForm").onsubmit = (e) => { e.preventDefault(); searchJobs(); };
$("jobForm").onsubmit = (e) => {
  e.preventDefault();
  busy(e.submitter, async () => {
    const id = $("jobId").value;
    const body = { title: $("jTitle").value, company: $("jCompany").value, location: $("jLocation").value, job_type: $("jType").value,
      description: $("jDesc").value, required_skills: $("jSkills").value.split(",").map((s) => s.trim()).filter(Boolean) };
    await api(id ? `/api/jobs/${id}` : "/api/jobs", { method: id ? "PUT" : "POST", body });
    toast("Job saved.", true); $("jobFormBox").hidden = true; searchJobs();
  });
};

// ---------------------------------------------------------------- advisor
async function loadStatus() {
  const s = await api("/api/system/status").catch(() => null);
  if (s) $("modeBadge").textContent = s.llm_enabled ? "LLM + RAG" : "Rule-based + RAG";
}
$("askForm").onsubmit = (e) => {
  e.preventDefault();
  busy(e.submitter, async () => {
    const body = { question: $("question").value };
    if ($("useResume").checked && state.resumeId) body.resume_id = state.resumeId;
    const d = await api("/api/career/ask", { method: "POST", body });
    $("answerBox").innerHTML = `<div class="card"><h2>Answer</h2><pre class="text">${esc(d.answer)}</pre>
      <h3>Sources retrieved</h3><div class="chips">${d.sources.map((s) => `<span class="chip">${esc(s.type)}: ${esc(s.title)}</span>`).join("")}</div></div>`;
  });
};

// ---------------------------------------------------------------- init
if (state.token) api("/api/auth/me").then(showApp).catch(() => logout(false));
