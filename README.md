# Wind Energy Monitoring and Forecasting

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

The event page names Phila Sibandze and Kgabo Humphrey Thamaga as speakers. The attached proposal names Phila Sibandze, Kgabo Humphrey Thamaga and Gbenga Afuye as lecturers. This repository credits the full listed author team without attributing identical speaking or coding roles to every person.

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
