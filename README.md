# Wind Energy Monitoring and Forecasting

This project started with a CHPC workshop contribution I co-authored with colleagues: *A near real-time spatial monitoring and forecasting of wind energy using geospatial big data*. I wanted a working tool I could explore myself, so I built **WindScope**, a local dashboard that runs on my own machine. I can search any place in South Africa (or a point offshore), see modelled 100 m wind and illustrative turbine power, map wind-power potential across municipalities and provinces, and train my own RNN, LSTM or hybrid models on years of ERA5 history.

It's a research and learning tool, not an operational forecasting system. I've tried to be clear throughout about what the data and models can and can't tell us. I wrote the new code with AI assistance. The research idea comes from a team effort, and I credit everyone who contributed (see [Collaborative credit](#collaborative-credit)).

## WindScope — my local dashboard

WindScope has a welcome page, local sign-in, searchable study areas, modelled wind monitoring, illustrative turbine power estimates, saved projects and an RNN/LSTM forecast lab.

### Starting the dashboard

I use Python 3.11 or 3.12 in a virtual environment:

```bash
git clone https://github.com/GcinaMdizwa/wind-energy-monitoring-forecasting.git
cd wind-energy-monitoring-forecasting
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python dashboard_server.py
```

Then open **http://localhost:8765**. The server only binds to `127.0.0.1`. On Windows, once the requirements are installed, `Start_WindScope.bat` is a shortcut. Keep the server running while you use the page. PyTorch is a fairly large dependency, but a CPU is enough for the included experiment. The tests also need `httpx` for FastAPI's test client.

### How I use it

1. Choose **Explore the dashboard** for a shared guest workspace, or create a separate local profile. Local profile names and passwords are separate from Google and GitHub, so never enter those accounts' passwords here. Profile passwords are PBKDF2-hashed. Sessions expire after 12 hours and reset when the server restarts. I built this as a local research application, not a hardened multi-user internet service.
2. Search for a place or enter WGS84 coordinates, including coastal and offshore points, and adjust the single-turbine capacity. The map shows the selected point; the weather service may return a nearby grid point.
3. Review wind speed, direction, illustrative power and estimated 24-hour energy. The chart switches between wind and power, and you can hover for values. All times are UTC. Weather refreshes every ten minutes while Overview is open, and upstream results are cached for ten minutes. If a request fails, the dashboard shows an error. It never fills in synthetic data.
   The **ERA5 wind & power layer** panel finds the municipality or province that contains the searched point. Choose a selected UTC hour, daily/monthly/annual average or custom period, switch between wind speed and estimated power, then select **Load ERA5 layer**. You can inspect the clipped grid cells and download their values with the boundary as GeoJSON.
4. **Save as project**, then open the **Forecast lab**. Pick RNN, LSTM or the hybrid, 1/2/3/5 years of hourly history, and the epoch budget. Training runs locally in the background, one job at a time. The UI reports progress and held-out MAE/RMSE against a persistence baseline. I don't assume the models will beat that baseline, and they don't always.
5. **Run forecast** takes the latest 48 completed hourly weather values and predicts the next 24 hourly wind speeds. Each model belongs to its project. The 24-hour power and energy estimate is derived from the predicted wind. Historical validation and the new forecast appear in separate panels.

### What the dashboard measures (and what it doesn't)

