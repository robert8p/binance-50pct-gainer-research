-- Binance V8 -> V9: frozen momentum-only continuous historical backtest.
-- Additive/preserving migration: all prior scans, confirmation jobs, backtests and files remain intact.

alter table binance_backtest_jobs
  alter column confirmation_job_id drop not null;

alter table binance_backtest_jobs
  alter column protocol_version set default 'v9_momentum_only_continuous_backtest_1';

alter table binance_backtest_jobs
  alter column take_profit_pct set default 10;

-- V6-V8 created a strict +15% constraint. Retain old rows while allowing the frozen V9 +10% target.
alter table binance_backtest_jobs
  drop constraint if exists binance_backtest_jobs_take_profit_pct_check;

alter table binance_backtest_jobs
  add constraint binance_backtest_jobs_take_profit_pct_check
  check (take_profit_pct in (10, 15));

comment on table binance_backtest_jobs is
  'Historical continuous backtests. V9 momentum-only jobs do not require a confirmation_job_id; earlier protocol rows remain linked.';
