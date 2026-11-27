"""Collect catalog pages with resumable checkpoints; compare source coverage."""
import collections
import contextlib
import datetime as dt
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path
from check_apis import ROOT, settings, request, redact

OUT = ROOT / "data" / "collection"
CONFIG = settings()
BUDGET = 850
calls = 0


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(redact(json.dumps(value, ensure_ascii=False, indent=2), CONFIG), encoding="utf-8")
    temp.replace(path)


def fetch(source, token, endpoint, params, key, key_param="serviceKey"):
    global calls
    path = OUT / source / f"{token}.json"
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached["params"] != params:
            raise RuntimeError(f"{source}: cached parameters changed; use a new collection folder")
        if cached["result"]["status"] in ("OK", "EMPTY") and not (source.endswith("-detail") and source.startswith("welfare-") and "_raw_xml" not in cached["result"].get("response", {})):
            return cached
    if calls >= BUDGET:
        raise RuntimeError("Run request budget reached; rerun to resume")
    results = []
    for attempt in range(2):
        if calls >= BUDGET:
            raise RuntimeError("Run request budget reached")
        calls += 1
        results = []
        with contextlib.redirect_stdout(io.StringIO()):
            rows = request(source, endpoint, params, key, CONFIG, results, key_param)
        if results[0]["status"] != "NETWORK_ERROR":
            break
        if attempt == 0:
            time.sleep(1)
    item = {"params": params, "result": results[0], "records": rows}
    save(path, item)
    time.sleep(0.12)
    if results[0]["status"] not in ("OK", "EMPTY"):
        raise RuntimeError(f"{source}: {results[0]['status']}")
    return item


def total_count(value):
    if isinstance(value, dict):
        for key in ("totalCount", "ALL_CNT"):
            if str(value.get(key, "")).isdigit():
                return int(value[key])
        for child in value.values():
            found = total_count(child)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = total_count(child)
            if found is not None:
                return found
    return None


