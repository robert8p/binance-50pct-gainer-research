from datetime import datetime, timezone

import pytest

from app.scanner import Scanner


class FakeDB:
    def __init__(self):
        self.rows = {}

    def upsert(self, table, payload, on_conflict, **kwargs):
        self.rows.setdefault(table, []).extend(payload)

    def insert(self, table, payload):
        self.rows.setdefault(table, []).append(payload)

    def update(self, table, filters, payload):
        pass


class FakeBinance:
    day_start = datetime(2026, 7, 1, tzinfo=timezone.utc)

    def klines(self, symbol, interval, start_ms, end_ms):
        assert interval == "1m"
        base = int(self.day_start.timestamp() * 1000)
        rows = []
        for minute in range(180):
            open_time = base + minute * 60_000
            high = 151 if minute == 179 else 101
            low = 100 if minute == 0 else 100.5
            rows.append(
                [
                    open_time,
                    "100.5",
                    str(high),
                    str(low),
                    "101",
                    "10",
                    open_time + 59_999,
                    "1000",
                    10,
                    "5",
                    "500",
                    "0",
                ]
            )
        return rows

    def aggregate_trades(self, symbol, start_ms, end_ms, max_pages=500):
        base = int(self.day_start.timestamp() * 1000)
        crossing = base + 179 * 60_000
        if start_ms == base:
            return ([{"a": 1, "p": "100", "q": "1", "f": 1, "l": 1, "T": base + 50_000, "m": False, "M": True}], False)
        if start_ms == crossing and end_ms - start_ms <= 60_000:
            return ([{"a": 2, "p": "150", "q": "1", "f": 2, "l": 2, "T": crossing + 1_000, "m": False, "M": True}], False)
        if start_ms == crossing + 1_000:
            # Exit liquidity exists below the +50% threshold. This must still pass
            # because v2 saleability proves executability, not price persistence.
            return ([{"a": 3, "p": "120", "q": "5", "f": 3, "l": 3, "T": start_ms + 2_000, "m": True, "M": True}], False)
        return ([], False)


def _context():
    previous = {
        "open_time": "2026-06-30T00:00:00+00:00",
        "close": 100.0,
    }
    current = {
        "open_time": "2026-07-01T00:00:00+00:00",
        "open": 100.5,
        "close": 120.0,
        "quote_volume": 100000.0,
        "trade_count": 1000,
    }
    symbol_info = {
        "symbol": "ABCUSDT",
        "base_asset": "ABC",
        "quote_asset": "USDT",
        "stablecoin_like": False,
        "leveraged_token_like": False,
    }
    return previous, current, symbol_info


def test_candidate_records_saleable_event_without_price_persistence():
    db = FakeDB()
    scanner = Scanner(db, FakeBinance())
    previous, current, symbol_info = _context()
    outcome = scanner._process_candidate(
        "00000000-0000-0000-0000-000000000001",
        symbol_info,
        previous,
        current,
        True,
        "v2_rolling_3h",
        50.0,
        180,
        500.0,
        300,
    )
    assert outcome == {"candidate_recorded": True, "sellability_pass": True}
    event = db.rows["binance_gainer_events"][0]
    assert event["sellability_pass"] is True
    assert event["seller_taker_notional_any_price"] == 600.0
    assert event["seller_taker_notional_at_or_above"] == 0.0
    assert event["minimum_exit_vwap"] == pytest.approx(120.0)
    assert event["exact_baseline_to_cross_seconds"] < 3 * 60 * 60
    assert event["first_cross_trade_time"].endswith("+00:00")
    assert db.rows["binance_event_agg_trades"][0]["event_id"] == event["id"]


class UnresolvedCrossBinance(FakeBinance):
    def aggregate_trades(self, symbol, start_ms, end_ms, max_pages=500):
        base = int(self.day_start.timestamp() * 1000)
        if start_ms == base:
            return ([{"a": 1, "p": "100", "q": "1", "f": 1, "l": 1, "T": base + 50_000, "m": False, "M": True}], False)
        return ([], False)


def test_unresolved_exact_cross_cannot_pass_saleability():
    db = FakeDB()
    scanner = Scanner(db, UnresolvedCrossBinance())
    previous, current, symbol_info = _context()
    outcome = scanner._process_candidate(
        "00000000-0000-0000-0000-000000000002",
        symbol_info,
        previous,
        current,
        True,
        "v2_rolling_3h",
        50.0,
        180,
        500.0,
        300,
    )
    event = db.rows["binance_gainer_events"][0]
    assert outcome["sellability_pass"] is False
    assert event["crossing_trade_unresolved"] is True
    assert event["first_cross_trade_time"] is None
    assert event["sellability_pass"] is False