- **Monitoring:** [Open-Meteo Forecast API](https://open-meteo.com/en/docs) numerical weather output, hourly wind at **100 m**. This is not anemometer, buoy or SCADA telemetry. The separately returned current 10 m reading is kept out of the 100 m charts.
- **Training data:** [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), explicitly **ERA5** hourly reanalysis at 100 m. The archive window ends seven days before retrieval. Place search uses [GeoNames via Open-Meteo](https://open-meteo.com/en/docs/geocoding-api). Map © OpenStreetMap contributors. Data attribution: Open-Meteo / ERA5, CC BY 4.0. Free public API use is subject to non-commercial terms and rate limits; a commercial deployment would need an appropriate plan.
- **Power:** an **illustrative cubic curve** with cut-in at 3 m/s, rated at 12 m/s and cut-out at 25 m/s, with capacity adjustable from 1 to 20,000 kW. Output is zero at or above cut-out. There's no calibrated manufacturer curve, air-density correction, wake effects, losses or availability. Energy is the sum of 24 hourly kW estimates × one hour, converted to MWh. These are not measured outputs or bankable yield estimates.
- **Model:** parallel `nn.RNN` and `nn.LSTM` encoders joined to a dense head, with single-RNN and single-LSTM alternatives. Inputs are 48 hours of wind speed, circular wind direction, hour and day-of-year; the target is a direct 24-hour wind-speed forecast. Seasonal features and multi-year data expose seasonal behaviour, but they can't guarantee the model learns it or that it will be skilful in future.
- **Validation:** chronological 70/15/15 train/validation/test target periods. Windows that cross period boundaries are excluded, scaler statistics come only from the training period, and early stopping keeps the best validation weights. MAE/RMSE are compared with persistence over identical rolling test origins and horizons. Overlapping windows are correlated, and a single holdout is not multi-season walk-forward validation.
- **Forecast transfer:** the model is trained on ERA5 but run on current forecast-provider weather, and I have **not calibrated** for that distribution shift. There's no measured-power training target, no sea-state inputs, no uncertainty bands and no automatic online learning; retraining is explicit. Before anyone uses this for operational coastal power forecasting, it would need measured mast, buoy or SCADA data and proper walk-forward testing.
- **Privacy:** local profiles, projects, model checkpoints and reports are stored in the git-ignored `local_state/` folder. Searches and coordinates are sent to public weather, geocoding and map providers. I haven't published any personal or company datasets or credentials. Please don't expose this development server to the internet.

To run the tests:

```bash
python -m unittest test_dashboard test_wind_forecast test_spatial_power test_era5_layer -v
```

The dashboard files are `dashboard_server.py`, `wind_data.py`, `recurrent_forecast.py`, `dashboard.html`, `dashboard.css`, `dashboard.js`, `test_dashboard.py` and `Start_WindScope.bat`. The earlier educational Random Forest example (below) is kept separate.

### Municipality / province spatial view

`spatial_power.py` queries the [NDMC SouthAfricaBoundaries service](https://gislive21.ndmc.gov.za/hosting/rest/services/SouthAfricaBoundaries/MapServer), which credits the Municipal Demarcation Board. A point-in-polygon query finds the local municipality (layer 2) or province (layer 0) containing the point. The service doesn't state the boundary vintage, so I have **not verified these as 2026 demarcations**. I haven't implemented ward-level mapping. Offshore points outside the administrative boundaries return a clear no-boundary message.

The visible layer now uses **ERA5 historical reanalysis**, through `era5_layer.py`, instead of the earlier forecast sample points. I explicitly request `models=era5`, hourly `wind_speed_100m`, m/s, UTC, `cell_selection=nearest` and `elevation=nan` for every coordinate, so there is no elevation adjustment. The map clips 0.25° grid-centred display footprints to the returned polygon, including holes and multipart geometry. It doesn't interpolate between cells or create finer wind detail at municipal borders. The service simplifies boundary geometry up to 0.001°, and the display footprints approximate ERA5 grid support. Returned grid coordinates and the complete hourly time axis are checked before using the data.

I can select one UTC hour, a full day, a complete month/year (including leap years), or a custom inclusive range of up to 366 days. Dates run from 1940 to seven days before today, leaving an archive-availability buffer. Province layers include every intersecting display cell, up to 1,200, rather than downsampling to a few sites. Data are fetched in batches of 16 and gzip-cached in the git-ignored `local_state/era5_cache/` folder. A background queue reports progress. Large annual province layers can take several minutes and are subject to provider limits; failures don't cause a switch to a different weather model. Jobs/results belong to their local session owner. Jobs reset on server restart; the archive cache persists.

For period averages, I calculate turbine power **hour by hour before averaging**, rather than applying the nonlinear curve to mean wind speed. Each cell includes mean wind, mean estimated power, and energy over the selected hours. A selected-hour layer uses just that hour. Cells with missing required hours are omitted and coverage is reported. The area-wide mean uses clipped cell areas in EPSG:6933 as weights. I show the period, coverage, cell range and assumptions in the map and export. These are illustrative per-turbine estimates, not measured generation, installed capacity or municipal totals, so **please don't add hypothetical turbines into a municipal total**. This spatial layer uses historical ERA5, not the point-specific neural forecast.

The earlier forecast sampling code (`spatial_power.distribution` and `/api/spatial-power`) remains a separate legacy API, tested independently. It isn't the visible ERA5 layer.

The mapping UI is in `spatial_map.js`; grid clipping, averaging, coordinate/time checks and cache tests are in `test_era5_layer.py`. [Leaflet 1.9.4](https://leafletjs.com/) is vendored with its BSD-2-Clause `LEAFLET-LICENSE.txt`; map tiles © OpenStreetMap contributors. ERA5 is credited to ECMWF/Copernicus via Open-Meteo. Boundary geometry and weather are fetched at runtime, not bundled in this repository. Provider availability, boundary vintage, coarse grid resolution and real siting constraints all limit how far these maps can be read. Real electricity-distribution mapping would need a separate, permissioned utility or grid dataset.

---

## The earlier Random Forest baseline

Before WindScope, I prepared this repository for my personal geospatial portfolio with a simpler educational example: a Python baseline for short-term turbine-power forecasting. The included demo uses synthetic data so anyone can run it straight away.

### Running the example

I use Python 3.11 or newer in a virtual environment:

```bash
python -m pip install -r requirements.txt
python wind_forecast.py --demo --horizon 1 --output outputs/demo
python -m unittest -v
```

With a CSV you have permission to use:

```bash
python wind_forecast.py --csv observations.csv --horizon 1 --output outputs/local
```

The input columns are `timestamp`, `wind_speed_mps`, `wind_direction_deg` and `power_kw`. Each timestamp must include `Z` or a UTC offset. The data should be for a single turbine, at a regular interval, with at least 200 rows. Missing values, duplicate timestamps and irregular intervals are rejected rather than silently filled. `--horizon` is 1–24 sampling intervals: with 10-minute data, horizon 6 means one hour ahead.

The outputs include MAE/RMSE in kW for a Random Forest and a persistence baseline, timestamped held-out predictions, and a forecast issued from the latest observation. The model only uses current and lagged observations, with a chronological 80/20 split and a purged boundary so that all training targets come before the first test issue time. Test rows are rolling issue times using only observations available at each one; this is not a multi-step forecast from one fixed historical origin.

Re-running against an updated CSV gives a batch snapshot. No sensor, SCADA service, live weather feed or scheduled acquisition is connected. I deliberately used a compact Random Forest here rather than claiming to reconstruct the workshop's LSTM. Outputs are power in kW, not energy in kWh, and I haven't modelled uncertainty intervals or turbine-specific operating limits.

## Workshop context

The CHPC contribution is titled **A near real-time spatial monitoring and forecasting of wind energy using geospatial big data**. Its published description covers integrating geospatial and meteorological data with turbine measurements, and forecasting with recurrent neural networks / LSTMs, evaluated using MAE and RMSE.

- [CHPC contribution and author record](https://events.chpc.ac.za/event/155/contributions/2684/)
- [CHPC 2024 workshop timetable](https://events.chpc.ac.za/event/139/timetable/?view=indico_weeks_view)

The idea behind the work was to bring together geospatial big data, weather data and deep learning so that wind energy can be monitored across space and forecast in near real time, supporting better planning for renewable energy in South Africa.

## Collaborative credit

This was team work. The people who contributed to the CHPC workshop project are:

- Onesimo Madikizela
- Aphelele Khalakahla
- Sange Mfamana
- Phila Sibandze
- Kgabo Humphrey Thamaga
- Nomaxabiso Ngogodo
- Gcina Mdizwa
- Sinethemba Funani
- Gbenga Abayomi Afuye

## About the code

The WindScope dashboard, `wind_forecast.py`, the tests and the example notebook are work I built for my portfolio with AI assistance in November 2026, inspired by the workshop project above.

## My next priorities

1. Evaluate the models on real observations, with multiple walk-forward test periods and a separate validation strategy for model selection.
2. Add proper forecast uncertainty and turbine operating checks.
3. Connect a live data feed only once I know its source, latency, access terms and monitoring requirements.

## Licence

I'm not granting a licence for the collaborative workshop materials at this stage. Linking to the public CHPC record does not transfer ownership or give permission to relicense other contributors' code or datasets.
