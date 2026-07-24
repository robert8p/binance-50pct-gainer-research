from __future__ import annotations

import pandas as pd

from app.confirmation import FROZEN_ACCEPTANCE, _evaluate


def test_frozen_confirmation_acceptance_is_not_tunable() -> None:
    assert FROZEN_ACCEPTANCE["version"] == "v7_h1_8h_fresh_confirmation_1"
    assert FROZEN_ACCEPTANCE["minimum_event_signal_rate"] == 0.25
    assert FROZEN_ACCEPTANCE["maximum_control_signal_rate"] == 0.15
    assert FROZEN_ACCEPTANCE["threshold_retuning_permitted"] is False


def test_evaluate_reports_event_and_control_rates() -> None:
    rows = []
    for group in range(8):
        rows.append({"match_group_id": str(group), "split": "sealed_test", "label": 1, "signal": group < 4, "symbol": f"E{group}"})
        for control in range(5):
            rows.append({"match_group_id": str(group), "split": "sealed_test", "label": 0, "signal": group == 0 and control == 0, "symbol": f"C{group}"})
    result = _evaluate(pd.DataFrame(rows), "overall")
    assert result["events"] == 8
    assert result["event_hits"] == 4
    assert result["controls"] == 40
    assert result["control_hits"] == 1
    assert result["event_rate"] == 0.5
    assert result["control_rate"] == 0.025
    assert result["unique_event_symbols_hit"] == 4
    assert result["matched_permutation_p"] is not None
