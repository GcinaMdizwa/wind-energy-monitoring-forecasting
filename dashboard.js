"use strict";
const $ = (id) => document.getElementById(id);
const state = {
  location: { name: "Jeffreys Bay, South Africa", lat: -34.05, lon: 24.92 },
  capacity: 2000,
  weather: null,
  projects: [],
  chart: "speed",
  view: "overview",
  jobTimer: null,
  authMode: "login",
  searchId: 0,
  weatherId: 0,
};
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
async function api(path, body) {
  const r = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data;
  try {
    data = await r.json();
  } catch {
    throw new Error("The local server returned an unreadable response.");
  }
  if (!r.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Please check your inputs and try again.",
    );
  return data;
}
function error(message) {
  $("global-error").textContent = message;
  $("global-error").hidden = false;
}
function clearError() {
  $("global-error").hidden = true;
}
let toastTimer;
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 4500);
}
function showAuth(mode) {
  state.authMode = mode;
  $("auth-title").textContent =
    mode === "login" ? "Welcome back." : "Make room for discovery.";
  $("auth-subtitle").textContent =
    mode === "login"
      ? "Sign in to your local research profile."
      : "Create a profile stored only on this computer.";
  $("auth-submit").textContent =
    mode === "login" ? "Sign in →" : "Create local profile →";
  $("switch-auth").textContent =
    mode === "login"
      ? "New here? Create a local profile"
      : "Already have a profile? Sign in";
  $("auth-password").autocomplete =
    mode === "login" ? "current-password" : "new-password";
  $("auth-error").textContent = "";
  $("auth-modal").hidden = false;
  $("auth-name").focus();
}
async function enter(user) {
  $("welcome").hidden = true;
  $("auth-modal").hidden = true;
  $("workspace").hidden = false;
  $("profile-name").textContent = user.name;
  document.querySelector(".avatar").textContent = user.name
    .split(" ")
    .map((x) => x[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  await loadProjects();
  setMap();
  loadWeather();
}
function view(name) {
  state.view = name;
  document
    .querySelectorAll(".view")
    .forEach((el) => (el.hidden = el.id !== `view-${name}`));
  document
    .querySelectorAll(".nav-item")
    .forEach((el) => el.classList.toggle("active", el.dataset.view === name));
  $("breadcrumb-view").textContent = {
    overview: "Overview",
    forecast: "Forecast lab",
    projects: "My projects",
    methods: "Data & methods",
  }[name];
  clearError();
  if (name === "forecast") loadModel();
  window.scrollTo({ top: 0, behavior: "smooth" });
}
document
  .querySelectorAll("[data-view]")
  .forEach((b) => b.addEventListener("click", () => view(b.dataset.view)));
$("today").textContent = new Date().toLocaleDateString("en-ZA", {
  day: "numeric",
  month: "short",
  year: "numeric",
});
$("open-login").onclick = () => showAuth("login");
$("open-register").onclick = () => showAuth("register");
$("close-auth").onclick = () => ($("auth-modal").hidden = true);
$("switch-auth").onclick = () =>
  showAuth(state.authMode === "login" ? "register" : "login");
$("auth-form").onsubmit = async (e) => {
  e.preventDefault();
  $("auth-submit").disabled = true;
  try {
    await enter(
      await api(`/api/auth/${state.authMode}`, {
        name: $("auth-name").value,
        password: $("auth-password").value,
      }),
    );
    $("auth-password").value = "";
  } catch (e) {
    $("auth-error").textContent = e.message;
  } finally {
    $("auth-submit").disabled = false;
  }
};
$("explore").onclick = async () => {
  try {
    await enter(await api("/api/auth/demo", {}));
  } catch (e) {
    toast(e.message);
  }
};
$("logout").onclick = async () => {
  try {
    await api("/api/logout", {});
    clearInterval(state.jobTimer);
    state.jobTimer = null;
    $("workspace").hidden = true;
    $("welcome").hidden = false;
    state.weather = null;
    state.projects = [];
    state.weatherId++;
    view("overview");
  } catch (e) {
    error(e.message);
  }
};
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    $("auth-modal").hidden = true;
    $("save-modal").hidden = true;
    $("search-results").hidden = true;
  }
});
function setMap() {
  const { lat, lon, name } = state.location;
  $("location-name").textContent = name;
  $("location-coords").textContent = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  $("map-coords").textContent =
    `${Math.abs(lat).toFixed(4)}° ${lat < 0 ? "S" : "N"} · ${Math.abs(lon).toFixed(4)}° ${lon < 0 ? "W" : "E"}`;
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  const bbox = [
    clamp(lon - 0.18, -180, 180),
    clamp(lat - 0.12, -90, 90),
    clamp(lon + 0.18, -180, 180),
    clamp(lat + 0.12, -90, 90),
  ].join(",");
  $("area-map").src =
    `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(bbox)}&layer=mapnik&marker=${lat}%2C${lon}`;
  $("open-map").href =
    `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=10/${lat}/${lon}`;
}
async function selectLocation(place) {
  state.location = place;
  state.weather = null;
  ["wind-value", "power-value", "direction-value", "energy-value"].forEach(
    (id) => ($(id).textContent = "—"),
  );
  $("main-chart").innerHTML =
    '<div class="empty-state">Loading weather for this study area…</div>';
  $("wind-mini").innerHTML = "";
  $("wind-rose").innerHTML = "";
  $("capacity-fill").style.width = "0";
  $("search-results").hidden = true;
  $("place-query").value = "";
  setMap();
  await loadWeather();
}
$("location-form").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("place-query").value.trim();
  if (q.length < 2) {
    toast("Enter at least two characters, or use coordinates.");
    return;
  }
  const id = ++state.searchId;
  $("search-results").hidden = false;
  $("search-results").innerHTML = "<p>Searching places…</p>";
  try {
    const { results } = await api(`/api/search?q=${encodeURIComponent(q)}`);
    if (id !== state.searchId) return;
    $("search-results").innerHTML = results.length
      ? ""
      : "<p>No places found. Try a nearby town or enter coordinates.</p>";
    for (const r of results) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = r.label;
      b.onclick = () =>
        selectLocation({ name: r.label, lat: r.lat, lon: r.lon });
      $("search-results").appendChild(b);
    }
  } catch (e) {
    $("search-results").textContent = e.message;
  }
};
$("coordinate-toggle").onclick = () =>
  ($("coordinates-form").hidden = !$("coordinates-form").hidden);
