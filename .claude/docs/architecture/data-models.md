# Aries Data Models

## Dataset

A provenance record for one immutable-by-contract source object. `(source, external_id)` and `object_key` are unique. At least one of `satellite_norad_id` or `aoi_id` is required. `size_bytes` and `sha256` describe the actual MinIO bytes.

## Observation

A normalized SatNOGS observation linked one-to-one to its Dataset with cascade deletion. It retains satellite, station, timestamp, frequency, signal quality, artifact URLs, decoded data, and ingestion time.

## Pass

Reserved for historical pass persistence. Current pass results are calculated on demand from Celestrak TLE data and are not written.

## Object Layout

SatNOGS raw objects use `raw/satnogs/{norad_id}/{observation_id}.json`. `processed` and `results` buckets exist for later workload and benchmark milestones but remain empty in Milestone 3.
