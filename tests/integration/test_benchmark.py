import json

from scripts import benchmark


def test_benchmark_writes_report(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTENTBLITZ_OUTPUT_DIR", str(tmp_path / "out"))
    assert benchmark.main(["--mock", "--runs", "2", "--scenarios", "linkedin", "image", "--out", str(tmp_path),
                           "--label", "t"]) == 0
    data = json.loads((tmp_path / "t.json").read_text())
    assert set(data["summary"]) == {"linkedin", "image"} and data["meta"]["offline"] is True
    assert data["summary"]["linkedin"]["runs"] == 2 and data["summary"]["linkedin"]["llm_calls"] >= 2
    md = (tmp_path / "t.md").read_text()
    assert "| linkedin |" in md and "Offline mock mode: yes" in md
