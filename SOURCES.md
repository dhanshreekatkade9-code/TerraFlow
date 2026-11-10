# Agronomic Sources & Methodology (FAO-56)

Data sources, formulas, reference values and assumptions used by **TerraFlow (Smart Irrigation Advisor)**. Values marked *team assumption* are not from a published standard; they are design choices and are labelled as such in the app.

---

## 1. Methodology: FAO-56 Water Balance

Daily crop water need and soil moisture depletion follow **FAO Irrigation and Drainage Paper No. 56: *Crop Evapotranspiration - Guidelines for computing crop water requirements*** (Allen, Pereira, Raes & Smith, 1998).

### 1.1 Crop Evapotranspiration ($ET_c$)
$$ET_c = K_c \times ET_0$$
- **$ET_0$**: daily reference evapotranspiration from Open-Meteo (`et0_fao_evapotranspiration`, FAO-56 Penman-Monteith computed from weather model output, not a field measurement).
- **$K_c$**: single crop coefficient by crop and growth stage (`initial`, `development`, `mid_season`, `late_season`).

### 1.2 Total Available Water ($TAW$)
$$TAW = 1000 \times (\theta_{FC} - \theta_{WP}) \times Z_r$$
(FAO-56 Eq. 82) $\theta_{FC}$ field capacity, $\theta_{WP}$ wilting point ($m^3/m^3$), $Z_r$ effective root depth (m), $TAW$ in mm.

### 1.3 Readily Available Water ($RAW$)
$$RAW = p \times TAW$$
(FAO-56 Eq. 83) Irrigation is recommended when root-zone depletion $D_r \ge RAW$.

### 1.4 Daily depletion balance
$D_{r,end} = D_{r,start} - P_{eff} - I + ET_c$, limited to the range 0 to $TAW$ (FAO-56 Box 8 / Eq. 85, without capillary rise or runoff terms).

### 1.5 Effective rainfall ($P_{eff}$)
USDA Soil Conservation Service method: $0.6P - 1$ for $P \le 25$ mm/day, $0.8P - 5$ above that (never below 0). Counted only when rain probability is 50% or more *(team assumption on the probability cut-off)*.

---

## 2. Crop Parameters (`crops.csv`, 10 crops x 4 stages)

Reference: **FAO-56 Table 12** (single $K_c$), **Table 22** (rooting depth $Z_r$ and depletion fraction $p$), adapted for Indian crops and stage lengths using ICAR / state agricultural university guidance. Stage lengths are typical values; actual lengths vary by variety and sowing season.

Values are listed as Initial / Development / Mid-season / Late-season.

| Crop | $K_c$ | Root depth $Z_r$ (m) | Depletion $p$ | Stage days |
| :--- | :--- | :--- | :--- | :--- |
| Wheat | 0.40 / 0.75 / 1.15 / 0.40 | 0.35 / 0.65 / 1.00 / 1.10 | 0.55 / 0.55 / 0.55 / 0.65 | 20 / 30 / 40 / 30 |
| Rice (Paddy) | 1.05 / 1.10 / 1.20 / 0.90 | 0.30 / 0.50 / 0.60 / 0.60 | 0.20 / 0.20 / 0.20 / 0.30 | 20 / 30 / 40 / 30 |
| Cotton | 0.40 / 0.75 / 1.20 / 0.65 | 0.40 / 0.90 / 1.40 / 1.50 | 0.65 / 0.65 / 0.65 / 0.70 | 30 / 50 / 60 / 40 |
| Maize | 0.40 / 0.80 / 1.20 / 0.60 | 0.30 / 0.70 / 1.00 / 1.20 | 0.55 / 0.55 / 0.55 / 0.60 | 20 / 35 / 40 / 30 |
| Sugarcane | 0.45 / 0.85 / 1.25 / 0.75 | 0.40 / 0.80 / 1.20 / 1.50 | 0.65 / 0.65 / 0.65 / 0.75 | 60 / 90 / 150 / 60 |
| Soybean | 0.40 / 0.70 / 1.15 / 0.50 | 0.30 / 0.60 / 0.90 / 1.00 | 0.50 / 0.50 / 0.50 / 0.60 | 20 / 30 / 40 / 25 |
| Chickpea (Gram) | 0.40 / 0.70 / 1.05 / 0.35 | 0.25 / 0.50 / 0.80 / 0.90 | 0.50 / 0.50 / 0.50 / 0.60 | 20 / 30 / 40 / 25 |
| Tomato | 0.45 / 0.75 / 1.15 / 0.80 | 0.25 / 0.50 / 0.80 / 0.90 | 0.40 / 0.40 / 0.40 / 0.50 | 25 / 35 / 45 / 30 |
| Onion | 0.50 / 0.75 / 1.05 / 0.75 | 0.20 / 0.35 / 0.45 / 0.50 | 0.35 / 0.35 / 0.35 / 0.45 | 20 / 35 / 45 / 25 |
| Groundnut | 0.40 / 0.75 / 1.15 / 0.60 | 0.30 / 0.60 / 0.85 / 0.90 | 0.50 / 0.50 / 0.50 / 0.60 | 25 / 35 / 45 / 25 |

