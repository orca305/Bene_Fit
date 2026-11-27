"""Offline checks for source identity, scope, detail mapping, and search."""
import json
import sqlite3
from catalog import normalize, search, text

def main():
    gov = {"서비스ID":"a","서비스명":"주거 급여","소관기관유형":"중앙행정기관","지원대상":"기본 대상"}
    detail = {"서비스ID":"a","지원대상":"상세 대상"}
    a = normalize("gov24",gov,detail)
    b = normalize("welfare-central",{"servId":"b","servNm":"주거급여"},
                  {"servId":"b","applmetList":[{"servSeDetailLink":"신청처"}]})
    assert a["id"] != b["id"]
    assert a["fields"]["target"] == "상세 대상"
    assert a["provenance"]["target"]["record"] == "detail"
    assert a["geographic_scope"] == "unverified"
    assert b["fields"]["application"] == "신청처"
    assert normalize("gov24",{"서비스ID":"c","소관기관유형":"공공기관"})["review_group"] == "scope_unknown"
    local = normalize("welfare-local",{"servId":"d","servNm":"주거급여","ctpvNm":"대전광역시"})
    assert local["review_group"] == "regional_source"
    assert text("소득 < 100 및 자산 > 0") == "소득 < 100 및 자산 > 0"
    try:
        normalize("gov24",gov,{"서비스ID":"wrong"})
    except ValueError:
        pass
    else:
        raise AssertionError("Mismatched detail ID accepted")
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE benefits (id TEXT, review_group TEXT, source TEXT, name_key TEXT, search_text TEXT, record TEXT)")
        for r in (a,b,local):
            db.execute("INSERT INTO benefits VALUES (?,?,?,?,?,?)",(r["id"],r["review_group"],r["source"],"주거급여","주거급여",json.dumps(r)))
        assert len(search(db,"주거 급여")) == 2
        assert len(search(db,"주거급여",True)) == 3
        assert not search(db,"주거' OR 1=1")
        try:
            search(db,"%%%")
        except ValueError:
            pass
        else:
            raise AssertionError("Empty normalized query accepted")
    print("Catalog checks passed")

if __name__ == "__main__":
    main()
