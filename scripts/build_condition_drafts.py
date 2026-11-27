"""Generate evidence-linked condition hints for human review, never eligibility rules."""
from collections import Counter
import json
from pathlib import Path
from check_apis import ROOT

CODE_FIELDS={
 "JA0403":("family_status","한부모·조손 여부"),"JA0411":("children_count","다자녀 여부"),
 "JA0302":("pregnancy","임신 여부"),"JA0303":("birth_adoption","출산·입양 여부"),
 "JA0412":("housing_ownership","무주택 여부"),"JA0328":("disability","장애 등록 여부"),
 "JA0201":("income_basis","중위소득 0~50% 분류"),"JA0202":("income_basis","중위소득 51~75% 분류"),
 "JA0203":("income_basis","중위소득 76~100% 분류"),"JA0204":("income_basis","중위소득 101~200% 분류"),
 "JA0205":("income_basis","중위소득 200% 초과 분류")}
TEXT_TOPICS={
 "child_age":("개월","월령","세 이하 아동"),"birth_order":("첫째","둘째","셋째","출생순","출생 순"),
 "children_count":("다자녀","자녀가","자녀 수"),"family_status":("한부모","조손","미혼모"),
 "residency_duration":("거주","주민등록","전입"),"income_basis":("중위소득","소득인정액","건강보험료"),
 "assets":("재산","자산"),"overlap":("중복","제외"),"care_gap":("양육공백","돌봄","요양")}


def hints(record):
    items=[]
    for field in ("target","criteria"):
        body=record.get("fields",{}).get(field,"")
        for question,terms in TEXT_TOPICS.items():
            match=next((term for term in terms if term in body),None)
            if match:
                index=body.index(match)
                items.append({"kind":"text_hint","question_key":question,"source_field":field,
                    "provenance":record.get("provenance",{}).get(field),
                    "normalized_text_offset":index,"excerpt":body[max(0,index-60):index+140],
                    "status":"draft","subject":"unresolved","operator":None,"value":None})
    codes=record.get("source_condition_codes",{})
    for code,(question,label) in CODE_FIELDS.items():
        if codes.get(code) is not None:
            items.append({"kind":"source_category","question_key":question,"label":label,
                "source_field":code,"raw_value":codes[code],"status":"draft",
                "subject":"unresolved","operator":None,"value":None})
    if codes.get("JA0110") is not None and codes.get("JA0111") is not None:
        items.append({"kind":"source_age_range","question_key":"age","source_field":["JA0110","JA0111"],
             "raw_value":[codes["JA0110"],codes["JA0111"]],"status":"draft",
             "subject":"unresolved","operator":None,"value":None})
    return {"record_id":record["id"],"name":record["fields"].get("name"),
            "source_url":record["fields"].get("source_url"),"checked_at":record.get("detail_checked_at") or record.get("checked_at"),
            "review_status":"draft","usable_for_eligibility":False,
            "logic":None,"questions":items}


def main():
    source=ROOT/"data/normalized/catalog.jsonl"
    records=[json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    output=ROOT/"data/conditions";output.mkdir(parents=True,exist_ok=True)
    stats=Counter();question_records=Counter();with_hints=0
    temp=output/"drafts.tmp.jsonl"
    with temp.open("w",encoding="utf-8") as stream:
        for record in records:
            draft=hints(record);stream.write(json.dumps(draft,ensure_ascii=False)+"\n")
            if draft["questions"]:with_hints+=1
            stats.update(x["kind"] for x in draft["questions"])
            question_records.update({x["question_key"] for x in draft["questions"]})
    temp.replace(output/"drafts.jsonl")
    summary={"records":len(records),"records_with_hints":with_hints,"hint_counts":dict(stats),
             "records_per_question":dict(question_records),"approved_rules":0,
             "note":"Draft review hints only. A category Y or missing code is not a necessary or sufficient eligibility condition."}
    (output/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
