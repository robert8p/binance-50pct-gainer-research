from app.classifier import decision_observations


def bar(open_time: str, close_time: str, close: float, high: float):
    return {
        "open_time": open_time,
        "close_time": close_time,
        "close": close,
        "high": high,
    }


def test_decision_outcome_excludes_entry_bar_high():
    rows = [
        bar("2026-07-01T13:00:00+00:00", "2026-07-01T13:00:59.999000+00:00", 100, 150),
        bar("2026-07-01T13:01:00+00:00", "2026-07-01T13:01:59.999000+00:00", 101, 110),
        bar("2026-07-01T13:02:00+00:00", "2026-07-01T13:02:59.999000+00:00", 102, 120),
    ]
    observations = decision_observations(rows, "2026-07-01")
    obs = next(x for x in observations if x["decision_label"].startswith("14:00"))
    assert obs["entry_close"] == 100
    assert obs["subsequent_high"] == 120
    assert obs["entry_time_utc"] == "2026-07-01T13:00:59.999000+00:00"
