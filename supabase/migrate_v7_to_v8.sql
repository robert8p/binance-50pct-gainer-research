-- Binance eight-hour 50% surge research v7 -> v8
-- Corrects fresh-confirmation controls by selecting non-event baselines with
-- the same 480-minute rolling-minimum algorithm used for genuine events.
-- Existing scans, research packages, confirmation rows and backtests remain intact.

alter table binance_confirmation_jobs
  alter column baseline_context_job_id drop not null;

alter table binance_confirmation_jobs
  add column if not exists scan_id uuid references binance_scan_jobs(id) on delete cascade;
alter table binance_confirmation_jobs
  add column if not exists controls_per_event integer not null default 5;
alter table binance_confirmation_jobs
  add column if not exists prior_days integer not null default 10;
alter table binance_confirmation_jobs
  add column if not exists local_low_window_minutes integer not null default 480;
alter table binance_confirmation_jobs
  add column if not exists min_entry_notional numeric not null default 500;
alter table binance_confirmation_jobs
  add column if not exists discovery_pct integer not null default 70;
alter table binance_confirmation_jobs
  add column if not exists validation_pct integer not null default 15;
alter table binance_confirmation_jobs
  add column if not exists events_total integer not null default 0;
alter table binance_confirmation_jobs
  add column if not exists symbols_total integer not null default 0;
alter table binance_confirmation_jobs
  add column if not exists symbols_processed integer not null default 0;
alter table binance_confirmation_jobs
  add column if not exists controls_created integer not null default 0;
alter table binance_confirmation_jobs
  add column if not exists failures integer not null default 0;
alter table binance_confirmation_jobs
  add column if not exists cluster_rr_ci_low numeric;
alter table binance_confirmation_jobs
  add column if not exists cluster_rr_ci_high numeric;
alter table binance_confirmation_jobs
  add column if not exists duration_bands_positive integer not null default 0;

alter table binance_confirmation_jobs
  alter column protocol_version set default 'v8_h3_local_low_confirmation_1';
alter table binance_backtest_jobs
  alter column protocol_version set default 'v8_h3_continuous_executable_backtest_1';

create table if not exists binance_confirmation_issues (
  id bigint generated always as identity primary key,
  confirmation_job_id uuid not null references binance_confirmation_jobs(id) on delete cascade,
  symbol text,
  stage text not null,
  message text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_binance_confirmation_scan
  on binance_confirmation_jobs(scan_id, created_at);
create index if not exists idx_binance_confirmation_issues_job
  on binance_confirmation_issues(confirmation_job_id, created_at);

alter table binance_confirmation_issues enable row level security;

-- No anonymous policies are created. The app uses the server-side secret/service-role key only.