$("coordinates-form").onsubmit = (e) => {
  e.preventDefault();
  const lat = Number($("latitude").value),
    lon = Number($("longitude").value);
  if (
    !Number.isFinite(lat) ||
    !Number.isFinite(lon) ||
    Math.abs(lat) > 90 ||
    Math.abs(lon) > 180
  )
    return;
  selectLocation({
    name: `Study point ${lat.toFixed(3)}, ${lon.toFixed(3)}`,
    lat,
    lon,
  });
  $("coordinates-form").hidden = true;
};
$("capacity").onchange = () => {
  state.capacity = Number($("capacity").value);
  loadWeather();
};
$("refresh-weather").onclick = () => loadWeather();
async function loadWeather() {
  const id = ++state.weatherId;
  clearError();
  $("weather-status").textContent = "Fetching modelled weather…";
  $("refresh-weather").disabled = true;
  try {
    const { lat, lon } = state.location;
    const data = await api(
      `/api/monitor?lat=${lat}&lon=${lon}&rated_kw=${state.capacity}`,
    );
    if (id !== state.weatherId) return;
    state.weather = data;
    renderWeather();
  } catch (e) {
    if (id !== state.weatherId) return;
    state.weather = null;
    $("weather-status").textContent = "Weather unavailable";
    ["wind-value", "power-value", "direction-value", "energy-value"].forEach(
      (id) => ($(id).textContent = "—"),
    );
    $("main-chart").innerHTML =
      '<div class="empty-state">No weather available. Please retry.<br>No synthetic values are used as live weather.</div>';
    $("wind-rose").innerHTML = "";
    $("wind-mini").innerHTML = "";
    $("capacity-fill").style.width = "0";
    error(e.message);
  } finally {
    if (id === state.weatherId) $("refresh-weather").disabled = false;
  }
}
function cardinal(d) {
  return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(d / 45) % 8];
}
function renderWeather() {
  const d = state.weather;
  if (!d?.rows?.length) return;
  const past = d.rows.filter((r) => !r.future);
  const current = past.at(-1);
  const next = d.rows.filter((r) => r.future).slice(0, 24);
  if (!current) return;
  $("wind-value").textContent = current.speed.toFixed(1);
  $("power-value").textContent = Math.round(current.power_kw).toLocaleString();
  $("direction-value").textContent =
    current.direction === null ? "—" : Math.round(current.direction);
  $("direction-cardinal").textContent =
    current.direction === null ? "°" : `° ${cardinal(current.direction)}`;
  $("energy-value").textContent =
    next.length === 24
      ? (next.reduce((s, r) => s + r.power_kw, 0) / 1000).toFixed(1)
      : "—";
  $("capacity-fill").style.width =
    `${Math.min((current.power_kw / state.capacity) * 100, 100)}%`;
  $("weather-status").textContent =
    `Modelled · ${new Date(current.time).toISOString().slice(11, 16)} UTC`;
  $("wind-mini").innerHTML = spark(past.slice(-24).map((r) => r.speed));
  const peak = next.length ? Math.max(...next.map((r) => r.speed)) : null;
  $("chart-insight").textContent =
    peak === null
      ? "Future weather unavailable."
      : `Next 24h peak wind: ${peak.toFixed(1)} m/s`;
  $("source-note").textContent =
    `Open-Meteo numerical weather · 100 m wind · grid ${d.grid_lat.toFixed(3)}, ${d.grid_lon.toFixed(3)} · fetched ${new Date(d.fetched_at).toISOString().slice(11, 16)} UTC. Refreshes every 10 min while open. Power uses an illustrative curve; no sensor or SCADA feed.`;
  renderMainChart();
  rose(d.rows);
}
function spark(a) {
  if (a.length < 2) return "";
  const min = Math.min(...a),
    range = Math.max(...a) - min || 1;
  return `<svg viewBox="0 0 200 23" preserveAspectRatio="none" aria-hidden="true"><path d="${a.map((v, i) => `${i ? "L" : "M"}${(i / (a.length - 1)) * 200},${22 - ((v - min) / range) * 20}`).join(" ")}" fill="none" stroke="#aac975" stroke-width="1.5"/></svg>`;
}
function chart(
  id,
  rows,
  series,
  { unit = "m/s", timeKey = "time", height = 215, forecast = true } = {},
) {
  const el = $(id);
  if (!rows.length) {
    el.innerHTML = '<div class="empty-state">No data to plot.</div>';
    return;
  }
  const W = 700,
    H = height,
    L = 40,
    R = 12,
    T = 18,
    B = 32;
  const values = rows
    .flatMap((r) => series.map((s) => r[s.key]))
    .filter(Number.isFinite);
  if (!values.length) {
    el.innerHTML = '<div class="empty-state">No finite values to plot.</div>';
    return;
  }
  const max = Math.max(...values, 1) * 1.15,
    min = 0,
    x = (i) => L + (i / (rows.length - 1 || 1)) * (W - L - R),
    y = (v) => H - B - ((v - min) / (max - min)) * (H - T - B);
  const path = (s, arr) =>
    arr
      .filter(({ r }) => Number.isFinite(r[s.key]))
      .map(
        ({ r, i }, j) =>
          `${j ? "L" : "M"}${x(i).toFixed(2)},${y(r[s.key]).toFixed(2)}`,
      )
      .join(" ");
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(series.map((s) => s.label).join(" and "))} in ${esc(unit)}"><title>${esc(unit)}; all timestamps UTC. Hover for values.</title>`;
  for (let i = 0; i <= 4; i++) {
    const v = (max * i) / 4,
      yy = y(v);
    svg += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="#e8eee4" stroke-dasharray="3 5"/><text x="${L - 9}" y="${yy + 3}" text-anchor="end" fill="#9ba995" font-size="9">${v >= 100 ? v.toFixed(0) : v.toFixed(1)}</text>`;
  }
  const futureIndex = rows.findIndex((r) => r.future);
  if (forecast && futureIndex > 0)
    svg += `<rect x="${x(futureIndex)}" y="${T}" width="${W - R - x(futureIndex)}" height="${H - T - B}" fill="#eff4e6" opacity=".65"/><line x1="${x(futureIndex)}" x2="${x(futureIndex)}" y1="${T}" y2="${H - B}" stroke="#b2c19c" stroke-dasharray="4 4"/><text x="${x(futureIndex) + 6}" y="${T + 10}" font-size="8" fill="#93a37b">FORECAST →</text>`;
  const indexed = rows.map((r, i) => ({ r, i }));
  for (const s of series) {
    if (forecast && futureIndex > 0) {
      svg += `<path d="${path(s, indexed.slice(0, futureIndex))}" fill="none" stroke="${s.color}" stroke-width="2.3"/><path d="${path(s, indexed.slice(futureIndex - 1))}" fill="none" stroke="${s.color}" stroke-width="2" stroke-dasharray="5 4"/>`;
    } else
      svg += `<path d="${path(s, indexed)}" fill="none" stroke="${s.color}" stroke-width="2" ${s.dash ? 'stroke-dasharray="5 4"' : ""}/>`;
  }
  for (let i = 0; i < 5; i++) {
    const index = Math.round((i * (rows.length - 1)) / 4);
    const stamp = rows[index][timeKey];
    const dt = new Date(stamp);
    const label = Number.isNaN(dt.getTime())
      ? String(stamp)
      : `${String(dt.getUTCDate()).padStart(2, "0")}/${String(dt.getUTCMonth() + 1).padStart(2, "0")} ${String(dt.getUTCHours()).padStart(2, "0")}:00`;
    svg += `<text x="${x(index)}" y="${H - 9}" text-anchor="${i === 0 ? "start" : i === 4 ? "end" : "middle"}" fill="#9aa891" font-size="8">${esc(label)}</text>`;
  }
  svg += "</svg>";
  el.innerHTML = svg + '<div class="chart-tooltip" hidden></div>';
  const tip = el.querySelector(".chart-tooltip");
  el.onmousemove = (e) => {
    const box = el.getBoundingClientRect();
    const index = Math.max(
      0,
      Math.min(
        rows.length - 1,
        Math.round(
          ((((e.clientX - box.left) / box.width) * W - L) / (W - L - R)) *
            (rows.length - 1),
        ),
      ),
    );
    const r = rows[index];
    tip.textContent =
      `${String(r[timeKey]).slice(0, 16).replace("T", " ")} UTC · ` +
      series
        .map(
          (s) =>
            `${s.label}: ${Number.isFinite(r[s.key]) ? r[s.key].toFixed(2) : "—"} ${unit}`,
        )
        .join(" · ");
    tip.hidden = false;
    tip.style.left = `${Math.min(Math.max(0, e.clientX - box.left - 60), Math.max(0, box.width - tip.offsetWidth))}px`;
    tip.style.top = "4px";
  };
  el.onmouseleave = () => (tip.hidden = true);
}
function renderMainChart() {
  if (!state.weather) return;
  $("chart-unit").textContent =
    state.chart === "speed" ? "m/s · UTC" : "kW · UTC";
  chart(
    "main-chart",
    state.weather.rows,
    [
      {
        key: state.chart,
        color: "#2a8d70",
        label: state.chart === "speed" ? "Modelled wind" : "Estimated power",
      },
    ],
    { unit: state.chart === "speed" ? "m/s" : "kW", height: 228 },
  );
}
document.querySelectorAll("[data-chart]").forEach(
  (b) =>
    (b.onclick = () => {
      state.chart = b.dataset.chart;
      document
        .querySelectorAll("[data-chart]")
        .forEach((x) => x.classList.toggle("selected", x === b));
      renderMainChart();
    }),
);
function rose(rows) {
  const counts = Array(8).fill(0);
  for (const r of rows)
    if (Number.isFinite(r.direction))
      counts[Math.round(r.direction / 45) % 8]++;
  const max = Math.max(...counts, 1),
    cx = 120,
    cy = 106;
  let svg =
    '<svg viewBox="0 0 240 215" role="img" aria-label="Wind direction frequency distribution">';
  for (const r of [22, 44, 66, 82])
    svg += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#e3ebdb" stroke-dasharray="3 3"/>`;
  for (let i = 0; i < 8; i++) {
    const a = ((i * 45 - 90) * Math.PI) / 180,
      rad = 12 + (counts[i] / max) * 64;
    const points = [
      [cx, cy],
      [cx + rad * Math.cos(a - 0.27), cy + rad * Math.sin(a - 0.27)],
      [cx + rad * Math.cos(a + 0.27), cy + rad * Math.sin(a + 0.27)],
    ]
      .map((p) => p.join(","))
      .join(" ");
    svg += `<polygon points="${points}" fill="${i % 2 ? "#78a884" : "#aecb91"}" opacity=".85"><title>${cardinal(i * 45)}: ${counts[i]} modelled hours</title></polygon><text x="${cx + 96 * Math.cos(a)}" y="${cy + 96 * Math.sin(a) + 3}" text-anchor="middle" fill="#99a78d" font-size="9">${cardinal(i * 45)}</text>`;
  }
  svg +=
    '<circle cx="120" cy="106" r="7" fill="#f8fbf3" stroke="#aac395"/></svg>';
  $("wind-rose").innerHTML = svg;
}
$("save-current").onclick = () => {
  $("project-name").value = state.location.name;
  $("save-location").textContent =
    `${state.location.lat.toFixed(4)}, ${state.location.lon.toFixed(4)} · ${(state.capacity / 1000).toFixed(1)} MW`;
  $("save-modal").hidden = false;
  $("project-name").focus();
};
$("close-save").onclick = () => ($("save-modal").hidden = true);
$("save-form").onsubmit = async (e) => {
  e.preventDefault();
  try {
    const r = await api("/api/projects", {
      name: $("project-name").value,
      lat: state.location.lat,
      lon: state.location.lon,
      rated_kw: state.capacity,
    });
    $("save-modal").hidden = true;
    await loadProjects();
    $("training-project").value = r.id;
    toast("Study area saved. Ready for your next experiment.");
  } catch (e) {
    toast(e.message);
  }
};
async function loadProjects() {
  const old = $("training-project").value;
  const { projects } = await api("/api/projects");
  state.projects = projects;
  $("project-count").textContent = projects.length;
  $("training-project").innerHTML =
    '<option value="">Select a saved study area</option>' +
    projects
      .map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`)
      .join("");
  if (projects.some((p) => p.id === old)) $("training-project").value = old;
  else if (projects.length) $("training-project").value = projects[0].id;
  $("projects-list").innerHTML = projects.length
    ? ""
    : '<article class="panel empty-state">No projects yet.<br>Search for a study area in Overview, then select Save as project.</article>';
  for (const [i, p] of projects.entries()) {
    const card = document.createElement("article");
    card.className = "panel project-card";
    card.innerHTML = `<span class="project-number">STUDY AREA / ${String(i + 1).padStart(2, "0")}</span><h2>${esc(p.name)}</h2><p>${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}<br>${(p.rated_kw / 1000).toFixed(1)} MW illustrative turbine<br>Saved ${esc(p.created.slice(0, 10))}</p><button class="button outline small">Monitor ↗</button><button class="button primary small">Forecast lab →</button>`;
    const buttons = card.querySelectorAll("button");
    buttons[0].onclick = () => {
      state.capacity = p.rated_kw;
      $("capacity").value = String(p.rated_kw);
      view("overview");
      selectLocation({ name: p.name, lat: p.lat, lon: p.lon });
    };
    buttons[1].onclick = () => {
      $("training-project").value = p.id;
      view("forecast");
    };
    $("projects-list").appendChild(card);
  }
}
function resetReport() {
  ["model-mae", "baseline-mae", "test-count"].forEach(
    (id) => ($(id).textContent = "—"),
  );
  $("training-chart").innerHTML = "";
  $("neural-chart").innerHTML =
    '<div class="empty-state">Your trained forecast will appear here.</div>';
  $("run-prediction").disabled = true;
  $("model-summary").textContent = "No model trained for this project.";
  $("training-title").textContent = "Ready when you are.";
  $("training-progress").style.width = "0";
}
function renderReport(r) {
  $("training-title").textContent =
    `${{ hybrid: "Hybrid RNN + LSTM", lstm: "LSTM", rnn: "RNN" }[r.architecture]} trained.`;
  $("training-description").textContent =
    `${r.source} · ${r.start} to ${r.end} · ${r.epochs_run} epochs`;
  $("model-mae").textContent = r.model.mae_mps.toFixed(2);
  $("baseline-mae").textContent = r.persistence.mae_mps.toFixed(2);
  $("test-count").textContent = r.test_windows.toLocaleString();
  $("training-progress").style.width = "100%";
  $("model-summary").textContent =
    `Test RMSE: ${r.model.rmse_mps.toFixed(2)} m/s · Persistence RMSE: ${r.persistence.rmse_mps.toFixed(2)} m/s. ${r.model.mae_mps < r.persistence.mae_mps ? "Model beat" : "Model did not beat"} persistence on this holdout. Last 7 days of one-hour test forecasts shown below. This is reanalysis validation, not live turbine validation.`;
  chart(
    "training-chart",
    r.test_preview,
    [
      { key: "actual", color: "#a9b69b", label: "ERA5 reference" },
      { key: "prediction", color: "#258c6c", label: "Model" },
      {
        key: "persistence",
        color: "#d2ad71",
        label: "Persistence",
        dash: true,
      },
    ],
    { forecast: false },
  );
  $("run-prediction").disabled = false;
}
async function loadModel() {
  clearInterval(state.jobTimer);
  state.jobTimer = null;
  resetReport();
  const id = $("training-project").value;
  if (!id) return;
  try {
    const data = await api(`/api/projects/${id}/model`);
    if (id !== $("training-project").value) return;
    if (data.report) renderReport(data.report);
    if (data.job?.state === "running") {
      updateJob(data.job);
      state.jobTimer = setInterval(() => pollJob(id), 2000);
    }
  } catch (e) {
    error(e.message);
  }
}
$("training-project").onchange = loadModel;
function updateJob(j) {
  $("train").disabled = j.state === "running";
  $("training-title").textContent = j.stage;
  $("training-description").textContent =
    j.state === "failed"
      ? j.error
      : `${j.rows ? j.rows.toLocaleString() + " hourly rows · " : ""}Epoch ${j.epoch} of ${j.epochs}${j.loss !== undefined ? " · validation MSE (scaled): " + j.loss : ""}`;
  $("training-progress").style.width =
    `${j.state === "complete" ? 100 : Math.max(3, (j.epoch / j.epochs) * 95)}%`;
}
async function pollJob(id) {
  try {
    const data = await api(`/api/projects/${id}/model`);
    if (id !== $("training-project").value) return;
    if (data.job) {
      updateJob(data.job);
      if (data.job.state !== "running") {
        clearInterval(state.jobTimer);
        state.jobTimer = null;
        $("train").disabled = false;
        if (data.job.state === "complete") {
          renderReport(data.report);
          toast("Training complete. Review the holdout comparison.");
        }
      }
    }
  } catch (e) {
    clearInterval(state.jobTimer);
    state.jobTimer = null;
    $("train").disabled = false;
    error(e.message);
  }
}
$("train").onclick = async () => {
  const id = $("training-project").value;
  if (!id) {
    toast("Save a study area as a project first.");
    return;
  }
  clearError();
  $("train").disabled = true;
  try {
    const { job } = await api(`/api/projects/${id}/train`, {
      architecture: $("architecture").value,
      years: Number($("history-years").value),
      epochs: Number($("epochs").value),
    });
    resetReport();
    updateJob(job);
    clearInterval(state.jobTimer);
    state.jobTimer = setInterval(() => pollJob(id), 2000);
  } catch (e) {
    $("train").disabled = false;
    error(e.message);
  }
};
$("run-prediction").onclick = async () => {
  const id = $("training-project").value;
  if (!id) return;
  $("run-prediction").disabled = true;
  try {
    const d = await api(`/api/projects/${id}/predict`);
    chart(
      "neural-chart",
      d.rows,
      [{ key: "speed", color: "#258c6c", label: "Neural wind forecast" }],
      { forecast: false },
    );
    const energy = d.rows.reduce((s, r) => s + r.power_kw, 0) / 1000;
    $("neural-note").textContent =
      `${d.architecture.toUpperCase()} · issued from ${d.issued_at.slice(0, 16)} UTC · ${d.input_source}. Next 24h estimated energy ${energy.toFixed(1)} MWh, from an illustrative curve. ERA5-to-current-model transfer is not calibrated; no uncertainty interval is provided.`;
  } catch (e) {
    error(e.message);
  } finally {
    $("run-prediction").disabled = false;
  }
};
setInterval(() => {
  if (!$("workspace").hidden && state.view === "overview") loadWeather();
}, 600000);
api("/api/session")
  .then(enter)
  .catch(() => {});
