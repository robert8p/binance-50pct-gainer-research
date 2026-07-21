from app.scanner import Scanner


class DB:
    def __init__(self):
        self.rows = {}
        self.updates = []

    def upsert(self, table, payload, on_conflict, **kwargs):
        self.rows.setdefault(table, []).extend(payload)

    def update(self, table, filters, payload):
        self.updates.append((table, payload))

    def insert(self, table, payload):
        self.rows.setdefault(table, []).append(payload)


class Binance:
    def exchange_info(self):
        def symbol(name, base, quote):
            return {
                "symbol": name,
                "baseAsset": base,
                "quoteAsset": quote,
                "status": "TRADING",
                "permissions": ["SPOT"],
                "isSpotTradingAllowed": True,
                "orderTypes": ["LIMIT", "MARKET"],
            }

        return {
            "symbols": [
                symbol("ABCUSDC", "ABC", "USDC"),
                symbol("ABCUSDT", "ABC", "USDT"),
                symbol("XYZUSDC", "XYZ", "USDC"),
            ]
        }

    def klines(self, symbol, interval, start_ms, end_ms):
        return []


def test_quote_preference_selects_one_pair_per_base_coin():
    db = DB()
    result = Scanner(db, Binance()).run(
        {
            "id": "00000000-0000-0000-0000-000000000101",
            "lookback_days": 2,
            "threshold_pct": 50,
            "min_exit_notional": 500,
            "confirmation_window_seconds": 300,
            "quote_assets": ["USDT", "USDC", "FDUSD"],
        }
    )
    snapshots = db.rows["binance_symbol_snapshots"]
    selected = {row["symbol"] for row in snapshots if row["selected_canonical"]}
    assert selected == {"ABCUSDT", "XYZUSDC"}
    assert result["symbols_total"] == 2
