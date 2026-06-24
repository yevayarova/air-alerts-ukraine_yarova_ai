# Milestone 3 Feature Validation

Generated at UTC: 2026-06-24T14:49:30.279142+00:00

## Input

- Input file path: `data/processed/alerts_clean.parquet`
- Input row count: 160576
- Coverage start: 2022-02-25T16:36:22+00:00
- Coverage end: 2026-06-24T00:55:27+00:00
- Number of regions: 25
- Timestamps timezone-aware: True

## Regions

- Cherkaska oblast
- Chernihivska oblast
- Chernivetska oblast
- Dnipropetrovska oblast
- Donetska oblast
- Ivano-Frankivska oblast
- Kharkivska oblast
- Khersonska oblast
- Khmelnytska oblast
- Kirovohradska oblast
- Kyiv City
- Kyivska oblast
- Luhanska oblast
- Lvivska oblast
- Mykolaivska oblast
- Odeska oblast
- Poltavska oblast
- Rivnenska oblast
- Sumska oblast
- Ternopilska oblast
- Vinnytska oblast
- Volynska oblast
- Zakarpatska oblast
- Zaporizka oblast
- Zhytomyrska oblast

## Outputs

- `data/processed/region_hour_features.parquet`: 948600 rows
- `data/processed/region_day_features.parquet`: 39525 rows
- `data/processed/national_day_features.parquet`: 1581 rows

## Metric Range Checks

| Metric | Min | Max | Expected range | Passed |
| --- | ---: | ---: | --- | --- |
| alert_minutes_in_hour | 0.0000 | 60.0000 | 0 to 60 | True |
| alert_minutes_total | 0.0000 | 1440.0000 | 0 to 1440 | True |
| alert_minutes_night | 0.0000 | 540.0000 | 0 to 540 | True |
| alert_minutes_workday | 0.0000 | 540.0000 | 0 to 540 | True |
| share_day_under_alert | 0.0000 | 1.0000 | 0 to 1 | True |
| national_alert_burden_index | 0.0168 | 1.0000 | 0 to 1 | True |

Validation passed: True

## Data Quality Notes

- Missing ended_at_utc values: 0
- Zero or negative durations: 0
- Duplicate alert_id values: 0

## Safety Note

These features measure historical civilian alert burden and disruption. They do not predict attacks, targets, routes, or military activity.

## Known Limitations

- Sleep/work windows are default assumptions and may not match every person/institution.
- Region-level aggregation may hide within-region variation.
- Feature tables are descriptive, not causal.
