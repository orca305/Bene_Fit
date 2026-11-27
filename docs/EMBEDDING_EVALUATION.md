# BGE-M3 / KURE-v3 비교 계획

평가셋 생성: eval/embedding_queries.json → scripts/prepare_embedding_eval.py.
실행 전 질문·문서·정답 조각 ID와 SHA-256을 고정한다.

범위:
- 상세를 확보한 중앙부처·지자체 복지의 지원대상·선정기준 조각 198개
- 합성 질문 32개, 앵커가 있는 정답 조각 40개
- 개인정보 미포함
- 작은 파일럿이며 전체 88,458개 조각에서의 성능을 뜻하지 않는다
- 정답 목록 외에도 관련 근거가 있을 수 있어 완전한 관련성 판정 데이터는 아니다

모델:
- BAAI/bge-m3, 5617a9f61b028005a4858fdac845db406aefb181
- nlpai-lab/KURE-v3, 5b0494e801cd5cc21234012df1b83cfdb42b2065
- CPU, float32, 4스레드, 배치 2
- BGE-M3는 dense 검색만 비교. sparse·ColBERT·재순위는 별도 평가
- KURE-v3는 공식 query/passage 프롬프트 사용
- 기본 차원 비교 후 KURE-v3 1,024차원도 추가 측정
- 다운로드 시간과 모델 로딩·문서 인코딩·질의 인코딩 시간을 분리

품질:
- 정답 근거 Hit@1/5/10
- 정답 근거 첫 순위 MRR
- 제도 ID 기준 Hit@5 (근거가 아닌 같은 제도 검색의 보조 지표)
- 개별 질문 결과 및 상위 10개 조각 보존

운영:
- 문서 인코딩 초·초당 조각 수
- 질의 인코딩 중앙값·95백분위 (워밍업 후 32개 질문)
- 프로세스 RSS 최대 표본값, 벡터 배열 크기
- 0.1초 간격 메모리 표본이므로 순간 최고값을 놓칠 수 있다
- GPU 환경의 성능을 예측하는 수치가 아니다

실행:

    .venv-embedding\Scripts\python.exe scripts/prepare_embedding_eval.py
    .venv-embedding\Scripts\python.exe scripts/benchmark_embedding.py bge-m3
    .venv-embedding\Scripts\python.exe scripts/benchmark_embedding.py kure-v3

모델은 프로젝트 전용 data/model-comparison/models에 내려받는다.
기존 사용자 모델 캐시·AURORE 환경은 변경하지 않는다.
용량이 부족하면 결과·벡터를 보존한 후 이 작업이 내려받은 모델 가중치만 정리해 순차 실행한다.

CPU 진단에서 bfloat16 행렬 연산이 매우 느려 최종 비교는 두 모델 모두 float32로 통일한다. 중단한 bfloat16 인코딩은 결과에서 제외한다.

실행 환경: Intel 12논리 CPU, 총 메모리 약 15.7GiB. 시작 시 가용 메모리 약 4.4GiB. NVIDIA 도구는 발견되지 않았고 비교는 CPU만 사용한다. 모델을 순차 실행하며 BGE 결과·벡터를 보존한 뒤 이번 비교에서 받은 가중치 파일만 정리했다.

KURE 로딩에서 Transformers가 rope_parameters의 apply_yarn_scaling 키를 인식하지 못한다는 경고를 출력했다. 모델의 고정된 공식 config를 수정하지 않고 표준 Sentence Transformers/Transformers 로더로 실행했다. 최종 결과 해석 시 이 런타임 경고를 함께 기록한다.
