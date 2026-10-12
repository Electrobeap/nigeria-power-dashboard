-- Run only on an operator-approved PostgreSQL read-only snapshot.
-- Bind :start_utc and :end_utc explicitly in the database client.
-- Export each result as CSV, record UTF-8 encoding and SHA-256, and keep rights evidence.
-- This file is documentation; it is never run by Flask or the scheduler.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '30000';

SELECT id AS snapshot_id, reading_timestamp, captured_at, as_at_time,
       total_generation_mw, reporting_gencos, source, source_url, daily_json,
       disco_as_at, total_load_allocation_mw
FROM grid_snapshots
WHERE reading_timestamp >= :start_utc AND reading_timestamp < :end_utc
ORDER BY reading_timestamp, id;

SELECT g.snapshot_id, g.plant, g.generation_mw, s.reading_timestamp, s.captured_at
FROM genco_data AS g JOIN grid_snapshots AS s ON s.id = g.snapshot_id
WHERE s.reading_timestamp >= :start_utc AND s.reading_timestamp < :end_utc
ORDER BY s.reading_timestamp, g.plant;

SELECT d.snapshot_id, d.company, d.load_allocation_mw, s.disco_as_at,
       s.reading_timestamp, s.captured_at, s.total_load_allocation_mw
FROM disco_data AS d JOIN grid_snapshots AS s ON s.id = d.snapshot_id
WHERE s.reading_timestamp >= :start_utc AND s.reading_timestamp < :end_utc
ORDER BY s.reading_timestamp, d.company;

ROLLBACK;
-- Source timestamp/fallback verification additionally requires approved inspection
-- of matching raw_payload_json and collection logs. Do not publish raw payloads
-- or private operational logs without rights and disclosure review.
