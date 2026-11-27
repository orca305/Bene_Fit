"""Freeze a small retrieval pilot before running either model."""
import hashlib,json,random,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/model-comparison"
def prepare():
    cases=json.loads((ROOT/"eval/embedding_queries.json").read_text(encoding="utf-8-sig"))
    db=sqlite3.connect(ROOT/"data/knowledge/knowledge.sqlite")
    corpus=[]
    for cid,rid,field,text,retrieval in db.execute("""SELECT c.id,d.record_id,c.field,c.text,c.retrieval_text
      FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.current=1
      AND c.field IN ('target','criteria') AND (d.record_id LIKE 'welfare-central:%' OR d.record_id LIKE 'welfare-local:%')
      ORDER BY c.id"""):
        corpus.append({"id":cid,"record_id":rid,"field":field,"text":text,"input":retrieval})
    queries=[];gold=set()
    for i,(query,rid,anchor) in enumerate(cases):
        relevant=[x for x in corpus if x["record_id"]==rid and anchor in x["text"]]
        if not relevant:raise ValueError(f"Missing evidence: {rid} {anchor}")
        ids=[x["id"] for x in relevant];gold.update(ids)
        queries.append({"id":f"q{i+1:02}","query":query,"record_id":rid,"anchor":anchor,"relevant_chunk_ids":ids})
    selected=[x for x in corpus if x["id"] in gold]
    other=[x for x in corpus if x["id"] not in gold]
    random.Random(20261127).shuffle(other)
    selected+=other[:max(0,256-len(selected))]
    selected.sort(key=lambda x:x["id"])
    payload={"scope":"Pilot on collected welfare target/criteria chunks; not full-corpus production evaluation",
      "seed":20261127,"annotation":"Agent-authored synthetic queries with anchored source evidence; relevance judgments are incomplete",
      "documents":selected,"queries":queries}
    OUT.mkdir(parents=True,exist_ok=True)
    body=json.dumps(payload,ensure_ascii=False,indent=2)
    (OUT/"evaluation.json").write_text(body,encoding="utf-8")
    (OUT/"evaluation.sha256").write_text(hashlib.sha256((OUT/"evaluation.json").read_bytes()).hexdigest(),encoding="ascii")
    print(json.dumps({"corpus":len(selected),"available_evidence_chunks":len(corpus),"queries":len(queries),"gold_chunks":len(gold)}))
if __name__=="__main__":prepare()
