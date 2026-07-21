-- Additive migration for installations created by v1.x.
-- Existing rows remain NULL so v1 scans cannot be mistaken for v2 scans.
alter table binance_scan_jobs add column if not exists event_definition_version text;
alter table binance_scan_jobs add column if not exists window_minutes integer not null default 180;
alter table binance_scan_jobs add column if not exists candidates_found integer not null default 0;
alter table binance_scan_jobs alter column lookback_days set default 60;

alter table binance_gainer_events add column if not exists event_definition_version text;
alter table binance_gainer_events add column if not exists previous_day_bar_available boolean not null default true;
alter table binance_gainer_events add column if not exists window_minutes integer not null default 180;
alter table binance_gainer_events add column if not exists measurement_method text not null default 'rolling prior-minute low to later-minute high';
alter table binance_gainer_events add column if not exists baseline_time timestamptz;
alter table binance_gainer_events add column if not exists baseline_price numeric;
alter table binance_gainer_events add column if not exists baseline_trade_time timestamptz;
alter table binance_gainer_events add column if not exists baseline_agg_trade_id bigint;
alter table binance_gainer_events add column if not exists baseline_trade_unresolved boolean not null default false;
alter table binance_gainer_events add column if not exists minutes_baseline_open_to_cross_open integer;
alter table binance_gainer_events add column if not exists exact_baseline_to_cross_seconds numeric;
alter table binance_gainer_events add column if not exists exact_window_pass boolean not null default false;
alter table binance_gainer_events add column if not exists rolling_gain_pct_at_cross_trade numeric;
alter table binance_gainer_events add column if not exists missing_window_minute_bars integer not null default 0;
alter table binance_gainer_events add column if not exists seller_taker_notional_any_price numeric not null default 0;
alter table binance_gainer_events add column if not exists seller_taker_base_quantity_any_price numeric not null default 0;
alter table binance_gainer_events add column if not exists minimum_exit_vwap numeric;
alter table binance_gainer_events add column if not exists minimum_exit_vwap_pct_vs_threshold numeric;
alter table binance_gainer_events add column if not exists minimum_exit_reached_price numeric;
alter table binance_gainer_events add column if not exists lowest_seller_exit_price numeric;
alter table binance_gainer_events add column if not exists highest_seller_exit_price numeric;
