# Third-party notices

## TracingInsights (car telemetry)

The telemetry files in `telemetry/` can be downloaded from the data repositories of
[TracingInsights](https://tracinginsights.com/) (for example
[TracingInsights/2026](https://github.com/TracingInsights/2026)), which are licensed
under the **Apache License, Version 2.0**. The licence text is in
[licenses/TracingInsights-Apache-2.0.txt](licenses/TracingInsights-Apache-2.0.txt), copied
from https://github.com/TracingInsights/2026/blob/main/LICENSE.

- **What it is:** telemetry derived from the Formula 1 live timing feed and processed with FastF1.
- **Changes made here** (Apache-2.0, section 4b): the per-lap JSON files are combined into
  one Parquet file per driver per session; times are converted to milliseconds since the
  start of the lap; DRS is stored as 0 or 1; columns are cast to compact types; and the
  columns TracingInsights computes itself (`acc_x`, `acc_y`, `acc_z`, `rel_distance`,
  `DriverAhead`, `DistanceToDriverAhead`) are left out.
- **Affiliation:** TracingInsights states that it is not affiliated with Formula 1, the FIA
  or any F1 team, and that all trademarks belong to their respective owners.
- **Attribution:** TracingInsights asks for credit but does not require it. These files
  are credited in `TelemetryIndex.Source` and in the README.

If you redistribute telemetry files that came from TracingInsights, keep this notice and
the licence text with them.

## FastF1 (optional telemetry source)

Telemetry that `Source = 'FastF1'` marks was loaded with
[FastF1](https://github.com/theOehrly/Fast-F1) (MIT licence) from the Formula 1 live timing
service, using the F1 TV account of whoever ran the scraper. FastF1 is used as a library
and is not redistributed in this repository. The data belongs to Formula 1; read the F1 TV
terms of use before sharing files obtained that way.
