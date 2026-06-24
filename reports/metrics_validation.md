# Milestone 4 Metrics Validation

Generated at UTC: 2026-06-24T14:59:35.132153+00:00

## Inputs

- `data/processed/region_day_features.parquet`: 39525 rows after metric build
- `data/processed/national_day_features.parquet`: 1581 national-day rows summarized

## Outputs

- `data/processed/region_day_metrics.parquet`: 39525 rows
- `data/processed/region_summary_metrics.parquet`: 25 rows
- `data/processed/national_summary_metrics.parquet`: 1 rows

## Coverage

- Date start: 2022-02-25
- Date end: 2026-06-24
- Regions: 25

## Metric Formulas

- Alert Burden Index: 0.50 * normalized(alert_minutes_total) + 0.20 * normalized(alert_count) + 0.20 * normalized(max_alert_duration) + 0.10 * normalized(1 - longest_alert_free_window_minutes / 1440).
- Sleep Disruption Index: alert_minutes_night / 540.
- Work/Study Disruption Index: alert_minutes_workday / 540.
- Alert-free recovery: alert_free_window_share = longest_alert_free_window_minutes / 1440; low_recovery_day is true when the longest alert-free window is less than 8 hours.
- Regional inequality: daily Gini values across regions for alert minutes and ABI; top-bottom ratio compares mean top 20% alert minutes with mean bottom 20%.

## Metric Range Checks

| Metric | Min | Max | Expected range | Passed |
| --- | ---: | ---: | --- | --- |
| alert_burden_index | 0.0000 | 0.9763 | 0 to 1 | True |
| sleep_disruption_index | 0.0000 | 1.0000 | 0 to 1 | True |
| workday_disruption_index | 0.0000 | 1.0000 | 0 to 1 | True |
| alert_free_window_share | 0.0000 | 1.0000 | 0 to 1 | True |
| gini_alert_minutes_total | 0.1366 | 0.9358 | 0 to 1 | True |
| gini_alert_burden_index | 0.1019 | 0.9301 | 0 to 1 | True |

Validation passed: True

## Category Counts

### Alert Burden Category

- low: 35080
- medium: 3424
- high: 1021

### Sleep Disruption Category

- low: 30649
- medium: 4151
- high: 4725

### Workday Disruption Category

- low: 35318
- medium: 1817
- high: 2390

## Top Regions

### Mean Alert Burden Index

- Dnipropetrovska oblast: 0.4965
- Kharkivska oblast: 0.4728
- Donetska oblast: 0.3614
- Sumska oblast: 0.2620
- Zaporizka oblast: 0.2413
- Chernihivska oblast: 0.1807
- Poltavska oblast: 0.1671
- Mykolaivska oblast: 0.1323
- Khersonska oblast: 0.1257
- Kirovohradska oblast: 0.1179

### Mean Sleep Disruption Index

- Dnipropetrovska oblast: 0.8904
- Kharkivska oblast: 0.5713
- Donetska oblast: 0.5129
- Sumska oblast: 0.4032
- Zaporizka oblast: 0.3415
- Chernihivska oblast: 0.2981
- Poltavska oblast: 0.2873
- Mykolaivska oblast: 0.2156
- Kyivska oblast: 0.2001
- Kirovohradska oblast: 0.1982

### Mean Workday Disruption Index

- Dnipropetrovska oblast: 0.4643
- Donetska oblast: 0.4248
- Kharkivska oblast: 0.4162
- Sumska oblast: 0.2667
- Zaporizka oblast: 0.2205
- Chernihivska oblast: 0.1469
- Poltavska oblast: 0.1017
- Khersonska oblast: 0.0922
- Mykolaivska oblast: 0.0813
- Kirovohradska oblast: 0.0659

## Safety Note

These metrics measure historical civilian alert burden and disruption. They do not predict attacks, targets, routes, or military activity.

## Known Limitations

- Metric weights are analytic design choices and should be interpreted as descriptive indicators.
- Sleep/work windows are default assumptions and may not match every person or institution.
- Region-level aggregation may hide within-region variation.
- Metrics are descriptive, not causal.
- High burden does not mean higher attack probability.
