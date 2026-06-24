# Milestone 6 Time-Series Diagnostics Validation

Generated at UTC: 2026-06-24T16:06:22.510238+00:00

## Input

- `data/processed/region_day_metrics.parquet` rows: 39525

## Outputs

- `data/processed/region_day_timeseries.parquet` rows: 39525
- `data/processed/region_timeseries_summary.parquet` rows: 25

## Coverage

- Date start: 2022-02-25
- Date end: 2026-06-24
- Regions covered: 25

## Columns Created

- `alert_minutes_7d_mean`
- `alert_minutes_14d_mean`
- `alert_minutes_30d_mean`
- `abi_7d_mean`
- `abi_14d_mean`
- `abi_30d_mean`
- `alert_minutes_14d_std`
- `alert_minutes_30d_std`
- `abi_14d_std`
- `abi_30d_std`

Summary diagnostics include period means, latest-vs-previous 30-day deltas, conservative change-point dates, volatility labels, trend labels, and statistical-shift labels.

## Rolling Null Counts

- `alert_minutes_7d_mean`: 0
- `alert_minutes_14d_mean`: 0
- `alert_minutes_30d_mean`: 0
- `abi_7d_mean`: 0
- `abi_14d_mean`: 0
- `abi_30d_mean`: 0
- `alert_minutes_14d_std`: 0
- `alert_minutes_30d_std`: 0
- `abi_14d_std`: 0
- `abi_30d_std`: 0

## Label Rules

- Volatility: low when daily alert-minute standard deviation is under 60 minutes, medium from 60 to under 180, high at 180 or above.
- Trend: stable when late-vs-early changes are small; worsening or improving when both alert minutes and ABI move in the same direction; mixed otherwise.
- Statistical shift flag: no clear statistical shift when no material change point is detected, possible statistical shift for one material change point, repeated statistical shifts for multiple material points.

## Example High-Volatility Regions

- Kharkivska oblast: high, mean=816.4, std=581.6
- Sumska oblast: high, mean=523.8, std=464.5
- Donetska oblast: high, mean=746.7, std=452.6
- Dnipropetrovska oblast: high, mean=1066.5, std=425.1
- Chernihivska oblast: high, mean=349.0, std=391.2
- Zaporizka oblast: high, mean=436.1, std=324.4
- Poltavska oblast: high, mean=291.7, std=236.6
- Kyivska oblast: high, mean=182.8, std=207.4
- Khersonska oblast: high, mean=207.7, std=194.1

## Example Statistical Shift Flags

- Kharkivska oblast: possible statistical shift, mean=816.4, std=581.6
- Sumska oblast: repeated statistical shifts, mean=523.8, std=464.5
- Donetska oblast: repeated statistical shifts, mean=746.7, std=452.6
- Dnipropetrovska oblast: repeated statistical shifts, mean=1066.5, std=425.1
- Chernihivska oblast: repeated statistical shifts, mean=349.0, std=391.2
- Zaporizka oblast: possible statistical shift, mean=436.1, std=324.4
- Poltavska oblast: repeated statistical shifts, mean=291.7, std=236.6
- Kyivska oblast: repeated statistical shifts, mean=182.8, std=207.4
- Khersonska oblast: repeated statistical shifts, mean=207.7, std=194.1
- Cherkaska oblast: repeated statistical shifts, mean=174.6, std=174.4

## Validation

- Missing time-series columns: []
- Missing summary columns: []
- Row count matches input: True
- Time-series has infinite values: False
- Summary has infinite values: False
- Label checks: {'volatility_label': True, 'trend_label': True, 'regime_shift_label': True}
- Validation passed: True

## Safety Note

These diagnostics describe historical civilian alert burden, instability, and statistical changes in past time series. They are not forecasts and are not designed for real-time decision-making.

## Known Limitations

- Descriptive only.
- No causal claims.
- Not for forecasting or real-time decisions.
- Change points identify statistical shifts, not reasons for shifts.
- Region-level aggregation may hide within-region variation.
