from pathlib import Path

import app.supabase as supabase_module
from app.supabase import SupabaseClient


class Response:
    def __init__(self, status_code):
        self.status_code = status_code
        self.headers = {}
        self.text = ""


class Session:
    def __init__(self):
        self.payloads = []

    def post(self, url, headers, data, timeout):
        self.payloads.append(data.read())
        return Response(503 if len(self.payloads) == 1 else 201)


def test_upload_retry_reopens_file(tmp_path, monkeypatch):
    monkeypatch.setattr(supabase_module.time, "sleep", lambda _: None)
    path = tmp_path / "payload.bin"
    path.write_bytes(b"complete-payload")
    client = SupabaseClient("https://example.test", "secret", "bucket")
    session = Session()
    client.session = session
    client.upload_file("x/payload.bin", path)
    assert session.payloads == [b"complete-payload", b"complete-payload"]
