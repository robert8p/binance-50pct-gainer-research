from datetime import datetime, timedelta, timezone

from app.classifier import classify_symbol, decision_observations, pct_change


def test_pct_change():
    assert pct_change(150, 100) == 50


def test_symbol_filter_fields():
    raw = {
        "symbol": "ABCUSDT",
        "baseAsset": "ABC",
        "quoteAsset": "USDT",
        "status": "TRADING",
        "permissions": ["SPOT"],
        "isSpotTradingAllowed": True,
        "orderTypes": ["LIMIT", "MARKET"],
    }
    item = classify_symbol(raw)
    assert item["spot_permission"] is True
    assert item["stablecoin_like"] is False


def test_decision_windows_have_london_dst_conversion():
    rows = []
    # 18 July is BST: 14:00 London is 13:00 UTC.
    for hour in range(24):
        rows.append(
            {
                "open_time": f"2026-07-18T{hour:02d}:00:00+00:00",
                "close_time": f"2026-07-18T{hour:02d}:59:59.999000+00:00",
                "close": 100 + hour,
                "high": 101 + hour,
            }
        )
    observations = decision_observations(rows, "2026-07-18")
    assert observations[0]["decision_time_utc"].startswith("2026-07-18T13:00:00")


def _minute(open_time: datetime, low: float, high: float) -> dict:
    return {
        "open_time": open_time.isoformat(),
        "close_time": (open_time + timedelta(seconds=59, milliseconds=999)).isoformat(),
        "open": low,
        "high": high,
        "low": low,
        "close": high,
    }


def test_rolling_surge_can_cross_utc_midnight():
    from app.classifier import first_rolling_surge

    day_start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    rows = [
        _minute(day_start - timedelta(minutes=120), 100, 101),
        _minute(day_start + timedelta(minutes=30), 120, 150),
    ]
    event = first_rolling_surge(
        rows,
        event_day_start=day_start,
        event_day_end=day_start + timedelta(days=1),
        threshold_pct=50,
        window_minutes=480,
    )
    assert event is not None
    assert event["baseline_price"] == 100
    assert event["crossing_time"] == day_start + timedelta(minutes=30)


def test_rolling_surge_excludes_same_minute_move():
    from app.classifier import first_rolling_surge

    day_start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    rows = [_minute(day_start, 100, 151)]
    assert first_rolling_surge(
        rows,
        event_day_start=day_start,
        event_day_end=day_start + timedelta(days=1),
        threshold_pct=50,
        window_minutes=480,
    ) is None


def test_rolling_surge_conservatively_excludes_480_minute_open_gap():
    from app.classifier import first_rolling_surge

    day_start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    rows = [
        _minute(day_start, 100, 101),
        _minute(day_start + timedelta(minutes=480), 120, 151),
    ]
    assert first_rolling_surge(
        rows,
        event_day_start=day_start,
        event_day_end=day_start + timedelta(days=1),
        threshold_pct=50,
        window_minutes=480,
    ) is None
