/* global L, state, api, esc, toast, $ */
// Same-origin module script, loaded after dashboard.js; no remote execution.
let spatialMap,
  spatialLayers,
  spatialRequest = 0,
  spatialResult = null;
function powerColour(percent) {
  return percent < 10
    ? "#d8e8c0"
    : percent < 30
      ? "#b5d57a"
      : percent < 50
        ? "#7dbb63"
        : percent < 75
          ? "#38986c"
          : "#125f58";
}
async function loadSpatial() {
  const id = ++spatialRequest;
  spatialResult = null;
  $("download-spatial").disabled = true;
  $("spatial-status").textContent = "Loading boundary and sampled weather…";
  $("spatial-area-name").textContent = "Identifying the containing area…";
  $("spatial-time").textContent =
    "All point estimates share a common UTC timestamp.";
  ["spatial-mean", "spatial-range", "spatial-count", "spatial-spacing"].forEach(
    (k) => ($(k).textContent = "—"),
  );
  $("spatial-table").replaceChildren();
  $("spatial-provenance").textContent = "";
  if (spatialLayers) spatialLayers.clearLayers();
  try {
    const { lat, lon } = state.location;
    const level = $("boundary-level").value;
    const d = await api(
      `/api/spatial-power?lat=${lat}&lon=${lon}&level=${level}&rated_kw=${state.capacity}&ahead=${$("spatial-hour").value}`,
    );
    if (id !== spatialRequest) return;
    spatialResult = d;
    if (!spatialMap) {
      spatialMap = L.map("spatial-map", { scrollWheelZoom: false }).setView(
        [lat, lon],
        9,
      );
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>',
      }).addTo(spatialMap);
      spatialLayers = L.featureGroup().addTo(spatialMap);
    }
    const boundary = L.geoJSON(d.boundary, {
      style: {
        color: "#1b6964",
        weight: 2,
        fillColor: "#b7d1a3",
        fillOpacity: 0.09,
      },
    }).addTo(spatialLayers);
    for (const p of d.samples) {
      const marker = L.circleMarker([p.lat, p.lon], {
        radius: 11,
        color: "#fff",
        weight: 1.5,
        fillColor: powerColour(p.capacity_percent),
        fillOpacity: 0.95,
      });
      marker
        .bindPopup(
          `<b>Sample ${p.sample_id} · ${esc(d.boundary.properties.name)}</b><br>${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}<br><b>${p.power_kw.toFixed(0)} kW</b> per ${d.rated_kw.toLocaleString()} kW turbine<br>100 m wind: ${p.speed.toFixed(1)} m/s<br>${p.capacity_percent.toFixed(1)}% of rated output<br>${esc(d.valid_time.slice(0, 16).replace("T", " "))} UTC<br><small>Modelled weather + illustrative power curve</small>`,
        )
        .addTo(spatialLayers);
    }
    L.circleMarker([lat, lon], {
      radius: 5,
      color: "#192d35",
      weight: 2,
      fillColor: "#fff",
      fillOpacity: 1,
    })
      .bindTooltip("Your searched location")
      .addTo(spatialLayers);
    spatialMap.invalidateSize();
    spatialMap.fitBounds(boundary.getBounds(), {
      padding: [25, 25],
      maxZoom: 12,
    });
    $("spatial-area-name").textContent =
      `${d.boundary.properties.name} · ${level === "municipality" ? "Municipality" : "Province"}`;
    $("spatial-time").textContent =
      `${d.valid_time.slice(0, 16).replace("T", " ")} UTC · ${d.ahead_hours === 0 ? "current modelled hour" : d.ahead_hours + "h weather forecast"}`;
    $("spatial-mean").textContent = d.summary.sample_mean_kw.toLocaleString();
    $("spatial-range").textContent =
      `${Math.round(d.summary.sample_min_kw)}–${Math.round(d.summary.sample_max_kw)}`;
    $("spatial-count").textContent = d.samples.length;
    $("spatial-grid-count").textContent =
      `${d.unique_weather_grid_points} unique weather-grid points`;
    $("spatial-spacing").textContent = `${d.spacing_x_km} × ${d.spacing_y_km}`;
    $("spatial-status").textContent = d.missing_samples
      ? `${d.missing_samples} samples unavailable · partial coverage`
      : "Boundary identified · samples ready";
    $("spatial-note").textContent =
      `${d.sampling}. ${d.limitations} Ward-level mapping is not included in this version.`;
    $("spatial-provenance").textContent =
      `Boundary: ${d.boundary.properties.boundary_credit}. Vintage: ${d.boundary.properties.boundary_vintage}. Geometry simplified up to 0.001° for this research view. Weather: Open-Meteo at 100 m; retrieved ${d.fetched_at.slice(0, 16)} UTC. Point estimate uses a ${d.rated_kw.toLocaleString()} kW illustrative turbine with 3/12/25 m/s cut-in/rated/cut-out speeds. Sample mean is not an area-weighted or municipal aggregate.`;
    for (const p of [...d.samples].sort((a, b) => b.power_kw - a.power_kw)) {
      const tr = document.createElement("tr");
      [
        p.sample_id,
        p.lat.toFixed(5),
        p.lon.toFixed(5),
        p.speed.toFixed(1),
        p.power_kw.toFixed(1),
      ].forEach((v) => {
        const td = document.createElement("td");
        td.textContent = v;
        tr.appendChild(td);
      });
      $("spatial-table").appendChild(tr);
    }
    $("download-spatial").disabled = false;
  } catch (e) {
    if (id !== spatialRequest) return;
    $("spatial-status").textContent = "Area mapping unavailable";
    $("spatial-area-name").textContent = "No verified area map available";
    $("spatial-note").textContent = e.message;
  }
}
$("boundary-level").onchange = loadSpatial;
$("spatial-hour").onchange = loadSpatial;
$("refresh-spatial").onclick = loadSpatial;
$("download-spatial").onclick = () => {
  if (!spatialResult) return;
  const d = spatialResult;
  const fc = {
    type: "FeatureCollection",
    metadata: {
      valid_time: d.valid_time,
      source: d.source,
      rated_kw: d.rated_kw,
      sampling: d.sampling,
      limitations: d.limitations,
      boundary_credit: d.boundary.properties.boundary_credit,
    },
    features: [
      d.boundary,
      ...d.samples.map((p) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [p.lon, p.lat] },
        properties: {
          ...p,
          valid_time: d.valid_time,
          power_unit: "kW",
          wind_unit: "m/s",
          wind_height_m: 100,
          power_type: "Illustrative per-turbine estimate",
        },
      })),
    ],
  };
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(fc, null, 2)], { type: "application/geo+json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `WindScope_${d.boundary.properties.name.replace(/[^a-z0-9]+/gi, "_")}_${d.ahead_hours}h.geojson`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
window.addEventListener("resize", () => {
  if (spatialMap) spatialMap.invalidateSize();
});
document.querySelectorAll('[data-view="overview"]').forEach((b) =>
  b.addEventListener("click", () =>
    requestAnimationFrame(() => {
      if (spatialMap) {
        spatialMap.invalidateSize();
        if (spatialResult)
          spatialMap.fitBounds(L.geoJSON(spatialResult.boundary).getBounds(), {
            padding: [25, 25],
            maxZoom: 12,
          });
      }
    }),
  ),
);
api("/api/session")
  .then(enter)
  .catch(() => {});
