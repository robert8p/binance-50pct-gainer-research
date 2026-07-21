import shutil
import zipfile
from pathlib import Path

import app.research as research_module
from app.research import ResearchBuilder


class FakeDB:
    def __init__(self, root: Path):
        self.root = root
        self.rows = []
        self.uploads = []

    def upload_file(self, storage_path: str, local_path: Path, content_type: str):
        copied = self.root / f"upload_{len(self.uploads)}_{local_path.name}"
        shutil.copyfile(local_path, copied)
        self.uploads.append((storage_path, copied, content_type))

    def upsert(self, table, payload, on_conflict):
        self.rows.extend((table, row) for row in payload)


class FakeBinance:
    def klines(self, symbol, interval, start_ms, end_ms):
        return []


def test_large_source_archives_are_uploaded_separately_from_compact_zip(tmp_path, monkeypatch):
    def fake_download(url: str, destination: Path) -> bool:
        payload = tmp_path / "payload.csv"
        payload.write_text("1,2,3\n", encoding="utf-8")
        with zipfile.ZipFile(destination, "w") as archive:
            archive.write(payload, "payload.csv")
        return True

    monkeypatch.setattr(research_module, "download_archive", fake_download)
    db = FakeDB(tmp_path)
    builder = ResearchBuilder(db, FakeBinance(), tmp_path)
    event = {
        "id": "00000000-0000-0000-0000-000000000010",
        "symbol": "ABCUSDT",
        "event_date": "2026-07-02",
        "first_cross_time": "2026-07-02T01:00:00+00:00",
    }
    record, files = builder._build_event(
        "00000000-0000-0000-0000-000000000020",
        event,
        prior_days=1,
        include_1s=False,
        include_agg=False,
        include_trades=False,
    )
    assert record["status"] == "completed"
    roles = {row["role"] for row in files}
    assert "prior_day_raw_source_archive" in roles
    assert "event_day_predictor_bars" in roles
    assert "event_compact_metadata_and_manifest" in roles

    compact = next(path for storage, path, _ in db.uploads if storage.endswith("_compact.zip"))
    with zipfile.ZipFile(compact) as archive:
        names = archive.namelist()
    assert "metadata/event_metadata.json" in names
    assert "metadata/file_manifest.csv" in names
    assert not any(name.startswith("source_archives/") for name in names)
