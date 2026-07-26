-- Binance V10.2 -> V12 exact-entry continuous validation.
-- Additive only: previous scans, research exports and files remain untouched.

create table if not exists binance_entry_validation_jobs (
  id uuid primary key default gen_random_uuid(),
  status text not null check (status in ('queued','running','completed','completed_with_warnings','failed','cancelled')),
  protocol_version text not null default 'v12_exact_entry_validation_1',
  window_start_date date not null default date '2025-01-01',
  window_end_date_exclusive date not null default date '2025-07-01',
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  heartbeat_at timestamptz,
  symbols_total integer not null default 0,
  symbols_processed integer not null default 0,
  candidate_edges integer not null default 0,
  selected_signals integer not null default 0,
  executions_processed integer not null default 0,
  failures integer not null default 0,
  result_json jsonb,
  error_message text,
  check (protocol_version = 'v12_exact_entry_validation_1'),
  check (window_start_date = date '2025-01-01'),
  check (window_end_date_exclusive = date '2025-07-01')
);

create table if not exists binance_entry_validation_files (
  id uuid primary key default gen_random_uuid(),
  entry_validation_job_id uuid not null references binance_entry_validation_jobs(id) on delete cascade,
  storage_path text not null,
  filename text not null,
  size_bytes bigint not null,
  sha256 text not null,
  content_type text not null,
  role text not null,
  created_at timestamptz not null default now(),
  unique (entry_validation_job_id, storage_path)
);

create table if not exists binance_entry_validation_issues (
  id bigint generated always as identity primary key,
  entry_validation_job_id uuid not null references binance_entry_validation_jobs(id) on delete cascade,
  symbol text,
  stage text not null,
  message text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_binance_entry_validation_jobs_status
  on binance_entry_validation_jobs(status, created_at);
create index if not exists idx_binance_entry_validation_files_job
  on binance_entry_validation_files(entry_validation_job_id, created_at);
create index if not exists idx_binance_entry_validation_issues_job
  on binance_entry_validation_issues(entry_validation_job_id, created_at);

alter table binance_entry_validation_jobs enable row level security;
alter table binance_entry_validation_files enable row level security;
alter table binance_entry_validation_issues enable row level security;

comment on table binance_entry_validation_jobs is
  'V12 untouched 2025 validation of frozen E1 and E2 continuous exact-entry triggers. Sealed July-October 2025 data are not accessed.';
