import shutil
import zipfile
from pathlib import Path

import pandas as pd

import app.research as research_module
from app.research import AGG_COLUMNS, ResearchBuilder


class Dummy:
    pass


def test_archive_filter_is_strictly_pre_cutoff_and_normalises_microseconds(tmp_path, monkeypatch):
    source_zip = tmp_path / "source.zip"
    cutoff_ms = 1_735_689_600_010
    rows = [
        [1, "1", "1", 1, 1, (cutoff_ms - 1) * 1000, True, True],
        [2, "1", "1", 2, 2, cutoff_ms * 1000, True, True],
        [3, "1", "1", 3, 3, (cutoff_ms + 1) * 1000, True, True],
    ]
    csv_path = tmp_path / "rows.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, header=False)
    with zipfile.ZipFile(source_zip, "w") as archive:
        archive.write(csv_path, "rows.csv")

    def fake_download(url: str, destination: Path) -> bool:
        shutil.copyfile(source_zip, destination)
        return True

    monkeypatch.setattr(research_module, "download_archive", fake_download)
    output = tmp_path / "filtered.parquet"
    warnings = []
    builder = ResearchBuilder(Dummy(), Dummy(), tmp_path)
    builder._filtered_archive_to_parquet(
        "https://example.test/archive.zip",
        output,
        AGG_COLUMNS,
        timestamp_column="timestamp",
        cutoff_ms=cutoff_ms,
        warnings=warnings,
    )
    result = pd.read_parquet(output)
    assert warnings == []
    assert result["aggregate_trade_id"].tolist() == [1]
    assert result["timestamp_ms_normalized"].tolist() == [cutoff_ms - 1]
