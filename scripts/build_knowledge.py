"""Versioned source snapshots, exact retrieval chunks and non-executable condition drafts."""
import argparse
from collections import Counter
from contextlib import closing
import datetime as dt
import hashlib
import json
import re
import sqlite3
from check_apis import ROOT
from build_condition_drafts import hints

PIPELINE="knowledge-v1"
OUT=ROOT/"data/knowledge"
SIZE,OVERLAP=1100,180

def packed(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def split_text(body,size=SIZE,overlap=OVERLAP):
    if not 0<=overlap<size:raise ValueError("Invalid chunk settings")
    start=0
    while start<len(body):
        end=min(start+size,len(body))
        if end<len(body):
            cuts=[start+m.end() for m in re.finditer(r"[。.!?]\s+|[\r\n]+|[;；]",body[start:end])]
            viable=[x for x in cuts if x>=start+size//2]
            if viable:end=viable[-1]
        yield start,end,body[start:end]
        if end==len(body):break
        start=max(start+1,end-overlap)

def chunks_for(record,doc):
    fields={k:v for k,v in record.get("fields",{}).items() if v and k in
            ("summary","target","criteria","benefit","application","documents","deadline","law")}
    if record.get("source_condition_codes"):
        fields["source_condition_codes"]=packed(record["source_condition_codes"])
    pieces=[]
    for field,body in fields.items():
        group=[]
        for start,end,text in split_text(body):
            group.append({"id":digest(packed([PIPELINE,doc,field,start,end,text])),
                "document_id":doc,"field":field,"start":start,"end":end,"text":text,
                "retrieval_text":f"{record['fields'].get('name','')} | {record['fields'].get('agency','')} | {field}\n{text}",
                "locator":{"representation":"normalized_field","field":field,"start":start,"end":end,
                           "source_mapping":record.get("provenance",{}).get(field)}})
        for i,piece in enumerate(group):
            piece["previous_id"]=group[i-1]["id"] if i else None
            piece["next_id"]=group[i+1]["id"] if i+1<len(group) else None
        pieces.extend(group)
    return fields,pieces

NUMBER=re.compile(r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>개월|명|세|년|%|원)\s*(?P<operator>이상|이하|초과|미만)")
OPS={"이상":"gte","이하":"lte","초과":"gt","미만":"lt"}

def conditions_for(record,doc,chunks):
    items=[]
    for hint in hints(record)["questions"]:
        field=hint["source_field"];start=hint.get("normalized_text_offset")
        linked=[c["id"] for c in chunks if
                (c["field"]==field and start is not None and c["start"]<=start<c["end"]) or
                (c["field"]=="source_condition_codes" and hint["kind"].startswith("source_"))]
        item={**hint,"document_id":doc,"evidence_chunk_ids":linked,"candidate_expression":None,
              "usable_for_eligibility":False}
        if hint["kind"]=="source_age_range":
            item["candidate_expression"]={"operator":"between","values":hint["raw_value"],
                "unit":"source_age_unit_unverified","subject":None,"inclusive":None}
        items.append(item)
    for field in ("target","criteria"):
        for match in NUMBER.finditer(record.get("fields",{}).get(field,"")):
            start,end=match.span()
            linked=[c["id"] for c in chunks if c["field"]==field and c["start"]<=start and end<=c["end"]]
            if linked:
                items.append({"kind":"numeric_text_candidate","question_key":None,"source_field":field,
                    "status":"draft","subject":"unresolved","usable_for_eligibility":False,
                    "document_id":doc,"evidence_chunk_ids":linked,
                    "locator":{"representation":"normalized_field","field":field,"start":start,"end":end},
                    "excerpt":match.group(),"candidate_expression":{"operator":OPS[match["operator"]],
                        "value":match["number"],"unit":match["unit"],"subject":None},
                    "warning":"Subject, alternatives, exceptions and period unreviewed."})
    for i,item in enumerate(items):
        item["group_id"]=digest(doc+":conditions")
        item["id"]=digest(packed([PIPELINE,doc,i,item]))
    return items

def create_schema(db):
    if db.execute("PRAGMA user_version").fetchone()[0] not in (0,1):raise ValueError("Unsupported DB schema")
    db.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,record_id TEXT NOT NULL,version_hash TEXT NOT NULL,
      current INTEGER NOT NULL,snapshot TEXT NOT NULL,metadata TEXT NOT NULL,fields TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS documents_record ON documents(record_id,current);
    CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id),
      field TEXT NOT NULL,start INTEGER,end INTEGER,text TEXT NOT NULL,retrieval_text TEXT NOT NULL,
      previous_id TEXT,next_id TEXT,locator TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
    CREATE TABLE IF NOT EXISTS condition_groups(id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id),
      status TEXT NOT NULL CHECK(status='draft'),logic TEXT,relation_evidence TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS condition_drafts(id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id),
      group_id TEXT NOT NULL REFERENCES condition_groups(id),status TEXT NOT NULL CHECK(status='draft'),payload TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS conditions_document ON condition_drafts(document_id);
    PRAGMA user_version=1;
    """)

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sources():
    base=ROOT/"data/collection";raw={};details={}
    for name in ("gov24-list","gov24-detail","gov24-conditions","welfare-central","welfare-local"):
        raw[name]={str(r.get("서비스ID") or r.get("servId")):r for r in read_json(base/name/"catalog.json")}
    for source in ("welfare-central","welfare-local"):
        for path in (base/(source+"-detail")).glob("*.json"):
            result=read_json(path)["result"]
            if result["status"]=="OK":
                value=result["response"]
                if value.get("_xml_tree",{}).get("servId")!=path.stem:raise ValueError("Detail ID mismatch")
                details[(source,path.stem)]=value
    return raw,details

def snapshot_for(record,raw,details):
    source,sid=record["source"],record["source_id"]
    if source=="gov24":
        original={name:raw[name].get(sid) for name in ("gov24-list","gov24-detail","gov24-conditions")}
        locators=[{"path":f"data/collection/{name}/catalog.json","source_id":sid} for name in original]
    else:
        original={"catalog":raw[source][sid]}
        locators=[{"path":f"data/collection/{source}/catalog.json","source_id":sid}]
        if (source,sid) in details:
            original["detail"]=details[(source,sid)]
            locators.append({"path":f"data/collection/{source}-detail/{sid}.json","source_id":sid})
    return {"record_id":record["id"],"original_records":original,"normalized_fields":record["fields"],
            "source_condition_codes":record.get("source_condition_codes",{})},locators

def build():
    OUT.mkdir(parents=True,exist_ok=True);raw,details=sources()
    records=[json.loads(line) for line in (ROOT/"data/normalized/catalog.jsonl").read_text(encoding="utf-8").splitlines()]
    if len({r["id"] for r in records})!=len(records):raise ValueError("Duplicate record IDs")
    stats=Counter()
    with closing(sqlite3.connect(OUT/"knowledge.sqlite")) as db:
        create_schema(db)
        with db:
            db.execute("UPDATE documents SET current=0")
            for record in records:
                snapshot,locators=snapshot_for(record,raw,details)
                version=digest(packed(snapshot));doc=record["id"]+"@"+version
                fields,chunks=chunks_for(record,doc)
                meta={"source":record["source"],"source_id":record["source_id"],
                    "name":record["fields"].get("name"),"source_url":record["fields"].get("source_url"),
                    "source_modified_at":record["fields"].get("source_modified_at"),
                    "reference_year":record["fields"].get("reference_year"),"checked_at":record.get("checked_at"),
                    "detail_checked_at":record.get("detail_checked_at"),"locators":locators,"pipeline":PIPELINE,
                    "snapshot_kind":"extracted_API_records_and_XML_when_available",
                    "embedding_status":"not_generated","applicable_period_verified":False}
                db.execute("INSERT INTO documents VALUES(?,?,?,1,?,?,?) ON CONFLICT(id) DO UPDATE SET current=1,metadata=excluded.metadata",
                    (doc,record["id"],version,packed(snapshot),packed(meta),packed(fields)))
                for c in chunks:
                    db.execute("INSERT OR IGNORE INTO chunks VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (c["id"],doc,c["field"],c["start"],c["end"],c["text"],c["retrieval_text"],
                         c["previous_id"],c["next_id"],packed(c["locator"])))
                relations=[]
                for field in ("target","criteria"):
                    for match in re.finditer(r"또는|그리고|다만|제외|예외|중복|모두|이면서|및",fields.get(field,"")):
                        relations.append({"field":field,"start":match.start(),"end":match.end(),"text":match.group()})
                db.execute("INSERT OR IGNORE INTO condition_groups VALUES(?,?,'draft',NULL,?)",
                    (digest(doc+":conditions"),doc,packed(relations)))
                conditions=conditions_for(record,doc,chunks)
                for c in conditions:
                    db.execute("INSERT OR IGNORE INTO condition_drafts VALUES(?,?,?,'draft',?)",(c["id"],doc,c["group_id"],packed(c)))
                stats.update(documents=1,chunks=len(chunks),condition_drafts=len(conditions))
                stats.update(c["kind"] for c in conditions)
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        temp=OUT/"embedding_jobs.tmp.jsonl"
        with temp.open("w",encoding="utf-8") as stream:
            for cid,doc,field,text in db.execute("SELECT c.id,c.document_id,c.field,c.retrieval_text FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.current=1 ORDER BY c.id"):
                stream.write(packed({"chunk_id":cid,"document_id":doc,"field":field,"input":text,
                    "input_sha256":digest(text),"status":"pending_model_selection"})+"\n")
        temp.replace(OUT/"embedding_jobs.jsonl")
        stats["stored_versions"]=db.execute("SELECT count(*) FROM documents").fetchone()[0]
    summary={"pipeline":PIPELINE,"created_at":dt.datetime.now(dt.timezone.utc).isoformat(),**dict(stats),
        "embeddings_generated":0,"approved_rules":0,"chunk_size":SIZE,"overlap":OVERLAP,
        "note":"Source snapshots, exact chunks, draft atoms and unresolved relation cues; no eligibility filtering."}
    (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

def search(query,limit):
    if not query.strip() or len(query)>200:raise ValueError("Query needs 1-200 characters")
    with closing(sqlite3.connect((OUT/"knowledge.sqlite").as_uri()+"?mode=ro",uri=True)) as db:
        rows=db.execute("""SELECT d.record_id,d.metadata,c.field,c.text,c.locator,c.id FROM chunks c
          JOIN documents d ON d.id=c.document_id WHERE d.current=1 AND instr(c.text,?)>0
          ORDER BY CASE c.field WHEN 'target' THEN 0 WHEN 'criteria' THEN 1 ELSE 2 END,d.record_id,c.start LIMIT ?""",(query,limit)).fetchall()
    for rid,meta,field,text,locator,cid in rows:
        print(packed({"record_id":rid,"source":json.loads(meta),"field":field,"text":text,"locator":json.loads(locator),"chunk_id":cid}))

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("build");find=sub.add_parser("search");find.add_argument("query");find.add_argument("--limit",type=int,default=5)
    args=parser.parse_args()
    if args.command=="build":build()
    elif 1<=args.limit<=20:search(args.query,args.limit)
    else:parser.error("--limit must be 1-20")
if __name__=="__main__":main()
