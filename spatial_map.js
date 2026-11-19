/* global L, state, api, esc, $ */
let spatialMap,
  spatialLayers,
  spatialRequest = 0,
  spatialResult = null,
  spatialPoll = null;
const isoDate = (d) => d.toISOString().slice(0, 10);
const archiveLatest = new Date(Date.now() - 7 * 86400000);
const previousMonth = new Date(
  Date.UTC(archiveLatest.getUTCFullYear(), archiveLatest.getUTCMonth(), 0),
);
let chosenDate = isoDate(
  new Date(
    Date.UTC(previousMonth.getUTCFullYear(), previousMonth.getUTCMonth(), 1),
  ),
);
$("era5-end").value = isoDate(previousMonth);
$("era5-end").max = isoDate(archiveLatest);
$("era5-hour").innerHTML = Array.from(
  { length: 24 },
  (_, i) =>
    `<option value="${i}">${String(i).padStart(2, "0")}:00 UTC</option>`,
).join("");
function configurePeriod() {
  const mode = $("era5-period").value,
    input = $("era5-date");
  if (input.value) {
    if (input.type === "date") chosenDate = input.value;
    else if (input.type === "month") chosenDate = input.value + "-01";
    else if (input.type === "number") chosenDate = input.value + "-01-01";
  }
  $("era5-end-label").hidden = mode !== "custom";
  $("era5-hour-label").hidden = mode !== "hour";
  if (mode === "month") {
    input.type = "month";
    input.min = "1940-01";
    input.max = isoDate(previousMonth).slice(0, 7);
    input.value = chosenDate.slice(0, 7);
    $("era5-date-label").textContent = "Month";
  } else if (mode === "year") {
    input.type = "number";
    input.min = "1940";
    input.max = archiveLatest.getUTCFullYear() - 1;
    input.value = Math.min(Number(chosenDate.slice(0, 4)), Number(input.max));
    $("era5-date-label").textContent = "Complete year";
  } else {
    input.type = "date";
    input.min = "1940-01-01";
    input.max = isoDate(archiveLatest);
    input.value = chosenDate;
    $("era5-date-label").textContent =
      mode === "custom" ? "Start date" : "Date";
  }
}
configurePeriod();
function selectedPeriod() {
  const mode = $("era5-period").value,
    v = $("era5-date").value;
  if (!$("era5-date").checkValidity() || !v)
    throw new Error("Choose a valid historical date or complete month/year.");
  let start,
    end,
    hour = null;
  if (mode === "month") {
    start = v + "-01";
    const [y, m] = v.split("-").map(Number);
    end = isoDate(new Date(Date.UTC(y, m, 0)));
  } else if (mode === "year") {
    start = v + "-01-01";
    end = v + "-12-31";
  } else {
    start = v;
    end = mode === "custom" ? $("era5-end").value : v;
    if (mode === "hour") hour = Number($("era5-hour").value);
  }
  if (!end) throw new Error("Choose an end date.");
  return { start, end, hour };
}
function colour(value, wind) {
  const p = wind ? (value / 16) * 100 : value;
  return p < 10
    ? "#d8e8c0"
    : p < 30
      ? "#b5d57a"
      : p < 50
        ? "#7dbb63"
        : p < 75
          ? "#38986c"
          : "#125f58";
}
async function loadSpatial() {
  const id = ++spatialRequest;
  clearTimeout(spatialPoll);
  spatialResult = null;
  $("download-spatial").disabled = true;
  $("spatial-status").textContent = "Preparing ERA5 layer…";
  $("spatial-area-name").textContent = "Identifying the containing area…";
  ["spatial-mean", "spatial-range", "spatial-count"].forEach(
    (k) => ($(k).textContent = "—"),
  );
  $("spatial-table").replaceChildren();
  $("spatial-provenance").textContent = "";
  if (spatialLayers) spatialLayers.clearLayers();
  try {
    const range = selectedPeriod(),
      { lat, lon } = state.location;
    const { job } = await api("/api/era5-layer", {
      lat,
      lon,
      level: $("boundary-level").value,
      rated_kw: state.capacity,
      ...range,
    });
    if (id !== spatialRequest) return;
    await pollERA5(job.id, id);
  } catch (e) {
    if (id === spatialRequest) spatialError(e.message);
  }
}
function spatialError(message) {
  $("spatial-status").textContent = "ERA5 layer unavailable";
  $("spatial-area-name").textContent = "No ERA5 layer loaded";
  $("spatial-note").textContent = message;
}
async function pollERA5(jid, id) {
  try {
    const { job } = await api("/api/era5-layer/" + jid);
    if (id !== spatialRequest) return;
    if (job.state === "failed") {
      spatialError(job.error);
      return;
    }
    if (job.state === "complete") {
      spatialResult = job.result;
      renderERA5();
      return;
    }
    $("spatial-status").textContent =
      `${job.stage}${job.total ? " · " + job.completed + " / " + job.total + " cells" : ""}`;
    $("spatial-note").textContent =
      "Downloading and aggregating hourly ERA5 data in the background. Large areas and annual periods can take several minutes. The archive is cached locally for reuse.";
    spatialPoll = setTimeout(() => pollERA5(jid, id), 1500);
  } catch (e) {
    if (id === spatialRequest) spatialError(e.message);
  }
}
function periodLabel(d) {
  return d.hour_utc !== null
    ? `${d.start_date} ${String(d.hour_utc).padStart(2, "0")}:00 UTC`
    : `${d.start_date} to ${d.end_date} · ${d.hours_per_cell.toLocaleString()} hourly values per cell · UTC`;
}
function renderERA5() {
  const d = spatialResult;
  if (!d) return;
  const wind = $("era5-metric").value === "wind_speed_mps",
    key = wind ? "wind_speed_mps" : "power_kw";
  const stats = d.summary[key];
  if (!spatialMap) {
    spatialMap = L.map("spatial-map", { scrollWheelZoom: false }).setView(
      [state.location.lat, state.location.lon],
      9,
    );
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>',
    }).addTo(spatialMap);
    spatialLayers = L.featureGroup().addTo(spatialMap);
  }
  spatialLayers.clearLayers();
  L.geoJSON(d.cells, {
    style: (f) => ({
      color: "#496c5c",
      weight: 0.45,
      fillColor: colour(
        wind ? f.properties.wind_speed_mps : f.properties.capacity_percent,
        wind,
      ),
      fillOpacity: 0.75,
    }),
    onEachFeature: (f, l) => {
      const p = f.properties;
      l.bindPopup(
        `<b>ERA5 cell ${p.cell_id} · ${esc(d.boundary.properties.name)}</b><br>Grid centre: ${p.lat.toFixed(2)}, ${p.lon.toFixed(2)}<br><b>${p.wind_speed_mps.toFixed(2)} m/s</b> · 100 m wind<br><b>${p.power_kw.toFixed(1)} kW</b> · estimated ${d.hour_utc === null ? "mean " : ""}power per turbine<br>${p.energy_mwh.toFixed(2)} MWh per turbine over ${p.hours} hour(s)<br>${esc(periodLabel(d))}<br><small>ERA5 via Open-Meteo · 0.25° grid<br>Power curve applied hourly, then averaged.<br>Not measured or installed generation.</small>`,
      );
    },
  }).addTo(spatialLayers);
  const b = L.geoJSON(d.boundary, {
    interactive: false,
    style: { color: "#1b6964", weight: 2, fillOpacity: 0 },
  }).addTo(spatialLayers);
  spatialMap.invalidateSize();
  spatialMap.fitBounds(b.getBounds(), { padding: [25, 25], maxZoom: 12 });
  $("spatial-area-name").textContent =
    `${d.boundary.properties.name} · ${d.boundary.properties.level === "municipality" ? "Municipality" : "Province"}`;
  $("spatial-time").textContent = periodLabel(d);
  $("spatial-mean").textContent = stats.area_weighted_mean.toFixed(
    wind ? 2 : 1,
  );
  $("spatial-range").textContent =
    `${stats.min.toFixed(wind ? 1 : 0)}–${stats.max.toFixed(wind ? 1 : 0)}`;
  $("spatial-mean-unit").textContent = $("spatial-range-unit").textContent =
    wind ? "m/s · 100 m wind" : "kW per illustrative turbine";
  $("spatial-count").textContent = d.cells.features.length;
  $("spatial-grid-count").textContent =
    `${d.coverage_percent.toFixed(1)}% area with complete data`;
  $("spatial-status").textContent =
    `ERA5 layer ready${d.missing_cells ? " · " + d.missing_cells + " incomplete cells omitted" : ""}`;
  $("spatial-note").textContent = d.limitations;
  $("era5-legend").innerHTML =
    `<span>${wind ? "ERA5 wind speed at 100 m" : "Estimated mean power / rated turbine capacity"}</span><i class="scale-low"></i><span>0${wind ? " m/s" : "%"}</span><i class="scale-mid"></i><span>${wind ? "8 m/s" : "50%"}</span><i class="scale-high"></i><span>${wind ? "16+ m/s" : "100%"}</span><small>Clipped 0.25° display cells · no spatial interpolation</small>`;
  $("spatial-provenance").textContent =
    `${d.source}. ${d.method} Retrievals ${d.retrieved_first.slice(0, 16)} to ${d.retrieved_last.slice(0, 16)} UTC. Turbine: ${d.rated_kw} kW, illustrative 3/12/25 m/s cut-in/rated/cut-out. Boundary: ${d.boundary.properties.boundary_credit}; vintage: ${d.boundary.properties.boundary_vintage}. No elevation adjustment or inferred fine-scale variation.`;
  $("spatial-table").replaceChildren();
  for (const f of [...d.cells.features].sort(
    (a, b) => b.properties[key] - a.properties[key],
  )) {
    const p = f.properties,
      tr = document.createElement("tr");
    [
      p.cell_id,
      p.lat.toFixed(2),
      p.lon.toFixed(2),
      p.wind_speed_mps.toFixed(2),
      p.power_kw.toFixed(1),
    ].forEach((v) => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });
    $("spatial-table").appendChild(tr);
  }
  $("download-spatial").disabled = false;
}
$("era5-period").onchange = configurePeriod;
$("boundary-level").onchange = loadSpatial;
$("era5-metric").onchange = renderERA5;
$("refresh-spatial").onclick = loadSpatial;
$("download-spatial").onclick = () => {
  if (!spatialResult) return;
  const d = spatialResult;
  const fc = {
    type: "FeatureCollection",
    metadata: {
      source: d.source,
      start_date: d.start_date,
      end_date: d.end_date,
      hour_utc: d.hour_utc,
      grid_degrees: d.grid_degrees,
      rated_kw: d.rated_kw,
      method: d.method,
      limitations: d.limitations,
      coverage_percent: d.coverage_percent,
      summary: d.summary,
    },
    features: [d.boundary, ...d.cells.features],
  };
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(fc, null, 2)], { type: "application/geo+json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `WindScope_ERA5_${d.boundary.properties.name.replace(/[^a-z0-9]+/gi, "_")}_${d.start_date}_${d.end_date}.geojson`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
function resizeSpatial() {
  if (spatialMap) {
    spatialMap.invalidateSize();
    if (spatialResult)
      spatialMap.fitBounds(L.geoJSON(spatialResult.boundary).getBounds(), {
        padding: [25, 25],
        maxZoom: 12,
      });
  }
}
window.addEventListener("resize", resizeSpatial);
document
  .querySelectorAll('[data-view="overview"]')
  .forEach((b) =>
    b.addEventListener("click", () => requestAnimationFrame(resizeSpatial)),
  );
api("/api/session")
  .then(enter)
  .catch(() => {});
