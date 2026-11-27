"""Verify real knowledge artifacts; --rebuild also checks idempotence and source preservation."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from build_knowledge import OUT,ROOT,digest,packed

def source_hashes():
    paths=list((ROOT/"data/collection").rglob("*.json"))+[ROOT/"data/normalized/catalog.jsonl"]
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def counts(db):
    return tuple(db.execute("SELECT count(*) FROM "+name).fetchone()[0] for name in
                 ("documents","chunks","condition_drafts","condition_groups"))

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--rebuild",action="store_true");args=parser.parse_args()
    with closing(sqlite3.connect(OUT/"knowledge.sqlite")) as db:
        before=counts(db)
    if args.rebuild:
        sources=source_hashes()
        subprocess.run([sys.executable,str(ROOT/"scripts/build_knowledge.py"),"build"],check=True,
                       stdout=subprocess.DEVNULL)
        assert sources==source_hashes(),"Source files changed"
    with closing(sqlite3.connect(OUT/"knowledge.sqlite")) as db:
        assert before==counts(db),"Repeat build changed row counts"
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        sections={}
        for doc,version,snapshot,fields in db.execute("SELECT id,version_hash,snapshot,fields FROM documents WHERE current=1"):
            assert digest(packed(json.loads(snapshot)))==version
            sections[doc]=json.loads(fields)
        assert len(sections)==16196
        chunks={}
        for cid,doc,field,start,end,text,previous,next_id in db.execute(
            "SELECT id,document_id,field,start,end,text,previous_id,next_id FROM chunks"):
            assert sections[doc][field][start:end]==text
            chunks[cid]=(doc,field,start,end,previous,next_id)
        for cid,(doc,field,start,end,previous,next_id) in chunks.items():
            if previous:
                other=chunks[previous]
                assert other[0:2]==(doc,field) and other[5]==cid and other[2]<start
            if next_id:
                other=chunks[next_id]
                assert other[0:2]==(doc,field) and other[4]==cid and other[2]>start
        checked=0
        for doc,status,payload in db.execute("SELECT document_id,status,payload FROM condition_drafts"):
            candidate=json.loads(payload)
            assert status=="draft" and candidate["usable_for_eligibility"] is False
            for cid in candidate["evidence_chunk_ids"]:
                assert chunks[cid][0]==doc
            assert candidate["evidence_chunk_ids"]
            checked+=1
        assert db.execute("SELECT count(*) FROM condition_groups WHERE logic IS NOT NULL").fetchone()[0]==0
        for term in ("한부모","자녀","소득"):
            assert db.execute("SELECT count(*) FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.current=1 AND instr(c.text,?)>0",(term,)).fetchone()[0]>0
        jobs=0
        for line in (OUT/"embedding_jobs.jsonl").open(encoding="utf-8"):
            job=json.loads(line);assert job["chunk_id"] in chunks
            assert job["input_sha256"]==digest(job["input"])
            assert job["status"]=="pending_model_selection"
            jobs+=1
        assert jobs==len(chunks)
        print(f"Knowledge data PASS: documents={len(sections)}, chunks={len(chunks)}, draft conditions={checked}, embedding inputs={jobs}")
        if args.rebuild:print("Rebuild PASS: unchanged IDs/counts and source file hashes")
if __name__=="__main__":main()
