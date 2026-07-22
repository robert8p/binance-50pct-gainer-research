# Quality report — v4.0.0

## Automated validation completed in the build environment

- 29 relevant network-free tests passed.
- Python compilation passed for all application modules.
- Ten-day features were verified to ignore the decision minute and all future bars.
- Required 5-, 7- and 10-day windows were verified.
- Structural feature families and schema/migration contracts were verified.
- The migration was scanned for destructive SQL operations.

The two unchanged positive-event archive tests require PyArrow at test-import time. PyArrow is pinned in `requirements.txt` and installed by GitHub Actions/Render, but it was unavailable in the offline packaging environment. The underlying v3 research code was not changed.

## Integrity controls

- Predictors end at the last completed minute before each decision timestamp.
- Outcome columns are explicitly prefixed `outcome_`.
- Existing opened data produce one exploratory package, not misleading new validation claims.
- Fresh staged mode preserves discovery, validation and sealed-test packages.
- Source archives are cached, hashed and listed in the index manifest.
- Missing data remain flagged rather than forward-filled.

## Remaining limitations

Live Binance, Supabase and Render calls were not available in the packaging environment. Deployment should begin with the existing exploratory job before queuing a large earlier historical scan.
