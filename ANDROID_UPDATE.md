# Android deployment note

Use the GitHub, Supabase and Render websites in desktop-site mode. Replace the repository files, run `supabase/migrate_v10_to_v12.sql` once, confirm `/health` reports `12.0.0`, then queue the single V12 validation job from the dashboard.
