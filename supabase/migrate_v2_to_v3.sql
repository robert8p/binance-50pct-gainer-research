-- Binance 3-hour surge research v3.0 matched-control migration.
-- Additive only: existing scans, events and research files are preserved.

create table if not exists binance_matched_control_jobs (
  id uuid primary key default gen_random_uuid(),
  scan_id uuid not null references binance_scan_jobs(id) on delete cascade,
  status text not null check (status in ('queued','running','completed','completed_with_warnings','failed')),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  heartbeat_at timestamptz,
  controls_per_event integer not null default 5 check (controls_per_event between 1 and 10),
  prior_days integer not null default 10 check (prior_days between 1 and 30),
  horizons_minutes jsonb not null default '[15,30,60,120]'::jsonb,
  contamination_before_minutes integer not null default 120,
  contamination_after_minutes integer not null default 180,
  min_entry_notional numeric not null default 500,
  discovery_pct integer not null default 70,
  validation_pct integer not null default 15,
  events_total integer not null default 0,
  events_processed integer not null default 0,
  controls_target integer not null default 0,
  controls_created integer not null default 0,
  feature_rows integer not null default 0,
  failures integer not null default 0,
  result_json jsonb,
  error_message text
);

create table if not exists binance_control_matches (
  matched_control_job_id uuid not null references binance_matched_control_jobs(id) on delete cascade,
  event_id uuid not null references binance_gainer_events(id) on delete cascade,
  control_id uuid not null,
  symbol text not null,
  split text not null check (split in ('discovery','validation','sealed_test')),
  event_anchor_time timestamptz not null,
  control_anchor_time timestamptz not null,
  control_rank integer not null,
  clock_offset_minutes integer not null,
  calendar_distance_days integer not null,
  weekday_match boolean not null,
  match_tier text not null,
  prior_global_reuse_count integer not null default 0,
  minimum_5m_quote_volume numeric,
  prior_history_observed_fraction numeric,
  quality_status text not null,
  created_at timestamptz not null default now(),
  primary key (matched_control_job_id, control_id),
  unique (matched_control_job_id, event_id, control_rank)
);

create table if not exists binance_matched_control_files (
  id uuid primary key default gen_random_uuid(),
  matched_control_job_id uuid not null references binance_matched_control_jobs(id) on delete cascade,
  split text check (split in ('discovery','validation','sealed_test')),
  storage_path text not null,
  filename text not null,
  size_bytes bigint not null,
  sha256 text not null,
  content_type text not null,
  role text not null,
  created_at timestamptz not null default now(),
  unique (matched_control_job_id, storage_path)
);

create table if not exists binance_matched_control_issues (
  id bigint generated always as identity primary key,
  matched_control_job_id uuid not null references binance_matched_control_jobs(id) on delete cascade,
  event_id uuid references binance_gainer_events(id) on delete cascade,
  stage text not null,
  message text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_binance_matched_jobs_status
  on binance_matched_control_jobs(status, created_at);
create index if not exists idx_binance_control_matches_event
  on binance_control_matches(matched_control_job_id, event_id, control_rank);
create index if not exists idx_binance_control_matches_symbol_time
  on binance_control_matches(matched_control_job_id, symbol, control_anchor_time);
create index if not exists idx_binance_matched_files_job
  on binance_matched_control_files(matched_control_job_id, created_at);

alter table binance_matched_control_jobs enable row level security;
alter table binance_control_matches enable row level security;
alter table binance_matched_control_files enable row level security;
alter table binance_matched_control_issues enable row level security;

-- No anonymous policies are created. The app uses the server-side secret/service-role key only.
