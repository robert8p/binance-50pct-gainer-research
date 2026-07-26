# Quality report — V12.0.0

- New V12 unit tests: protocol freeze, continuous T3 signal, R48 arming sequence, portfolio cap/cooldown, exact no-stop execution, and schema migration.
- 71 available automated tests passed.
- Two unchanged legacy research-export tests could not be collected in the packaging container because PyArrow was unavailable there. PyArrow remains pinned in `requirements.txt` for Render.
- All Python application and test files compile successfully.
- The V12 migration is additive and preserves all previous rows and Storage files.
- The validation dates, trigger thresholds, execution assumptions and graduation criteria are stored in `docs/V12_PREREGISTERED_PROTOCOL.json`.
