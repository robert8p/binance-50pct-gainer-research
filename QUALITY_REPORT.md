# V10 quality report

## Scope

V10 changes the research hand-off rather than inventing another trading rule. The app now exports neutral raw evidence for ChatGPT analysis.

## Integrity protections

- The source period is fixed to a previously unexamined 180-day block.
- Event and control baselines use the same 480-minute rolling-minimum algorithm.
- Controls with a future 50% rise are rejected.
- Controls near known same-symbol events are rejected.
- Control baselines are not reused across matched groups.
- Whole UTC event dates remain in one chronological split.
- Raw histories are not forward-filled or imputed.
- Outcome columns are explicitly prefixed `outcome_` in sample metadata.
- Validation and sealed files are visibly named `DO_NOT_OPEN`.
- The app contains no V10 predictor, threshold search, model or trading rule.

## Tests

- 62 available network-free tests passed.
- Five V10 exporter helper tests passed.
- V10 migration contract test passed.
- Python compilation passed.
- Jinja template parsing passed.
- FastAPI health/version smoke test passed.
- Clean-package checksum verification is performed before release.

Two unchanged legacy research tests could not be collected in the local packaging environment because PyArrow was unavailable. PyArrow remains pinned in `requirements.txt` and is required on Render and GitHub Actions.

## Operational considerations

The discovery archive may be large because it contains millions of raw minute rows. Overlapping sample windows are deduplicated by physical symbol/time, monthly Binance archives are used for complete months, Parquet uses Zstandard compression, and Parquet files are stored without redundant ZIP recompression.

## Remaining limitations

- The source universe still begins with coins currently returned as tradeable by Binance, so historically delisted coins can be absent.
- Five controls per event are a research sample, not every possible non-event minute.
- The selected baseline remains a scanner-defined local low; the control design now matches this mechanically, but any final candidate still requires continuous-time testing.
- Raw aggregate trades are not included in the first discovery export because ten days of trades for hundreds of samples would be impractically large. Exact aggregate trades should be collected only after ChatGPT identifies a small number of candidate entry states.
