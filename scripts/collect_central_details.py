"""Resume all central welfare details; successful source files are reused."""
from collections import Counter
import json
import sys
import collect_catalogs as collection

FIELDS = ("tgtrDtlCn", "slctCritCn", "alwServCn", "applmetList", "crtrYr")


def validate(item, service_id):
    result = item["result"]
    value = result.get("response", {}).get("_xml_tree", {})
    if result.get("status") != "OK":
        raise ValueError(result.get("status", "UNKNOWN"))
    if not isinstance(value, dict) or value.get("servId") != service_id:
        raise ValueError("DETAIL_ID_MISMATCH")
    if not value.get("servNm"):
        raise ValueError("MISSING_NAME")
    return value


def collect_all():
    source = collection.OUT / "welfare-central" / "catalog.json"
    rows = json.loads(source.read_text(encoding="utf-8"))
    ids = [row["servId"] for row in rows]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Central source IDs missing or duplicated")
    report = {"source":"welfare-central","expected":len(ids),"completed":0,
              "failures":[], "field_presence":dict.fromkeys(FIELDS, 0)}
    report_path = collection.OUT / "central-details-summary.json"
    consecutive_errors = 0
    for index, service_id in enumerate(ids, 1):
        stop_reason = None
        try:
            item = collection.fetch("welfare-central-detail", service_id,
                "B554287/NationalWelfareInformationsV001/NationalWelfaredetailedV001",
                {"servId":service_id,"callTp":"D"}, "WELFARE_CENTRAL_SERVICE_KEY")
            value = validate(item, service_id)
            consecutive_errors = 0
            report["completed"] += 1
            for field in FIELDS:
                report["field_presence"][field] += bool(value.get(field))
        except (RuntimeError, ValueError) as error:
            consecutive_errors += 1
            report["failures"].append({"source_id":service_id,"reason":str(error)})
            path = collection.OUT / "welfare-central-detail" / f"{service_id}.json"
            failure = json.loads(path.read_text(encoding="utf-8"))["result"] if path.exists() else {}
            if failure.get("http_status") in (401, 403, 429):
                stop_reason = f"HTTP {failure['http_status']}; resume after authorization or quota recovery"
                report["retry_after"] = failure.get("retry_after")
            elif consecutive_errors >= 3:
                stop_reason = "Three consecutive errors; stopping to avoid repeated failed requests"
        report["network_requests_this_run"] = collection.calls
        report["processed"] = index
        report["pending"] = len(ids) - report["completed"]
        if stop_reason:
            report["stop_reason"] = stop_reason
        report["status"] = "COMPLETE" if report["completed"] == len(ids) else "INCOMPLETE"
        collection.save(report_path, report)
        if index % 20 == 0 or index == len(ids):
            print(f"Processed {index}/{len(ids)}; valid={report['completed']}; failures={len(report['failures'])}",flush=True)
        if stop_reason or collection.calls >= collection.BUDGET:
            break
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return 0 if report["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(collect_all())
