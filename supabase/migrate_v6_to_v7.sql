-- Binance eight-hour 50% surge research v6 -> v7
-- Additive/default-only migration. Existing three-hour rows and files are preserved.

alter table binance_scan_jobs
  alter column event_definition_version set default 'v7_rolling_8h';
alter table binance_scan_jobs
  alter column window_minutes set default 480;

alter table binance_gainer_events
  alter column event_definition_version set default 'v7_rolling_8h';
alter table binance_gainer_events
  alter column window_minutes set default 480;

alter table binance_matched_control_jobs
  alter column horizons_minutes set default '[15,30,60,120,180,480]'::jsonb;
alter table binance_matched_control_jobs
  alter column contamination_after_minutes set default 480;

alter table binance_context_jobs
  alter column horizons_minutes set default '[15,30,60,120,180,480]'::jsonb;
alter table binance_context_jobs
  alter column windows_minutes set default '[15,30,60,120,180,360,480,720,1440,2880,4320,7200,10080,14400]'::jsonb;

alter table binance_baseline_context_jobs
  alter column snapshot_offsets_minutes set default '[14400,10080,7200,4320,2880,1440,720,480,360,180,60,0]'::jsonb;

alter table binance_confirmation_jobs
  alter column protocol_version set default 'v7_h1_8h_fresh_confirmation_1';
alter table binance_backtest_jobs
  alter column protocol_version set default 'v7_continuous_executable_backtest_1';
