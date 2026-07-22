-- Binance 3-hour 50% surge research v4 -> v5
-- Additive migration: preserves all existing scans, matched controls and context outputs.

create table if not exists binance_baseline_context_jobs (
  id uuid primary key default gen_random_uuid(),
  matched_control_job_id uuid not null references binance_matched_control_jobs(id) on delete cascade,
  status text not null check (status in ('queued','running','completed','completed_with_warnings','failed')),
  research_mode text not null default 'exploratory_reuse' check (research_mode in ('exploratory_reuse','fresh_staged')),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  heartbeat_at timestamptz,
  prior_days integer not null default 10 check (prior_days = 10),
  snapshot_offsets_minutes jsonb not null default '[14400,10080,7200,4320,2880,1440,720,360,180,60,0]'::jsonb,
  continuation_horizons_minutes jsonb not null default '[15]'::jsonb,
  min_entry_notional numeric not null default 500,
  samples_total integer not null default 0,
  samples_processed integer not null default 0,
  events_total integer not null default 0,
  controls_total integer not null default 0,
  feature_rows integer not null default 0,
  continuation_rows integer not null default 0,
  failures integer not null default 0,
  result_json jsonb,
  error_message text
);

create table if not exists binance_baseline_context_files (
  id uuid primary key default gen_random_uuid(),
  baseline_context_job_id uuid not null references binance_baseline_context_jobs(id) on delete cascade,
  split text check (split in ('discovery','validation','sealed_test')),
  storage_path text not null,
  filename text not null,
  size_bytes bigint not null,
  sha256 text not null,
  content_type text not null,
  role text not null,
  created_at timestamptz not null default now(),
  unique (baseline_context_job_id, storage_path)
);

create table if not exists binance_baseline_context_issues (
  id bigint generated always as identity primary key,
  baseline_context_job_id uuid not null references binance_baseline_context_jobs(id) on delete cascade,
  symbol text,
  stage text not null,
  message text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_binance_baseline_context_jobs_status
  on binance_baseline_context_jobs(status, created_at);
create index if not exists idx_binance_baseline_context_files_job
  on binance_baseline_context_files(baseline_context_job_id, created_at);
create index if not exists idx_binance_baseline_context_issues_job
  on binance_baseline_context_issues(baseline_context_job_id, created_at);

alter table binance_baseline_context_jobs enable row level security;
alter table binance_baseline_context_files enable row level security;
alter table binance_baseline_context_issues enable row level security;

-- No anonymous policies are created. The app uses the server-side secret/service-role key only.
