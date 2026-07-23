-- Binance 3-hour 50% surge research v5 -> v6
-- Additive only. Existing scans, controls and context packages are preserved.

create table if not exists binance_confirmation_jobs (
  id uuid primary key default gen_random_uuid(),
  baseline_context_job_id uuid not null references binance_baseline_context_jobs(id) on delete cascade,
  status text not null check (status in ('queued','running','completed','failed')),
  protocol_version text not null default 'v6_h1_fresh_confirmation_1',
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  heartbeat_at timestamptz,
  passed boolean,
  events_evaluable integer not null default 0,
  controls_evaluable integer not null default 0,
  event_hits integer not null default 0,
  control_hits integer not null default 0,
  event_rate numeric,
  control_rate numeric,
  matched_permutation_p numeric,
  unique_event_symbols_hit integer not null default 0,
  result_json jsonb,
  error_message text
);

create table if not exists binance_confirmation_files (
  id uuid primary key default gen_random_uuid(),
  confirmation_job_id uuid not null references binance_confirmation_jobs(id) on delete cascade,
  storage_path text not null,
  filename text not null,
  size_bytes bigint not null,
  sha256 text not null,
  content_type text not null,
  role text not null,
  created_at timestamptz not null default now(),
  unique (confirmation_job_id, storage_path)
);

create table if not exists binance_backtest_jobs (
  id uuid primary key default gen_random_uuid(),
  confirmation_job_id uuid not null references binance_confirmation_jobs(id) on delete restrict,
  status text not null check (status in ('queued','running','completed','completed_with_warnings','failed')),
  protocol_version text not null default 'v6_continuous_executable_backtest_1',
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  heartbeat_at timestamptz,
  window_start_date date not null,
  window_end_date_exclusive date not null,
  quote_assets jsonb not null default '["USDT","USDC","FDUSD"]'::jsonb,
  position_quote_notional numeric not null default 500 check (position_quote_notional = 500),
  take_profit_pct numeric not null default 15 check (take_profit_pct = 15),
  stop_loss_pct numeric not null default 5 check (stop_loss_pct = 5),
  max_hold_minutes integer not null default 180 check (max_hold_minutes = 180),
  fee_bps numeric not null default 10 check (fee_bps = 10),
  max_trades_per_day integer not null default 5 check (max_trades_per_day = 5),
  symbols_total integer not null default 0,
  symbols_processed integer not null default 0,
  candidate_signals integer not null default 0,
  completed_trades integer not null default 0,
  failures integer not null default 0,
  result_json jsonb,
  error_message text,
  check (window_start_date < window_end_date_exclusive),
  check (window_end_date_exclusive <= date '2026-05-22')
);

create table if not exists binance_backtest_files (
  id uuid primary key default gen_random_uuid(),
  backtest_job_id uuid not null references binance_backtest_jobs(id) on delete cascade,
  storage_path text not null,
  filename text not null,
  size_bytes bigint not null,
  sha256 text not null,
  content_type text not null,
  role text not null,
  created_at timestamptz not null default now(),
  unique (backtest_job_id, storage_path)
);

create table if not exists binance_backtest_issues (
  id bigint generated always as identity primary key,
  backtest_job_id uuid not null references binance_backtest_jobs(id) on delete cascade,
  symbol text,
  stage text not null,
  message text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_binance_confirmation_jobs_status
  on binance_confirmation_jobs(status, created_at);
create index if not exists idx_binance_confirmation_files_job
  on binance_confirmation_files(confirmation_job_id, created_at);
create index if not exists idx_binance_backtest_jobs_status
  on binance_backtest_jobs(status, created_at);
create index if not exists idx_binance_backtest_files_job
  on binance_backtest_files(backtest_job_id, created_at);
create index if not exists idx_binance_backtest_issues_job
  on binance_backtest_issues(backtest_job_id, created_at);

alter table binance_confirmation_jobs enable row level security;
alter table binance_confirmation_files enable row level security;
alter table binance_backtest_jobs enable row level security;
alter table binance_backtest_files enable row level security;
alter table binance_backtest_issues enable row level security;

-- No anonymous policies are created. The app uses the server-side secret/service-role key only.