def collect(source, endpoint, params, key, page_key, size_key, key_param="serviceKey"):
    rows, signatures, declared = [], set(), None
    for page in range(1, 1001):
        item = fetch(source, f"page-{page:04}", endpoint,
                     {**params, page_key:page, size_key:100}, key, key_param)
        batch = item["records"]
        count = total_count(item["result"].get("response"))
        if declared is None:
            declared = count
        signature = hashlib.sha256(json.dumps(batch, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if batch and signature in signatures:
            raise RuntimeError(f"{source}: repeated page; pagination not advancing")
        signatures.add(signature)
        rows.extend(batch)
        if declared is not None and len(rows) >= declared:
            if len(rows) != declared:
                raise RuntimeError(f"{source}: count exceeds advertised total")
            break
        if not batch:
            if declared is not None and len(rows) != declared:
                raise RuntimeError(f"{source}: early empty page {len(rows)}/{declared}")
            break
        if page % 10 == 0:
            print(f"{source}: {len(rows)} rows", flush=True)
    else:
        raise RuntimeError(f"{source}: page safety limit")
    save(OUT / source / "catalog.json", rows)
    return rows, {"rows":len(rows), "advertised_total":declared,
                  "pages":page, "status":"COMPLETE",
                  "completion_basis":"advertised total" if declared is not None else "empty page"}


def normalized(name):
    return re.sub(r"[^가-힣a-z0-9]", "", str(name).lower())


def compare(catalogs):
    groups = collections.defaultdict(list)
    for source, rows in catalogs.items():
        if source not in ("gov24-list", "welfare-central", "welfare-local"):
            continue
        for row in rows:
            name = row.get("서비스명") or row.get("servNm") or ""
            if normalized(name):
                groups[normalized(name)].append({
                    "source":source, "id":row.get("서비스ID") or row.get("servId"), "name":name,
                    "agency":row.get("소관기관명") or row.get("jurMnofNm") or row.get("bizChrDeptNm"),
                    "region":row.get("ctpvNm"), "district":row.get("sggNm")})
    matches = [v for v in groups.values() if len({x["source"] for x in v}) > 1]
    welfare_only = [x for v in groups.values() if not any(x["source"] == "gov24-list" for x in v)
                    for x in v if x["source"].startswith("welfare-")]
    return {"method":"Exact normalized title candidates only; not verified duplicates or confirmed omissions.",
            "cross_source_title_groups":len(matches), "candidates":matches,
            "welfare_titles_not_matched_to_gov24":len(welfare_only),
            "unmatched_welfare_candidates":welfare_only}


def details(catalogs):
    output = {}
    for source, base, operation, key, fields in (
        ("welfare-central","NationalWelfareInformationsV001","NationalWelfaredetailedV001",
         "WELFARE_CENTRAL_SERVICE_KEY", ("tgtrDtlCn", "slctCritCn", "alwServCn", "wlfareInfoOutlCn")),
        ("welfare-local","LocalGovernmentWelfareInformations","LcgvWelfaredetailed",
         "WELFARE_LOCAL_SERVICE_KEY", ("sprtTrgtCn", "slctCritCn", "alwServCn", "aplyMtdCn"))):
        samples = catalogs.get(source, [])[:10]
        values = []
        for row in samples:
            service_id = row["servId"]
            params = {"servId":service_id}
            if source == "welfare-central":
                params["callTp"] = "D"
            item = fetch(source+"-detail", service_id, f"B554287/{base}/{operation}", params, key)
            values.append(item)
        output[source] = {"sample_count":len(values), "fields_present":{
            field:sum(bool(x["result"].get("response", {}).get(field)) for x in values) for field in fields},
            "note":"First 10 catalog services; not a representative accuracy evaluation. wlfareInfoOutlCn is an outline, not necessarily application instructions."}
    return output



def quality(catalogs):
    fields = {
        "gov24-list": ("서비스ID", "서비스명", "지원대상", "선정기준", "지원내용", "신청방법", "신청기한", "상세조회URL"),
        "gov24-detail": ("서비스ID", "지원대상", "선정기준", "지원내용", "신청방법", "구비서류", "법령"),
        "welfare-central": ("servId", "servNm", "servDgst", "servDtlLink"),
        "welfare-local": ("servId", "servNm", "servDgst", "servDtlLink", "ctpvNm", "sggNm"),
        "myhome": ("pblancId", "houseSn", "pblancNm", "beginDe", "endDe", "url"),
        "lh-notice": ("PAN_ID", "PAN_NM", "DTL_URL", "PAN_SS"),
    }
    report = {}
    for source, names in fields.items():
        if source not in catalogs:
            continue
        rows = catalogs[source]
        report[source] = {"rows": len(rows), "nonempty_fields":{
            field: sum(bool(str(row.get(field) or "").strip()) for row in rows) for field in names}}
    gov_sets = {source:{row.get("서비스ID") for row in catalogs[source] if row.get("서비스ID")}
                for source in ("gov24-list", "gov24-detail", "gov24-conditions") if source in catalogs}
    if "gov24-list" in gov_sets:
        report["gov24_id_links"] = {
            source: {"unique_ids":len(ids),
                     "missing_from_list":len(ids - gov_sets["gov24-list"]),
                     "list_ids_not_in_source":len(gov_sets["gov24-list"] - ids)}
            for source, ids in gov_sets.items()}
    report["note"] = "Nonempty field counts measure presence, not correctness. Same names are only duplicate candidates."
    return report


def main():
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    # Freeze date range for safe resume, rather than silently changing existing pages.
    scope_path = OUT / "scope.json"
    if scope_path.exists():
        scope = json.loads(scope_path.read_text(encoding="utf-8"))
    else:
        scope = {"start":(today-dt.timedelta(days=365)).strftime("%Y.%m.%d"),
                 "end":today.strftime("%Y.%m.%d"),
                 "created_at":dt.datetime.now(dt.timezone.utc).isoformat()}
        save(scope_path, scope)
    specs = []
    for operation, name in (("serviceList","list"),("serviceDetail","detail"),("supportConditions","conditions")):
        specs.append(("gov24-"+name,"https://api.odcloud.kr/api/gov24/v3/"+operation,
                      {"returnType":"JSON"},"GOV24_SERVICE_KEY","page","perPage","serviceKey"))
    specs.extend([
        ("welfare-central","B554287/NationalWelfareInformationsV001/NationalWelfarelistV001",
         {"callTp":"L","srchKeyCode":"001"},"WELFARE_CENTRAL_SERVICE_KEY","pageNo","numOfRows","serviceKey"),
        ("welfare-local","B554287/LocalGovernmentWelfareInformations/LcgvWelfarelist",
         {},"WELFARE_LOCAL_SERVICE_KEY","pageNo","numOfRows","serviceKey"),
        ("myhome","1613000/HWSPR02/rsdtRcritNtcList",
         {},"MYHOME_SERVICE_KEY","pageNo","numOfRows","serviceKey"),
        ("lh-notice","B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1",
         {"UPP_AIS_TP_CD":"06","PAN_NT_ST_DT":scope["start"],"CLSG_DT":scope["end"]},
         "LH_NOTICE_SERVICE_KEY","PAGE","PG_SZ","ServiceKey")])
    catalogs, summary = {}, {"scope":scope,"sources":{}}
    for spec in specs:
        source = spec[0]
        try:
            catalogs[source], summary["sources"][source] = collect(*spec)
        except RuntimeError as error:
            summary["sources"][source] = {"status":"INCOMPLETE","reason":str(error)}
        print(source, summary["sources"][source], flush=True)
        save(OUT/"summary.json", summary)
    save(OUT/"quality.json", quality(catalogs))
    comparison = compare(catalogs)
    save(OUT/"comparison.json", comparison)
    summary["comparison"] = {k:v for k,v in comparison.items() if k not in ("candidates","unmatched_welfare_candidates")}
    try:
        summary["welfare_detail_samples"] = details(catalogs)
    except RuntimeError as error:
        summary["detail_error"] = str(error)
    summary["network_requests_this_run"] = calls
    summary["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save(OUT/"summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return int(any(x["status"] != "COMPLETE" for x in summary["sources"].values()) or "detail_error" in summary)


if __name__ == "__main__":
    sys.exit(main())
