from build_condition_drafts import hints
def main():
    record={"id":"gov24:test","fields":{"name":"Test","target":"한부모 대상 안내. 중복 지원 제외."},"source_condition_codes":{"JA0403":"Y","JA0110":0,"JA0111":18}}
    draft=hints(record)
    assert draft["usable_for_eligibility"] is False and draft["logic"] is None
    assert all(x["status"]=="draft" and x["subject"]=="unresolved" and x["operator"] is None for x in draft["questions"])
    assert any(x["question_key"]=="overlap" for x in draft["questions"])
    assert any(x["kind"]=="source_age_range" and x["raw_value"]==[0,18] for x in draft["questions"])
    assert not hints({"id":"empty","fields":{}})["questions"]
    assert not hints({"id":"missing","fields":{},"source_condition_codes":{"JA0403":None}})["questions"]
    print("Condition draft evidence and non-executable status: PASS")
if __name__=="__main__":main()
