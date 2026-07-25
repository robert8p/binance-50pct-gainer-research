# V9 deployment

This is an in-place upgrade.

1. Run `supabase/migrate_v8_to_v9.sql`.
2. Replace the existing repository contents with V9.
3. Wait for Render web and worker redeployment.
4. Confirm `/health` returns version `9.0.0`.
5. Queue the frozen 1 July–1 November 2025 momentum-only backtest once.
6. Download `continuous_backtest_results.zip` after completion.

See `WINDOWS_UPDATE.md` for the simplest detailed instructions.
