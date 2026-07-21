from app.binance import archive_url, normalize_archive_timestamp
from datetime import date


def test_archive_url():
    assert archive_url("klines", "BTCUSDT", date(2026, 7, 1), "1m").endswith(
        "BTCUSDT-1m-2026-07-01.zip"
    )


def test_archive_timestamp_normalisation():
    assert normalize_archive_timestamp(1735689600010866) == 1735689600010
    assert normalize_archive_timestamp(1600000000000) == 1600000000000


def test_download_archive_verifies_companion_checksum(tmp_path, monkeypatch):
    import hashlib
    import io
    import zipfile

    import app.binance as binance_module

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("rows.csv", "1,2,3\n")
    payload = buffer.getvalue()
    checksum = hashlib.sha256(payload).hexdigest()

    class Response:
        def __init__(self, status, body=b"", text=""):
            self.status_code = status
            self._body = body
            self.text = text

        def iter_content(self, chunk_size):
            yield self._body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(self.status_code)

    responses = iter([
        Response(200, body=payload),
        Response(200, text=f"{checksum}  sample.zip\n"),
    ])
    monkeypatch.setattr(binance_module.requests, "get", lambda *args, **kwargs: next(responses))
    destination = tmp_path / "sample.zip"
    assert binance_module.download_archive("https://example.test/sample.zip", destination) is True
    assert destination.read_bytes() == payload
