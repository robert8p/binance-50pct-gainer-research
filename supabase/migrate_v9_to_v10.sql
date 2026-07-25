-- Binance V9 -> V10: neutral raw-data exporter for ChatGPT-led pattern discovery.
-- Additive only. All earlier scans, research jobs, files and audit history remain intact.

create table if not exists binance_chatgpt_export_jobs (
  id uuid primary key default gen_random_uuid(),
  scan_id uuid not null references binance_scan_jobs(id) on delete restrict,
  status text not null check (status in ('queued','running','completed','completed_with_warnings','failed')),
  protocol_version text not null default 'v10_neutral_chatgpt_research_export_1',
  controls_per_event integer not null default 5 check (controls_per_event = 5),
  prior_days integer not null default 10 check (prior_days = 10),
  discovery_pct integer not null default 60 check (discovery_pct = 60),
  validation_pct integer not null default 20 check (validation_pct = 20),
  include_baseline_bar boolean not null default true,
  reference_symbols jsonb not null default '["BTCUSDT","ETHUSDT","BNBUSDT"]'::jsonb,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  heartbeat_at timestamptz,
  events_total integer not null default 0,
  symbols_total integer not null default 0,
  symbols_processed integer not null default 0,
  controls_created integer not null default 0,
  samples_exported integer not null default 0,
  minute_rows_exported bigint not null default 0,
  failures integer not null default 0,
  result_json jsonb,
  error_message text
);

create table if not exists binance_chatgpt_export_files (
  id uuid primary key default gen_random_uuid(),
  chatgpt_export_job_id uuid not null references binance_chatgpt_export_jobs(id) on delete cascade,
  storage_path text not null,
  filename text not null,
  size_bytes bigint not null,
  sha256 text not null,
  content_type text not null,
  role text not null,
  split text check (split is null or split in ('discovery','validation','sealed_test')),
  created_at timestamptz not null default now(),
  unique (chatgpt_export_job_id, storage_path)
);

create table if not exists binance_chatgpt_export_issues (
  id bigint generated always as identity primary key,
  chatgpt_export_job_id uuid not null references binance_chatgpt_export_jobs(id) on delete cascade,
  symbol text,
  stage text not null,
  message text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_binance_chatgpt_export_jobs_status
  on binance_chatgpt_export_jobs(status, created_at);
create index if not exists idx_binance_chatgpt_export_files_job
  on binance_chatgpt_export_files(chatgpt_export_job_id, created_at);
create index if not exists idx_binance_chatgpt_export_issues_job
  on binance_chatgpt_export_issues(chatgpt_export_job_id, created_at);

alter table binance_chatgpt_export_jobs enable row level security;
alter table binance_chatgpt_export_files enable row level security;
alter table binance_chatgpt_export_issues enable row level security;

comment on table binance_chatgpt_export_jobs is
  'Neutral staged raw-data exports. The app selects no predictor or trading rule; ChatGPT performs discovery from the discovery package.';
