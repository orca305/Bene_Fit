"""Offline checks for pagination, checkpoint parameters, and title matching."""
import tempfile
from pathlib import Path
import collect_catalogs as c

def run():
    original_fetch, original_out = c.fetch, c.OUT
    with tempfile.TemporaryDirectory() as directory:
        c.OUT = Path(directory)
        try:
            def page(source, token, endpoint, params, key, key_param):
                n = params["page"]
                return {"records":[{"서비스ID":str(n)}], "result":{"response":{"totalCount":2}}}
            c.fetch = page
            rows, result = c.collect("test", "unused", {}, "unused", "page", "perPage")
            assert len(rows) == 2 and result["status"] == "COMPLETE"
            def repeated(*args):
                return {"records":[{"서비스ID":"same"}], "result":{"response":{"totalCount":3}}}
            c.fetch = repeated
            try:
                c.collect("repeat", "unused", {}, "unused", "page", "perPage")
            except RuntimeError as error:
                assert "repeated page" in str(error)
            else:
                raise AssertionError("Repeated page accepted")
            report = c.compare({"gov24-list":[{"서비스ID":"g","서비스명":"주거 급여"}],
                                "welfare-central":[{"servId":"w","servNm":"주거급여"},
                                                   {"servId":"x","servNm":"별도제도"}]})
            assert report["cross_source_title_groups"] == 1
            assert report["welfare_titles_not_matched_to_gov24"] == 1
        finally:
            c.fetch, c.OUT = original_fetch, original_out
    print("Collection checks passed")

if __name__ == "__main__":
    run()
