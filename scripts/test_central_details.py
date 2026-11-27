"""Offline validation for a central welfare detail."""
from collect_central_details import validate, collect_all
import collect_catalogs as collection
import contextlib
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

def main():
    good = {"result":{"status":"OK","response":{"_xml_tree":{"servId":"a","servNm":"Benefit"}}}}
    assert validate(good,"a")["servNm"] == "Benefit"
    for item, identifier in ((good,"b"),({"result":{"status":"EMPTY"}},"a"),
                             ({"result":{"status":"OK","response":{"_xml_tree":{"servId":"a"}}}},"a")):
        try:
            validate(item,identifier)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid detail accepted")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root/"welfare-central").mkdir()
        (root/"welfare-central"/"catalog.json").write_text(
            json.dumps([{"servId":"a"},{"servId":"b"}]),encoding="utf-8")
        requests = []
        def limited(source, token, *args):
            requests.append(token)
            folder = root / source
            folder.mkdir(exist_ok=True)
            (folder / f"{token}.json").write_text(json.dumps(
                {"result":{"status":"HTTP_ERROR","http_status":429}}),encoding="utf-8")
            raise RuntimeError("HTTP_ERROR")
        with patch.object(collection,"OUT",root), patch.object(collection,"fetch",limited), contextlib.redirect_stdout(io.StringIO()):
            assert collect_all() == 1
        report = json.loads((root/"central-details-summary.json").read_text(encoding="utf-8"))
        assert requests == ["a"]
        assert report["pending"] == 2 and report["status"] == "INCOMPLETE"
        assert "429" in report["stop_reason"]
    print("Central detail checks passed")

if __name__ == "__main__":
    main()
