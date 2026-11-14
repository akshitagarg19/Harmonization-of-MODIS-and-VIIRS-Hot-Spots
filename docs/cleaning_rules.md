# Punjab Fire Calendar - Cleaning Rules

## Source
hotspots_punjab_clipped.parquet

## Confidence standardisation
- MODIS confidence below 30: low
- MODIS confidence 30 to 80 inclusive: nominal
- MODIS confidence above 80: high
- VIIRS low/l: low
- VIIRS nominal/n: nominal
- VIIRS high/h: high
- Unrecognised or missing values: unknown

Low-confidence detections are excluded.
Unknown-confidence detections are retained and labelled unknown.

## Brightness
- MODIS standard brightness uses the brightness field.
- VIIRS standard brightness uses bright_ti4.
- Original sensor-specific brightness fields are preserved.
- These measurements are not assumed to be directly equivalent.

## Time
FIRMS acquisition date and time are interpreted as UTC.
Both UTC and Asia/Kolkata timestamps are stored.
Missing or invalid times produce a null timestamp.
Day/night is standardised to Day, Night, or Unknown.

## Duplicates
Exact duplicates are removed within the same sensor.
Likely overlapping-pass duplicates are also suppressed within
the same sensor, acquisition date, rounded 0.01-degree
coordinate bin, and 30-minute time window.
The record with the highest FRP is retained.
Different sensors are never deduplicated against one another.

This approximate rule may occasionally merge nearby distinct
detections. It is a practical prototype rule.

## Grid
Each detection is assigned to a globally aligned 0.25-degree
latitude/longitude grid cell.

## Non-vegetation heat sources
No industrial-site or land-cover filtering is applied at this
stage. Brick kilns, industrial heat sources and other
non-vegetation thermal sources may remain in the dataset.
A land-cover dataset such as MODIS MCD12Q1 can support a
future filtering or classification stage.