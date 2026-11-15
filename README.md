# Wind Energy Monitoring and Forecasting

## WindScope — local dashboard

A local geospatial research dashboard by Gcina Mdizwa: welcome page, local sign-in, searchable study areas, modelled wind monitoring, illustrative turbine power estimates, saved projects and an RNN/LSTM forecast lab. This is new portfolio software with AI assistance, not the recovered CHPC implementation.

### Start the dashboard

Use Python 3.11 or 3.12 in a virtual environment:

```bash
git clone https://github.com/GcinaMdizwa/wind-energy-monitoring-forecasting.git
cd wind-energy-monitoring-forecasting
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python dashboard_server.py
```

Open **http://localhost:8765**. The server binds only to `127.0.0.1`. `Start_WindScope.bat` is a Windows shortcut after installing the requirements. Keep the server running while using the page. PyTorch is a substantial dependency; CPU is sufficient for the included experiment. Tests additionally require `httpx` for FastAPI's test client.

1. Choose **Explore the dashboard** for a shared guest workspace, or create a separate local profile. Local profile names/passwords are separate from Google and GitHub; never enter those accounts' passwords here. Profile passwords are PBKDF2 hashed. Sessions expire after 12 hours and reset when the server restarts. This local research application is not a hardened multi-user internet service.
2. Search a place or enter WGS84 coordinates, including coastal/offshore points. Adjust single-turbine capacity. The map shows the selected point; the weather service can return a nearby grid point.
3. Review wind, direction, illustrative power and 24-hour estimated energy. Switch the chart between wind and power, and hover for values. Times are UTC. Weather refreshes every ten minutes while Overview is open; upstream results are cached for ten minutes. Failed requests show an error, never synthetic replacement data.
   The **Spatial wind-power potential** panel identifies the municipality or province containing the searched point. Change the area level or the common valid hour (now / +6 / +12 / +24 h), inspect coloured sample points and download boundary plus samples as GeoJSON.
4. **Save as project**, then open **Forecast lab**. Select RNN, LSTM or the hybrid, 1/2/3/5 years of hourly history and the epoch budget. Training runs locally in the background, one job at a time. The UI reports progress and held-out MAE/RMSE against persistence. Models need not outperform the baseline.
5. **Run forecast** uses the latest 48 completed hourly weather values and predicts 24 future wind speeds. The model is project-specific. A 24-hour power/energy estimate is derived from its wind prediction. Historical validation and the new forecast are separate panels.

### What the dashboard measures (and does not)

