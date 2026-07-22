-- Binance 3-hour surge research v4.0 ten-day-context migration.
-- Additive only: existing scans, events, controls and files are preserved.

alter table binance_scan_jobs add column if not exists window_start_date date;
alter table binance_scan_jobs add column if not exists window_end_date_exclusive date;

create table if not exists binance_context_jobs (
  id uuid primary key default gen_random_uuid(),
  matched_control_job_id uuid not null references binance_matched_control_jobs(id) on delete cascade,
  status text not null check (status in ('queued','running','completed','completed_with_warnings','failed')),
  research_mode text not null default 'exploratory_reuse' check (research_mode in ('exploratory_reuse','fresh_staged')),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  heartbeat_at timestamptz,
  prior_days integer not null default 10 check (prior_days = 10),
  horizons_minutes jsonb not null default '[15,30,60,120]'::jsonb,
  windows_minutes jsonb not null default '[15,30,60,120,180,360,720,1440,2880,4320,7200,10080,14400]'::jsonb,
  min_entry_notional numeric not null default 500,
  samples_total integer not null default 0,
  samples_processed integer not null default 0,
  events_total integer not null default 0,
  controls_total integer not null default 0,
  feature_rows integer not null default 0,
  failures integer not null default 0,
  result_json jsonb,
  error_message text
);

create table if not exists binance_context_files (
  id uuid primary key default gen_random_uuid(),
  context_job_id uuid not null references binance_context_jobs(id) on delete cascade,
  split text check (split in ('discovery','validation','sealed_test')),
  storage_path text not null,
  filename text not null,
  size_bytes bigint not null,
  sha256 text not null,
  content_type text not null,
  role text not null,
  created_at timestamptz not null default now(),
  unique (context_job_id, storage_path)
);

create table if not exists binance_context_issues (
  id bigint generated always as identity primary key,
  context_job_id uuid not null references binance_context_jobs(id) on delete cascade,
  symbol text,
  stage text not null,
  message text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_binance_context_jobs_status
  on binance_context_jobs(status, created_at);
create index if not exists idx_binance_context_files_job
  on binance_context_files(context_job_id, created_at);
create index if not exists idx_binance_scan_custom_window
  on binance_scan_jobs(window_start_date, window_end_date_exclusive);

alter table binance_context_jobs enable row level security;
alter table binance_context_files enable row level security;
alter table binance_context_issues enable row level security;

-- No anonymous policies are created. The app uses the server-side secret/service-role key only.
