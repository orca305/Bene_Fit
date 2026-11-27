from build_knowledge import split_text,chunks_for,conditions_for,digest,packed
def main():
    body="대상 아동 12세 이하. 자녀 2명 이상. 다만 예외 조건을 확인해야 합니다. "*150
    chunks=list(split_text(body,size=120,overlap=30))
    assert all(body[start:end]==part for start,end,part in chunks)
    covered=set()
    for start,end,_ in chunks:covered.update(range(start,end))
    assert len(covered)==len(body) and all(len(text)<=120 for _,_,text in chunks)
    record={"id":"test:1","fields":{"name":"Test","target":body},"provenance":{},"source_condition_codes":{"JA0110":0,"JA0111":18}}
    _,pieces=chunks_for(record,"doc")
    assert pieces[0]["next_id"] and pieces[1]["previous_id"]==pieces[0]["id"]
    atoms=conditions_for(record,"doc",pieces)
    assert all(a["usable_for_eligibility"] is False and a["evidence_chunk_ids"] for a in atoms)
    numeric=[a for a in atoms if a["kind"]=="numeric_text_candidate"]
    assert any(a["candidate_expression"]["value"]=="12" and a["candidate_expression"]["operator"]=="lte" for a in numeric)
    assert all(a["subject"]=="unresolved" for a in numeric)
    assert digest(packed(record))==digest(packed(record))
    assert digest(packed(record))!=digest(packed({**record,"fields":{"target":"changed"}}))
    print("Chunk coverage, offsets, adjacency, evidence links and draft-only atoms: PASS")
if __name__=="__main__":main()