- Monitoring: [Open-Meteo Forecast API](https://open-meteo.com/en/docs) numerical weather output, hourly wind at **100 m**, not anemometer/buoy/SCADA telemetry. The separately returned current 10 m reading is not mixed into 100 m charts.
- Training: [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), explicitly **ERA5** hourly reanalysis at 100 m. The archive window ends seven days before retrieval. Place search uses [GeoNames via Open-Meteo](https://open-meteo.com/en/docs/geocoding-api). Map © OpenStreetMap contributors. Data attribution: Open-Meteo / ERA5, CC BY 4.0. Free public API use is subject to non-commercial usage terms and rate limits; commercial deployment needs an appropriate plan.
- Power: **illustrative cubic curve**, cut-in 3 m/s, rated 12 m/s, cut-out 25 m/s, adjustable 1–20,000 kW capacity. Zero output at/above cut-out. No calibrated manufacturer curve, air-density correction, wakes, losses or availability. Energy sums 24 hourly estimated kW values × one hour and converts to MWh. These are not measured outputs or bankable yield estimates.
- Model: parallel `nn.RNN` and `nn.LSTM` encoders joined to a dense head. Alternatives use a single RNN or LSTM. Inputs: 48 hours of wind speed, circular wind direction, hour and day-of-year; direct 24-hour wind-speed target. Seasonal features and multi-year data expose seasonal behaviour, but cannot guarantee learning or future skill.
- Validation: chronological 70/15/15 train/validation/test target periods. Windows crossing target-period boundaries are excluded. Scaler statistics use only the training period. Early stopping selects the best validation weights. MAE/RMSE compare identical rolling test origins/horizons with persistence. Overlapping windows are correlated. One holdout is not multi-season walk-forward validation.
- Forecast transfer: the ERA5-trained model consumes current forecast-provider weather estimates; this distribution shift is **not calibrated**. No measured-power training target, sea-state inputs, uncertainty bands or automatic online learning is implemented. Retraining is explicit. Measured mast/buoy/SCADA data and proper walk-forward tests are required before operational coastal power forecasting.
- Privacy: local profiles, projects, model checkpoints and reports are stored in ignored `local_state/`. Searches and coordinates go to public weather/geocoding/map providers. No personal/company datasets or credentials are published. Do not expose this development server to the internet.

```bash
python -m unittest test_dashboard test_wind_forecast test_spatial_power -v
```

New dashboard files: `dashboard_server.py`, `wind_data.py`, `recurrent_forecast.py`, `dashboard.html`, `dashboard.css`, `dashboard.js`, `test_dashboard.py`, `Start_WindScope.bat`. The original educational Random Forest example below remains separate.

### Municipality / province spatial view

`spatial_power.py` queries the [NDMC SouthAfricaBoundaries service](https://gislive21.ndmc.gov.za/hosting/rest/services/SouthAfricaBoundaries/MapServer), which credits the Municipal Demarcation Board. A point-in-polygon query identifies a containing local municipality (layer 2) or province (layer 0). The service does not specify the boundary vintage; these are **not verified as 2026 demarcations**. Ward-level mapping is not implemented. Offshore points outside these administrative boundaries return a clear no-boundary message.

The map uses up to 25 centres of a 5×5 regular grid in **EPSG:6933 equal-area coordinates**, clipped to the served polygon, including holes/multipart geometry. Display/analysis geometry is simplified by the service with a maximum offset of 0.001°. Very narrow polygons use an interior representative point if no grid centres fall inside. Map and export report sample spacing. This is a coarse research sampling scheme, not a high-resolution wind resource assessment.

A batch Open-Meteo request retrieves **100 m hourly wind at every sample**. Every coloured point is evaluated at one common UTC valid time. The same selected turbine capacity and illustrative curve are used everywhere. Points can share a coarse weather-model grid; the unique grid count is shown. Missing samples are omitted and counted explicitly. No interpolated raster, measured generation, installed capacity, electricity flows or municipal aggregate is claimed. The sample mean/range describes the queried points, not an area-weighted energy yield; **do not sum hypothetical turbines into a municipal total**. The spatial view uses numerical weather, not the point-specific neural model.

Mapping UI: `spatial_map.js`; geometry/sampling tests: `test_spatial_power.py`. [Leaflet 1.9.4](https://leafletjs.com/) is vendored with its BSD-2-Clause `LEAFLET-LICENSE.txt`; map tiles © OpenStreetMap contributors. Public boundary geometry and weather are fetched at runtime, not bundled in the repository. Provider availability, boundary vintage, coarse grid resolution and siting constraints all limit interpretation. Real electricity-distribution mapping requires a separate, permissioned utility/grid dataset.

---

Repository preparation for Gcina Mdizwa's personal geospatial portfolio, documenting collaborative CHPC workshop work on wind-energy monitoring and forecasting.

**Status:** a new educational Python baseline for short-term turbine-power forecasting. It is not the original CHPC implementation or an operational near-real-time system. The included demo uses synthetic data; it does not reproduce a CHPC scientific result.

## Run the new example

Use Python 3.11 or newer in a virtual environment:

```bash
python -m pip install -r requirements.txt
python wind_forecast.py --demo --horizon 1 --output outputs/demo
python -m unittest -v
```

For a CSV you have permission to use:

```bash
python wind_forecast.py --csv observations.csv --horizon 1 --output outputs/local
```

Input columns: `timestamp`, `wind_speed_mps`, `wind_direction_deg`, `power_kw`. Each timestamp must include `Z` or a UTC offset. Supply a single turbine, a regular interval and at least 200 rows. Missing values, duplicate timestamps and irregular intervals are rejected instead of silently filled. `--horizon` is 1-24 sampling intervals: at 10-minute sampling, horizon 6 means one hour ahead.

Outputs include MAE/RMSE in kW for a Random Forest and persistence baseline, timestamped held-out predictions, and a forecast issued from the latest observation. The model uses current and lagged observations only, with a chronological 80/20 split and a purged boundary to keep training targets before the first test issue time. Test rows represent rolling issue times with observations available at each issue time; this is not a multi-step forecast made from one fixed historical origin.

Re-running against an updated CSV provides a batch snapshot. No sensor, SCADA service, live weather feed or scheduled acquisition is connected. The baseline deliberately uses a compact Random Forest rather than claiming to reconstruct the workshop's LSTM. Outputs are power in kW, not energy in kWh. No uncertainty intervals or turbine-specific operational limits are modelled.

## Workshop context

The CHPC contribution is titled **A near real-time spatial monitoring and forecasting of wind energy using geospatial big data**. Its published description discusses geospatial and meteorological data integration, turbine measurements, and recurrent neural networks / LSTM forecasting, with evaluation using MAE and RMSE.

- [CHPC contribution and author record](https://events.chpc.ac.za/event/155/contributions/2684/)
- [CHPC 2024 workshop timetable](https://events.chpc.ac.za/event/139/timetable/?view=indico_weeks_view)

The contribution appears on the 2025 event site, while its attached workshop proposal explicitly refers to the 2024 meeting. These records are cited as found; a specific year of Gcina's delivery has not yet been confirmed. The public materials document the proposed approach, not a reproduced performance result.

## Collaborative credit

The CHPC primary-author record lists the following people (duplicate entries removed, source order retained):

- Onesimo Madikizela
- Aphelele Khalakahla
- Sange Mfamana
- Phila Sibandze
- Kgabo Humphrey Thamaga
- Nomaxabiso Ngogodo
- Gcina Mdizwa
- Sinethemba Funani
- Gbenga Abayomi Afuye


## Original code and future additions

A Colab search in Gcina's personal account located and downloaded `Untitled18.ipynb` (nine cells) and `Untitled19.ipynb` (two cells). The first contains an incomplete wind-siting cell plus mainly housing-site experiments; the second contains mapping and housing-site code. They are not a recovered time-series wind-power forecasting implementation. Searches for `LSTM` returned no notebook matches. This is a bounded search, not proof that no original notebook exists elsewhere.

The downloaded notebooks remain outside this public repository. The first wind cell contains an incomplete feature-stack expression, undefined inputs, an absent saved model dependency, and inference-time scaler fitting. Those issues prevent treating it as a reproduced forecasting result. Unrelated cells, private asset paths and notebook outputs are not republished.

`wind_forecast.py`, its tests and the accompanying example notebook are new work prepared for this personal portfolio with AI assistance in November 2026. The original workshop author team is credited for the collaborative research context, not assigned authorship of this new baseline code.

Original notebooks, newly written examples and reproduced results will be clearly distinguished. Original author credit will be retained. Private paths, project identifiers, credentials, personal information and restricted assets will be reviewed before anything is published.

## Review priorities

1. Locate the original workshop forecasting notebook and trained model, if available.
2. Establish data provenance, contributor attribution and applicable reuse terms before importing original material.
3. Evaluate real observations with multiple walk-forward test periods and a separate validation strategy for model selection.
4. Add suitable forecast uncertainty and turbine operational checks.
5. Connect a documented live feed only when its source, latency, access terms and monitoring requirements are known.

## Licence

No licence is granted for the collaborative workshop materials or recovered notebooks at this stage. Linking the public CHPC record does not transfer ownership or establish permission to relicense other contributors' code or datasets.