The `critical_stage` column in `crops.csv` marks stages that are especially sensitive to water stress; it is informational and does not change the calculation.

---

## 3. Soil Characteristics (`soils.csv`, 8 soils)

Reference: **FAO-56 Table 19** (typical soil water characteristics by texture) and NBSS&LUP / ICAR descriptions of Indian soil groups. These are typical class values, not measurements of any particular field.

| Soil | Field capacity (%) | Wilting point (%) | Available water (mm/m) | Infiltration (mm/h) |
| :--- | :---: | :---: | :---: | :---: |
| Loam | 31 | 15 | 160 | 15 |
| Black cotton (Vertisol) | 40 | 22 | 180 | 4 |
| Clay loam | 36 | 18 | 180 | 8 |
| Sandy loam | 22 | 10 | 120 | 25 |
| Sand | 14 | 6 | 80 | 45 |
| Silt loam | 33 | 13 | 200 | 12 |
| Red sandy loam (Alfisol) | 24 | 11 | 130 | 20 |
| Alluvial | 32 | 14 | 180 | 14 |

The engine uses field capacity and wilting point only; available water (FC - WP) is shown for reference. Infiltration rate and bulk density are stored but not used in the current calculation.

---

## 4. Irrigation Application Efficiency

Reference: FAO Irrigation Water Management Training Manual No. 4 (field application efficiencies).
- Drip: 90% ($\eta = 0.90$)
- Sprinkler: 75% ($\eta = 0.75$)
- Surface / flood: 60% ($\eta = 0.60$)

Gross irrigation (mm) = net requirement / $\eta$. Litres = gross mm x acres x 4046.86 (1 mm over 1 acre).

---

## 5. Weather and AI services

| Service | Use | Note |
| :--- | :--- | :--- |
| [Open-Meteo Forecast API](https://open-meteo.com/) | 7-day rain, rain probability, temperature, $ET_0$; current temperature, humidity, wind | Weather-model output, not ground-station readings. Data licensed CC BY 4.0; attribution is shown in the app footer. |
| Nugen AI (chat completions) | Writes the explanations, chat answers and WhatsApp text from numbers the engine already calculated | Answers containing numbers the engine did not produce are discarded. |

When live weather fails the app shows the last saved forecast (labelled), then built-in demo data (labelled DEMO).

---

## 6. Team assumptions (not from a published standard)

| Item | Value | Where |
| :--- | :--- | :--- |
| Hold irrigation for forecast rain | 10 mm or more at 60% probability or more within 24-48 h, unless soil is nearly dry (depletion over 90% of TAW) | `engine.py` |
| Default soil moisture when no input | 60% of RAW already depleted | `engine.py` |
| Soil-feel test moisture | about 16 / 26 / 34 / 45% | `service.py` |
| Crop stress multipliers | 1.10 (mild wilt), 1.20 (heat roll), 0.70 (yellowing) | `service.py` |
| Water availability factor | 1.0 / 0.75 / 0.5 | `service.py` |
| Mulch cut to $ET_0$ | 15% organic, 25% plastic | `service.py` |
| Savings baseline | fixed 25 mm every 3 days (illustrative) | `engine.py` |
| Pump energy | 0.746 kW per HP; diesel 0.85 L/h; grid emissions 0.82 kg CO2/kWh | `engine.py` |
| Confidence score | engine heuristic from rain-forecast certainty; capped at 50 when weather is not live; not statistically calibrated | `engine.py`, `service.py` |
| $ET_0$ fallback | Hargreaves-Samani (FAO-56 Eq. 52) only when a day has no $ET_0$ value | `engine.py` |

---

## 7. Limitations

- Soil moisture comes from the farmer (sensor or feel test) or a model estimate, not from a satellite.
- Forecast rain may not arrive; advice should be re-run daily.
- Soil and crop values are typical class values; local calibration (soil test, KVK advice) will differ.
- Hindi and Marathi text needs review by a fluent speaker or agronomist before public use.