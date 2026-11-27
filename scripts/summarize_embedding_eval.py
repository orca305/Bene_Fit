"""Summarize the two local dense-retrieval pilot runs."""
import datetime as dt,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/model-comparison"
def main():
    a=json.loads((OUT/"bge-m3-result.json").read_text(encoding="utf-8"))
    b=json.loads((OUT/"kure-v3-result.json").read_text(encoding="utf-8"))
    assert a["evaluation_sha256"]==b["evaluation_sha256"]
    assert (a["device"],a["dtype"],a["threads"],a["batch_size"])==(b["device"],b["dtype"],b["threads"],b["batch_size"])
    assert a["truncated_inputs"]==b["truncated_inputs"]==0
    all_rows=[("BGE-M3",a,a["results"][0]),("KURE-v3",b,b["results"][0]),("KURE-v3 1024차원",b,b["results"][1])]
    lines=["# 임베딩 모델 실측 비교","",
      "검증일: "+dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d")+" (Asia/Seoul)","",
      "공개 복지 문서의 지원대상·선정기준 조각 198개, 합성 질문 32개, 정답 근거 조각 40개로 비교했다.",
      "CPU·float32·4스레드·배치 2. 모든 입력은 잘림 없이 처리했다.","",
      "## 검색 품질","",
      "| 모델 | 차원 | 근거 Hit@1 | Hit@5 | Hit@10 | MRR | 제도 Hit@5 |",
      "|---|---:|---:|---:|---:|---:|---:|"]
    for label,run,r in all_rows:
        lines.append(f"| {label} | {r['dimension']} | {r['evidence_hit_at_1']:.1%} | {r['evidence_hit_at_5']:.1%} | {r['evidence_hit_at_10']:.1%} | {r['mrr']:.3f} | {r['record_hit_at_5']:.1%} |")
    lines+=["","Hit@k는 상위 k개에 지정한 정답 조각이 하나 이상 있는 질문의 비율이다. 모든 관련 근거의 Recall과 다르다.",
      "제도 Hit@5는 같은 제도를 찾았는지만 보는 보조 지표다.","","## 실행 비용","",
      "| 모델 | 문서 인코딩 | 초당 조각 | 질의 중앙값 | 질의 p95 | 최대 표본 RSS |",
      "|---|---:|---:|---:|---:|---:|"]
    for label,run in (("BGE-M3",a),("KURE-v3",b)):
        lines.append(f"| {label} | {run['document_encoding_seconds']:.1f}초 | {run['documents_per_second']:.2f} | {run['query_latency_median_ms']:.0f}ms | {run['query_latency_p95_ms']:.0f}ms | {run['peak_process_rss_gib']:.2f}GiB |")
    lines+=["","KURE 1024차원은 같은 2048차원 출력의 앞부분을 잘라 재정규화한 결과라 인코딩 비용은 같다.",
      "메모리는 0.1초 간격 프로세스 RSS 표본이며 GPU 메모리나 전체 시스템 사용량이 아니다.",
      "모델 다운로드·로딩 시간은 결과 JSON에 분리 기록했고 위 인코딩 시간에 포함하지 않았다.","",
      "## 질문별 차이",""]
    wins_a=wins_b=ties=0
    for qa,qb in zip(a["results"][0]["per_query"],b["results"][0]["per_query"]):
        ra,rb=qa["first_evidence_rank"],qb["first_evidence_rank"]
        wins_a+=ra<rb;wins_b+=rb<ra;ties+=ra==rb
        if ra!=rb:
            lines.append(f"- {qa['id']} {qa['query']} — BGE {ra}위 / KURE {rb}위")
    lines+=["",f"지정 근거 첫 순위: BGE 우세 {wins_a}개, KURE 우세 {wins_b}개, 동률 {ties}개.","",
      "## 해석 범위","",
      "- 전체 88,458개 조각이 아닌 작은 파일럿이다. 중앙부처 상세 수집이 일부만 완료돼 표본 편향이 있다.",
      "- 질문은 사람이 실제 서비스에서 제출한 기록이 아닌 에이전트 작성 합성 질문이다.",
      "- 정답 앵커 외에도 정답일 수 있는 문단이 있어 모든 관련성 판정이 완전하지 않다.",
      "- 예: q18은 온가족보듬사업 등 유사 지원이, q29는 부산 남구의 중복·유사 원천 ID가 검색돼도 지정 정답 외에는 이 지표에서 미적중으로 센다.",
      "- 따라서 1~2개 질문의 순위 차이를 한국어 검색 전반의 우열이나 실제 오답률 차이로 단정하지 않는다.",
      "- Dense 검색만 비교했다. 키워드 결합·BGE sparse·ColBERT·reranker는 측정하지 않았다.",
      "- CPU 실행 결과이며 GPU의 처리량·메모리 성능을 대신하지 않는다.",
      "- 모델별 1회 순차 실행이며 시스템 부하·발열을 통제한 반복 실험은 아니다.",
      "- KURE 로딩 시 rope_parameters.apply_yarn_scaling 미인식 경고가 있었다. 공식 config는 수정하지 않았다.",
      "- 기준일·숫자·예외의 최종 자격 판정 정확도를 평가한 결과가 아니다.",
      "- 모델은 리비전을 고정했고 개인 프로필이나 유료 API를 사용하지 않았다.","",
      "## 이번 파일럿에 대한 판단","",
      "KURE-v3 기본 2048차원은 지정 근거 1위 적중이 2문항 더 높았다. 상위 5개 적중은 두 모델 모두 32/32였다.",
      "실제 차이는 동일 제도의 대상/선정기준 근거를 먼저 배치한 q22·q24에서 났다. q18은 BGE가 3위, KURE가 4위였다.",
      "현재 CPU에서 BGE는 질의 인코딩이 약 3.2배, 문서 인코딩이 약 3.9배 빠르고 표본 RSS도 작았다.",
      "현 PC 개발 기준으로는 BGE-M3를 기본 후보로 제안하며, KURE는 근거 순위 품질을 중시하거나 GPU 운영을 검토할 때 확대 비교할 후보로 남긴다.",
      "KURE 1024차원은 이번 표본에서 상위 5개 적중이 1문항 감소했고 인코딩 비용은 줄지 않았다.",
      "전체 자료·실제 사용자 질문으로 확대하기 전에는 어느 모델의 일반적 우월성도 확정하지 않는다. 운영 모델 설정은 아직 변경하지 않았다.","",
      "## 재현","",
      "- eval/embedding_queries.json 및 data/model-comparison/evaluation.json",
      "- scripts/prepare_embedding_eval.py",
      "- scripts/benchmark_embedding.py bge-m3 / kure-v3",
      "- scripts/test_embedding_metrics.py",
      "- data/model-comparison/*-result.json, *-vectors.npz",
      "- docs/EMBEDDING_EVALUATION.md"]
    (ROOT/"docs/EMBEDDING_COMPARISON_RESULTS.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines[:27]))
if __name__=="__main__":main()
