"""Build and search a local, source-preserving benefits catalog. No API calls."""
import argparse
from collections import Counter
from contextlib import closing
import datetime as dt
import html
import json
from pathlib import Path
import re
import sqlite3
import sys
from check_apis import ROOT

COLLECTION = ROOT / "data" / "collection"
OUTPUT = ROOT / "data" / "normalized"


def text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"</?[A-Za-z][^>]*>", " ", str(value)))).strip()


def norm(value):
    return re.sub(r"[^가-힣a-z0-9]", "", text(value).lower())


def normalize(source, row, detail=None, condition=None, checked_at=None):
    gov = source == "gov24"
    source_id = text(row.get("서비스ID" if gov else "servId"))
    if not source_id:
        raise ValueError(f"{source}: missing source ID")
    record = {
        "id":f"{source}:{source_id}", "source":source, "source_id":source_id,
        "fields":{}, "provenance":{}, "checked_at":checked_at,
        "geographic_scope":"unverified", "eligibility_rules_approved":False,
        "detail_available":detail is not None,
    }
    mapping = ({
        "name":"서비스명", "summary":"서비스목적요약", "agency":"소관기관명",
        "agency_type":"소관기관유형", "category":"서비스분야", "target":"지원대상",
        "criteria":"선정기준", "benefit":"지원내용", "application":"신청방법",
        "deadline":"신청기한", "source_url":"상세조회URL", "source_modified_at":"수정일시",
    } if gov else {
        "name":"servNm", "summary":"servDgst",
        "agency":"jurMnofNm" if source == "welfare-central" else "bizChrDeptNm",
        "category":"intrsThemaArray" if source == "welfare-central" else "intrsThemaNmArray",
        "source_url":"servDtlLink", "region":"ctpvNm", "district":"sggNm",
        "source_modified_at":"lastModYmd", "life_stage":"lifeArray" if source == "welfare-central" else "lifeNmArray",
    })
    def put(field, value, origin, original_field):
        cleaned = text(value)
        if cleaned:
            record["fields"][field] = cleaned
            record["provenance"][field] = {"source":source,"source_id":source_id,
                                           "record":origin,"field":original_field}
    for field, original in mapping.items():
        put(field, row.get(original), "catalog", original)
    if detail is not None:
        if str(detail.get("서비스ID" if gov else "servId")) != source_id:
            raise ValueError("Detail source ID mismatch")
        detail_mapping = ({
            "name":"서비스명","target":"지원대상","criteria":"선정기준","benefit":"지원내용",
            "application":"신청방법","documents":"구비서류","law":"법령","deadline":"신청기한",
            "apply_url":"온라인신청사이트URL","source_modified_at":"수정일시",
        } if gov else {
            "target":"tgtrDtlCn" if source == "welfare-central" else "sprtTrgtCn",
            "criteria":"slctCritCn","benefit":"alwServCn","application":"aplyMtdCn",
            "reference_year":"crtrYr","effective_from":"enfcBgngYmd","effective_to":"enfcEndYmd",
        })
        for field, original in detail_mapping.items():
            put(field, detail.get(original), "detail", original)
        if source == "welfare-central":
            items = detail.get("applmetList", [])
            if isinstance(items, dict):
                items = [items]
            instructions = [text(x.get("servSeDetailLink")) for x in items
                            if isinstance(x, dict) and x.get("servSeDetailLink")]
            put("application", " / ".join(instructions), "detail", "applmetList[].servSeDetailLink")
        record["source_references"] = {
            field:detail[field] for field in ("baslawList", "basfrmList", "inqplCtadrList", "inqplHmpgReldList")
            if detail.get(field)}
    if condition is not None:
        if str(condition.get("서비스ID")) != source_id:
            raise ValueError("Condition source ID mismatch")
        record["source_condition_codes"] = {k:v for k,v in condition.items() if k.startswith("JA")}
    central = source == "welfare-central" or (gov and row.get("소관기관유형") == "중앙행정기관")
    record["review_group"] = "national_candidate" if central else (
        "regional_source" if source == "welfare-local" or row.get("소관기관유형") in
        ("시군구","광역시도","지방출자_출연기관","지방공기업","교육청") else "scope_unknown")
    record["review_reason"] = "중앙부처 출처, 전국 적용 여부 검토 필요" if central else "지역·기관 적용 범위 검토 필요"
    record["missing_fields"] = [k for k in ("name","target","criteria","benefit","application","source_url")
                                if not record["fields"].get(k)]
    return record


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build():
    summary = load(COLLECTION/"summary.json")
    required = ("gov24-list","gov24-detail","gov24-conditions","welfare-central","welfare-local")
    if any(summary["sources"].get(s, {}).get("status") != "COMPLETE" for s in required):
        raise ValueError("Complete source catalogs required")
    catalogs = {s:load(COLLECTION/s/"catalog.json") for s in required}
    for source, rows in catalogs.items():
        key = "서비스ID" if source.startswith("gov24") else "servId"
        ids = [r.get(key) for r in rows]
        if len(ids) != len(set(ids)) or not all(ids):
            raise ValueError(f"{source}: duplicate or missing source IDs")
        if len(rows) != summary["sources"][source]["rows"]:
            raise ValueError(f"{source}: catalog count mismatch")
    gov_detail = {x["서비스ID"]:x for x in catalogs["gov24-detail"]}
    conditions = {x["서비스ID"]:x for x in catalogs["gov24-conditions"]}
    records = []
    source_stats = {}
    for source, catalog_name in (("gov24","gov24-list"),("welfare-central","welfare-central"),
                                 ("welfare-local","welfare-local")):
        times = {}
        for path in sorted((COLLECTION/catalog_name).glob("page-*.json")):
            page = load(path)
            for row in page["records"]:
                times[row.get("서비스ID") or row.get("servId")] = page["result"]["checked_at"]
        details = {}
        detail_times = {}
        if source != "gov24":
            for path in sorted((COLLECTION/(source+"-detail")).glob("*.json")):
                item = load(path)
                if item["result"]["status"] == "OK":
                    value = item["result"]["response"]
                    value = value.get("_xml_tree", value)
                    if isinstance(value, dict) and value.get("servId"):
                        if path.stem != value["servId"]:
                            raise ValueError(f"{source}: detail filename ID mismatch")
                        details[value["servId"]] = value
                        detail_times[value["servId"]] = item["result"].get("checked_at")
        for row in catalogs[catalog_name]:
            sid = row.get("서비스ID") or row.get("servId")
            record = normalize(source, row, gov_detail.get(sid) if source == "gov24" else details.get(sid),
                               conditions.get(sid) if source == "gov24" else None, times.get(sid))
            if source != "gov24" and sid in detail_times:
                record["detail_checked_at"] = detail_times[sid]
                for provenance in record["provenance"].values():
                    if provenance["record"] == "detail":
                        provenance["checked_at"] = detail_times[sid]
            records.append(record)
        source_stats[source] = len(catalogs[catalog_name])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT/"catalog.tmp.sqlite"
    if temp.exists():
        temp.unlink()
    with closing(sqlite3.connect(temp)) as db, db:
        db.execute("CREATE TABLE benefits (id TEXT PRIMARY KEY, review_group TEXT, source TEXT, name_key TEXT, search_text TEXT, record TEXT)")
        for record in records:
            fields = record["fields"]
            db.execute("INSERT INTO benefits VALUES (?,?,?,?,?,?)",
                       (record["id"],record["review_group"],record["source"],norm(fields.get("name","")),
                        norm(" ".join(fields.values())),json.dumps(record,ensure_ascii=False)))
        db.execute("CREATE INDEX benefits_group ON benefits(review_group)")
    temp.replace(OUTPUT/"catalog.sqlite")
    jsonl = OUTPUT/"catalog.tmp.jsonl"
    with jsonl.open("w",encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record,ensure_ascii=False)+"\n")
    jsonl.replace(OUTPUT/"catalog.jsonl")
    national = OUTPUT/"national_candidates.tmp.jsonl"
    with national.open("w",encoding="utf-8") as stream:
        for record in records:
            if record["review_group"] == "national_candidate":
                stream.write(json.dumps(record,ensure_ascii=False)+"\n")
    national.replace(OUTPUT/"national_candidates.jsonl")
    report = {"built_at":dt.datetime.now(dt.timezone.utc).isoformat(),
              "records":len(records),"sources":source_stats,
              "review_groups":dict(Counter(x["review_group"] for x in records)),
              "detail_available":dict(Counter(x["source"] for x in records if x["detail_available"])),
              "missing_fields":dict(Counter(k for x in records for k in x["missing_fields"])),
              "scope":"Benefits only; housing recruitment notices kept in original collections.",
              "note":"No cross-source merge. national_candidate is not verified nationwide eligibility."}
    (OUTPUT/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


def search(db, query, all_sources=False, limit=10):
    key = norm(query)
    if not key:
        raise ValueError("Search needs Korean letters, Latin letters or digits")
    # ponytail: substring scan, add a Korean search index when measured latency warrants it.
    return [json.loads(row[0]) for row in db.execute(
        "SELECT record FROM benefits WHERE instr(search_text, ?) > 0 "
        "AND (? OR review_group = 'national_candidate') "
        "ORDER BY CASE WHEN name_key = ? THEN 0 WHEN instr(name_key, ?) > 0 THEN 1 ELSE 2 END, id LIMIT ?",
        (key,int(all_sources),key,key,limit))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command",required=True)
    sub.add_parser("build")
    find = sub.add_parser("search")
    find.add_argument("query")
    find.add_argument("--all",action="store_true",help="Include regional and scope-unknown sources")
    find.add_argument("--limit",type=int,default=10)
    find.add_argument("--json",action="store_true")
    show = sub.add_parser("show")
    show.add_argument("id")
    args = parser.parse_args()
    if args.command == "build":
        build()
        return
    path = OUTPUT/"catalog.sqlite"
    if not path.exists():
        parser.error("Run catalog.py build first")
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)) as db:
        if args.command == "show":
            row = db.execute("SELECT record FROM benefits WHERE id=?",(args.id,)).fetchone()
            if not row:
                parser.error("Unknown record ID")
            print(json.dumps(json.loads(row[0]),ensure_ascii=False,indent=2))
            return
        if not 1 <= args.limit <= 100:
            parser.error("--limit must be between 1 and 100")
        try:
            rows = search(db,args.query,args.all,args.limit)
        except ValueError as error:
            parser.error(str(error))
        if args.json:
            print(json.dumps(rows,ensure_ascii=False,indent=2))
        else:
            print("전체 출처 검색" if args.all else "전국 제도 검토 후보 검색 (전국 적용 미검증)")
            for record in rows:
                fields = record["fields"]
                print(f"\n{record['id']} | {fields.get('name','')} | {fields.get('agency','')}")
                print(fields.get("summary") or fields.get("benefit","")[:200] or "설명 미확인")
                print(fields.get("source_url","출처 URL 미확인"))
            print(f"\n표시: {len(rows)}건 (최대 {args.limit}건)")


if __name__ == "__main__":
    main()
