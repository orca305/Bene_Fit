"""Small, read-only public API smoke check. Python standard library only."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://apis.data.go.kr/"
KEYS = ("DATA_GO_KR_SERVICE_KEY", "GOV24_SERVICE_KEY",
        "WELFARE_CENTRAL_SERVICE_KEY", "WELFARE_LOCAL_SERVICE_KEY",
        "MYHOME_SERVICE_KEY", "LH_NOTICE_SERVICE_KEY",
        "LH_DETAIL_SERVICE_KEY", "LH_SUPPLY_SERVICE_KEY")


def settings():
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                name, sep, value = line.partition("=")
                if not sep or name.strip() not in KEYS:
                    raise ValueError("Invalid .env entry; use .env.example format.")
                values[name.strip()] = value.strip().strip("\"'")
    return {name: os.environ.get(name, values.get(name, "")) for name in KEYS}


def redact(text, config):
    for key in config.values():
        if key:
            for variant in (key, urllib.parse.unquote(key),
                            urllib.parse.quote(key, safe=""), urllib.parse.quote_plus(key)):
                text = text.replace(variant, "[REDACTED]")
    return text


def records(value):
    """Find common API row arrays without counting error metadata as data."""
    if isinstance(value, list):
        rows = [x for x in value if isinstance(x, dict)]
        if rows and any(k in rows[0] for k in ("서비스ID", "PAN_NM", "servId")):
            return rows
        for item in value:
            found = records(item)
            if found:
                return found
    if isinstance(value, dict):
        for name in ("data", "dsList", "dsList01", "dsSbd", "dsSplScdl", "dsAhflInfo", "dsEtcInfo", "item"):
            rows = value.get(name)
            if isinstance(rows, list):
                return [x for x in rows if isinstance(x, dict)]
            if isinstance(rows, dict):
                return [rows]
        for name, item in value.items():
            if name in ("dsSch", "resHeader") or name.endswith("Nm"):
                continue
            found = records(item)
            if found:
                return found
    return []


def parse(body):
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        root = ET.fromstring(body)
        value = {node.tag.split("}")[-1]: node.text for node in root.iter() if len(node) == 0}
        def structured(node):
            if not len(node):
                return node.text
            children = {}
            for child in node:
                children.setdefault(child.tag.split("}")[-1], []).append(structured(child))
            return {key: items[0] if len(items) == 1 else items for key, items in children.items()}
        value["_xml_tree"] = structured(root)
        value["_raw_xml"] = body
        rows = []
        for node in root.iter():
            tag = node.tag.split("}")[-1]
            if tag in ("servList", "item", "wantedList") and any(
                    child.tag.split("}")[-1] in ("servId", "servNm") for child in node):
                rows.append({c.tag.split("}")[-1]: c.text for c in node})
        if not rows and value.get("servId") and value.get("servNm"):
            rows = [value["_xml_tree"]]
        return value, rows
    return value, records(value)


def api_error(value):
    if isinstance(value, list):
        return next((error for x in value if (error := api_error(x))), None)
    if isinstance(value, dict):
        for name, allowed in (("resultCode", ("0", "00", "000", "NORMAL_SERVICE")),
                              ("SS_CODE", ("Y",)), ("errCd", ("0",)),
                              ("code", ("0", "200"))):
            if name in value and str(value[name]) not in allowed:
                return f"{name}={value[name]}"
        if value.get("errMsg") or value.get("returnAuthMsg"):
            return str(value.get("errMsg") or value.get("returnAuthMsg"))
        return next((error for x in value.values() if (error := api_error(x))), None)
    return None


def request(name, path, params, key_name, config, results, key_param="serviceKey"):
    key = config[key_name] or config["DATA_GO_KR_SERVICE_KEY"]
    result = {"api": name, "endpoint": path, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    results.append(result)
    if not key:
        result.update(status="MISSING_KEY", rows=0)
        print(f"[MISSING_KEY] {name}")
        return []
    params = {**params, key_param: urllib.parse.unquote(key)}
    url = (path if path.startswith("https://") else BASE + path) + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            body = response.read(5_000_001)
            if len(body) > 5_000_000:
                raise ValueError("Response exceeds 5 MB limit")
            body = body.decode("utf-8-sig")
            result["http_status"] = response.status
        value, rows = parse(body)
        error = api_error(value)
        result.update(status="API_ERROR" if error else ("OK" if rows else "EMPTY"),
                      rows=len(rows), fields=list(rows[0]) if rows else [],
                      error=error, response=value)
        print(f"[{result['status']}] {name}: {len(rows)} rows")
        return rows if not error else []
    except urllib.error.HTTPError as error:
        result.update(status="HTTP_ERROR", http_status=error.code)
        result["retry_after"] = error.headers.get("Retry-After")
        try:
            error_body = error.read(65536).decode("utf-8-sig", errors="replace")
            value, _ = parse(error_body)
            result["response"] = value
        except (ValueError, ET.ParseError, OSError):
            pass
    except (urllib.error.URLError, TimeoutError, OSError):
        result.update(status="NETWORK_ERROR")
    except (ValueError, ET.ParseError):
        result.update(status="PARSE_ERROR")
    print(f"[{result['status']}] {name}")
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        assert parse('{"data":[{"서비스ID":"1"}]}')[1][0]["서비스ID"] == "1"
        assert parse("<root><resultCode>00</resultCode><servList><servId>1</servId></servList></root>")[1][0]["servId"] == "1"
        detail, rows = parse("<root><servId>x</servId><servNm>Test</servNm><links><link>A</link><link>B</link></links></root>")
        assert len(rows) == 1 and detail["_xml_tree"]["links"]["link"] == ["A", "B"]
        assert detail["_raw_xml"].startswith("<root>")
        assert api_error({"response":{"header":{"resultCode":"30"}}})
        assert not api_error([{"dsSch":[{"SS_CODE":"Y"}]}])
        assert records([{"dsSch":[{"PAN_ID":"1"}]}, {"dsList01":[{"AREA":42}]}]) == [{"AREA":42}]
        assert redact("abc a%2Bb a+b", {"key":"a+b", "other":"abc"}) == "[REDACTED] [REDACTED] [REDACTED]"
        print("Self-test passed")
        return 0
    config, results = settings(), []
    def check(name, path, params, key, key_param="serviceKey"):
        return request(name, path, params, key, config, results, key_param)
    page = {"pageNo":1, "numOfRows":3}
    gov = "https://api.odcloud.kr/api/gov24/v3/"
    for operation in ("serviceList", "serviceDetail", "supportConditions"):
        check("gov24/" + operation, gov + operation,
              {"page":1,"perPage":3,"returnType":"JSON"}, "GOV24_SERVICE_KEY")
    check("welfare-central", "B554287/NationalWelfareInformationsV001/NationalWelfarelistV001",
          {**page,"callTp":"L","srchKeyCode":"001"}, "WELFARE_CENTRAL_SERVICE_KEY")
    check("welfare-local", "B554287/LocalGovernmentWelfareInformations/LcgvWelfarelist",
          page, "WELFARE_LOCAL_SERVICE_KEY")
    check("myhome", "1613000/HWSPR02/rsdtRcritNtcList", page, "MYHOME_SERVICE_KEY")
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    notices = check("lh-notice", "B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1",
                    {"PAGE":1,"PG_SZ":10,"UPP_AIS_TP_CD":"06",
                     "PAN_NT_ST_DT":(today-dt.timedelta(days=365)).strftime("%Y.%m.%d"),
                     "CLSG_DT":today.strftime("%Y.%m.%d")}, "LH_NOTICE_SERVICE_KEY", "ServiceKey")
    link_keys = ("SPL_INF_TP_CD","CCR_CNNT_SYS_DS_CD","PAN_ID","UPP_AIS_TP_CD")
    linked = next((row for row in notices if all(row.get(k) for k in link_keys)), None)
    for name, service, operation, key, key_param in (
        ("lh-detail","lhLeaseNoticeDtlInfo1","getLeaseNoticeDtlInfo1","LH_DETAIL_SERVICE_KEY","serviceKey"),
        ("lh-supply","lhLeaseNoticeSplInfo1","getLeaseNoticeSplInfo1","LH_SUPPLY_SERVICE_KEY","ServiceKey")):
        if linked:
            check(name, f"B552555/{service}/{operation}",
                  {k:linked[k] for k in link_keys}, key, key_param)
        else:
            results.append({"api":name,"status":"BLOCKED","reason":"LH notice with linking IDs required"})
            print(f"[BLOCKED] {name}: no linked LH notice")
    output = ROOT / "data" / "api-check"
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest.json").write_text(redact(json.dumps(results, ensure_ascii=False, indent=2), config), encoding="utf-8")
    print("Report: data/api-check/latest.json")
    return 0 if all(r["status"] == "OK" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
