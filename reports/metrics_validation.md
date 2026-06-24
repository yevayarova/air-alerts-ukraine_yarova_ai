# Milestone 4 Metrics Validation

Generated at UTC: 2026-06-24T15:25:19.059093+00:00

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

- Alert Burden Index: 0.50 * normalized(alert_minutes_total) + 0.20 * normalized(merged_alert_episode_count) + 0.20 * normalized(max_alert_duration) + 0.10 * normalized(1 - longest_alert_free_window_minutes / 1440).
- ABI uses `merged_alert_episode_count`, not raw source record count, so overlapping administrative records do not inflate the count component.
- Min-max normalization is computed over the observed region-day table at build time. A future refresh can rescale historical ABI values if new minima or maxima enter the dataset.
- Sleep Disruption Index: alert_minutes_night / 540.
- Work/Study Disruption Index: alert_minutes_workday / 540.
- Alert-free recovery: alert_free_window_share = longest_alert_free_window_minutes / 1440; low_recovery_day is true when the longest alert-free window is less than 8 hours.
- Regional inequality: daily Gini values across regions for alert minutes and ABI; top-bottom ratio compares mean top 20% alert minutes with mean bottom 20%.

## Metric Range Checks

| Metric | Min | Max | Expected range | Passed |
| --- | ---: | ---: | --- | --- |
| alert_burden_index | 0.0000 | 0.8125 | 0 to 1 | True |
| sleep_disruption_index | 0.0000 | 1.0000 | 0 to 1 | True |
| workday_disruption_index | 0.0000 | 1.0000 | 0 to 1 | True |
| alert_free_window_share | 0.0000 | 1.0000 | 0 to 1 | True |
| gini_alert_minutes_total | 0.1366 | 0.9358 | 0 to 1 | True |
| gini_alert_burden_index | 0.1104 | 0.9298 | 0 to 1 | True |

Validation passed: True

## Category Counts

### Alert Burden Category

- low: 34038
- medium: 4854
- high: 633

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

- Dnipropetrovska oblast: 0.4960
- Kharkivska oblast: 0.4877
- Donetska oblast: 0.4006
- Sumska oblast: 0.2958
- Zaporizka oblast: 0.2875
- Chernihivska oblast: 0.2031
- Poltavska oblast: 0.2024
- Mykolaivska oblast: 0.1628
- Khersonska oblast: 0.1570
- Kirovohradska oblast: 0.1456

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

These metrics measure historical civilian alert burden and disruption. They are descriptive only and are not designed for forecasting or real-time decision-making.

## Known Limitations

- Metric weights are analytic design choices and should be interpreted as descriptive indicators.
- ABI values are refresh-relative because min-max normalization is rebuilt from the current processed dataset.
- Sleep/work windows are default assumptions and may not match every person or institution.
- Sleep disruption is based on calendar-day Kyiv-local night hours, not individual sleep episodes.
- Region-level aggregation may hide within-region variation.
- Metrics are descriptive, not causal.
- High burden should not be read as a future danger signal.
