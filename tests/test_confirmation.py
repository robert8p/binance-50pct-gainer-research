from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.confirmation import FROZEN_ACCEPTANCE, _evaluate, derive_algorithmic_baseline, duration_band


def _frame(minutes: int = 1500) -> pd.DataFrame:
    index = pd.date_range(datetime(2025, 11, 1, tzinfo=timezone.utc), periods=minutes, freq="1min")
    frame = pd.DataFrame(index=index)
    frame["low"] = 100.0
    frame["high"] = 101.0
    frame["close"] = 100.5
    frame["quote_volume"] = 1000.0
    frame["observed"] = True
    return frame


def test_frozen_confirmation_acceptance_is_not_tunable() -> None:
    assert FROZEN_ACCEPTANCE["version"] == "v8_h3_local_low_confirmation_1"
    assert FROZEN_ACCEPTANCE["frozen_rule"] == {
        "volatility_1d_to_7d_ratio_min": 0.4,
        "ret_prior_1d_to_7d_pct_max": 5.0,
    }
    assert FROZEN_ACCEPTANCE["minimum_event_signal_rate"] == 0.30
    assert FROZEN_ACCEPTANCE["threshold_retuning_permitted"] is False


def test_algorithmic_baseline_uses_latest_equal_minimum_and_rejects_future_cross() -> None:
    frame = _frame()
    cross = frame.index[900]
    # Two equal lows in the prior 479 minutes. The scanner deque keeps the latest.
    frame.loc[frame.index[600], "low"] = 80.0
    frame.loc[frame.index[700], "low"] = 80.0
    derived = derive_algorithmic_baseline(frame, cross.to_pydatetime())
    assert derived is not None
    assert derived["baseline_time"] == frame.index[700].to_pydatetime()
    assert derived["duration_minutes"] == 200
    assert derived["duration_band"] == "gt_3h_to_6h"
    assert derived["contaminated"] is False

    frame.loc[frame.index[800], "high"] = 120.0  # 50% above the selected 80 low
    contaminated = derive_algorithmic_baseline(frame, cross.to_pydatetime())
    assert contaminated is not None
    assert contaminated["contaminated"] is True


def test_duration_bands_cover_the_eight_hour_target() -> None:
    assert duration_band(180) == "le_3h"
    assert duration_band(181) == "gt_3h_to_6h"
    assert duration_band(400) == "gt_6h_to_7h"
    assert duration_band(480) == "gt_7h_to_8h"


def test_evaluate_reports_event_and_control_rates() -> None:
    rows = []
    for group in range(8):
        rows.append({"match_group_id": str(group), "split": "sealed_test", "label": 1, "signal": group < 4, "symbol": f"E{group}"})
        for control in range(5):
            rows.append({"match_group_id": str(group), "split": "sealed_test", "label": 0, "signal": group == 0 and control == 0, "symbol": f"E{group}"})
    result = _evaluate(pd.DataFrame(rows), "overall")
    assert result["events"] == 8
    assert result["event_hits"] == 4
    assert result["controls"] == 40
    assert result["control_hits"] == 1
    assert result["event_rate"] == 0.5
    assert result["control_rate"] == 0.025
    assert result["unique_event_symbols_hit"] == 4
    assert result["matched_permutation_p"] is not None
