# Verification & Test Documentation

Tests for **TerraFlow (Smart Irrigation Advisor)**. Two scripts, both run from the project root and needing no network:

```bash
python run_tests.py                  # 7 engine and fallback-text tests
python tests/test_integration.py     # weather, validation, website contract and Nugen layer (Nugen mocked)
```

Both read `crops.csv` and `soils.csv`, so they must be present. The engine tests compute their soil-moisture inputs from those files, so they stay valid when the data changes.

---

## 1. Engine tests (`run_tests.py`)

| ID | Scenario | Expected |
| :---: | :--- | :--- |
| TC-01 | Soil at wilting point, dry week | Irrigate |
| TC-02 | 18 mm rain (78% probability) tomorrow, soil past the stress threshold but not dead dry | Hold irrigation |
| TC-03 | Soil at field capacity | No irrigation |
| TC-04 | Rainy week, soil full | Savings against the fixed schedule are positive |
| TC-05 | Weather API offline | Built-in sample weather, 7 days |
| TC-06 | No AI key | Valid English, Hindi and Marathi fallback text |
| TC-07 | Known gross mm, acres, pump L/h | Litres and pump minutes match the formula |

Rationale (FAO-56): irrigate when root-zone depletion reaches the readily available water, `RAW = p x TAW`; hold when significant rain is forecast within 24 to 48 hours; litres = mm x acres x 4046.86.

---

## 2. Integration tests (`tests/test_integration.py`)

- **Validation:** unknown crop, soil or method, out-of-range area, latitude or sensor value, and a bad sowing date are rejected with the field name (no silent default).
- **Website contract:** the response carries every field `frontend/index.html` reads (weather, stage, moisture, charts, methods, confidence).
- **Arithmetic:** net, gross, litres and pump minutes reconcile; acre and sqm inputs agree.
- **Farmer inputs:** growth stage from sowing date, soil-feel test, crop stress, water availability, mulch.
- **Weather:** live, then cached, then sample fallback; a missing forecast value is rejected, never turned into 0.
- **Confidence:** non-live weather gives Low confidence.
- **Nugen layer (mocked):** answers are used and labelled; answers with invented numbers are discarded; API errors and a missing or placeholder key give labelled built-in text; farmer questions are treated as data; the status route shows the host and never the key.

---

## 3. Not covered by the scripts

- The real Nugen API (needs your key): check with `/api/ai/status?ping=true`.
- The FastAPI routes and the website in a browser: start the server and click through.
- Hindi and Marathi wording: needs a fluent speaker's review.
