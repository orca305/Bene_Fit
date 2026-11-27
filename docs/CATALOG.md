# 정규화 목록 및 로컬 검색

작성일: 2026-11-27.

## 실행

Python 기본 라이브러리만 사용하며 추가 API 호출은 하지 않는다.

    cd C:\dev\Bene_Fit
    python scripts/catalog.py build
    python scripts/catalog.py search 주거급여
    python scripts/catalog.py search 긴급복지 --limit 5
    python scripts/catalog.py search 주거급여 --all
    python scripts/catalog.py show welfare-central:WLF00003201

기본 검색은 중앙부처 출처 후보만 표시한다. --all은 지역·범위 미상도 포함한다.
검색어의 공백·기호를 정규화한 부분 문자열 검색이며, 이름 일치를 먼저 표시한다.
제도명 외 지원대상·내용·조건에도 검색하므로 관련 항목이 함께 표시될 수 있다.
자연어 의미 검색·RAG·개인별 추천은 아직 아니다. --json으로 전체 공통 필드를 출력한다.

## 결과

총 16,196건:
- 정부24 10,898건
- 복지로 중앙부처 461건
- 복지로 지자체 4,837건

검토 구분:
- national_candidate 1,509건: 정부24 중앙행정기관 1,048건 + 복지로 중앙부처 461건
- regional_source 14,091건: 지자체 출처 및 지역기관 유형
- scope_unknown 596건: 정부24 공공기관 출처

national_candidate는 중앙부처 출처에 따른 검토 우선순위이며 전국 적용을 확인한 분류가 아니다.
regional_source도 실제 적용 지역을 확정한 분류가 아니다. 모든 geographic_scope는 unverified다.
주거·복지와 인접 분야가 포함되어 있으며 MVP 지원 제도 목록으로 승인한 것은 아니다.

## 저장 파일

data/normalized/ 아래:
- catalog.sqlite: 로컬 검색 DB
- catalog.jsonl: 전체 정규화 레코드
- national_candidates.jsonl: 전국 제도 검토 후보만 추린 목록
- summary.json: 출처·검토 구분·상세 연결·누락 필드 건수

모두 Git 제외. 빌드 시 교체한다. 원천 카탈로그는 수정하지 않는다.

## 공통 필드와 출처

각 레코드는 출처:원천ID 형태의 고유 ID를 가진다.
fields에 이름·설명·기관·분야·대상·선정기준·지원내용·신청방법·출처 URL·시점을 저장한다.
존재하는 항목만 채우고 missing_fields로 주요 누락 항목을 표시한다.
각 필드의 원래 출처·원천 ID·목록/상세 구분·필드명을 provenance에 남긴다.
checked_at은 목록을 API에서 확인한 시각이며 정책의 시행일이나 상세 검토일이 아니다.
원천 수정일·기준연도·시행기간은 별도 필드다. 현재 신청 가능 여부를 자동 판정하지 않는다.

정부24는 같은 서비스 ID의 상세·지원조건을 연결한다.
지원조건 코드는 source_condition_codes로 원래 값을 보존하며 자격 규칙으로 승인하지 않는다.
복지로는 중앙부처 상세 88건·지자체 표본 10건을 같은 출처 ID로 연결했다. 중앙부처 나머지 373건은 일일 호출 한도 초과로 미수집이다.
중앙부처 신청 안내는 중첩 applmetList를 보존한 상세에서 가져온다.
동명 제도는 출처 사이에서 자동 병합하지 않으며, 임의로 누락 필드를 다른 출처로 채우지 않는다.

주거 모집공고(마이홈·LH)는 제도와 별도 개체라 이번 정규화 목록에 섞지 않았다.
원본 수집 폴더에 그대로 있으며 향후 회차·기간 모델로 연결해야 한다.

## 검증

    python scripts/test_catalog.py

출처 구분, 잘못된 상세 ID 거부, 중앙기관의 전국 확정 방지,
중첩 신청 안내, 기본/전체 검색 범위, 검색 입력 처리를 확인한다.
실제 데이터 빌드 및 주거급여·긴급복지 검색도 확인했다.

## 중앙부처 복지 상세 전체 수집

    python scripts/collect_central_details.py
    python scripts/catalog.py build

기존 중앙부처 목록의 모든 서비스 ID를 순차 조회한다. 성공한 상세는 재사용한다.
API 응답 성공 여부뿐 아니라 상세 ID·이름을 확인한다.
실패 항목은 건별 기록하고 나머지 수집을 계속한다. 동일 명령으로 재실행하면 실패 항목을 재시도한다.
통신 오류는 한 번 재시도하며 실행당 신규 호출 상한은 850회다.
보고서는 data/collection/central-details-summary.json에 기록한다.
완료 후 catalog.py build를 실행하면 수집된 상세가 검색 DB와 JSONL에 연결된다.
목록 확인시각과 상세 확인시각은 checked_at·detail_checked_at으로 구분한다.
상세 필드 provenance에도 실제 상세 조회시각을 기록한다.
법령·서식·문의처 등 중첩 참조는 source_references로 원천 구조를 유지한다.
제도별 내용 정확성·최신성·전국 적용·자격 규칙 승인과 수집 완료는 구분한다.

    python scripts/test_central_details.py

### 2026-11-27 전체 상세 수집 진행 결과

중앙부처 461건 중 88건 상세 수집·ID 검증·검색 반영 완료. 나머지 373건 대기.
API가 HTTP 429 및 returnReasonCode 22, ‘일일 서비스 요청제한 횟수 초과 에러’를 반환했다. Retry-After 헤더는 없었으며 정확한 재개 시각은 미확인이다.
401·403·429 응답 또는 연속 오류 3건 발생 시 즉시 중단한다. 제한 해제 후 같은 명령을 실행하면 성공한 88건을 재사용한다.
모든 성공 88건에서 지원대상·선정기준·지원내용·신청 안내·기준연도 필드가 존재했다. 내용 정확성을 승인한 것은 아니다.
공공데이터포털 활용신청 상세에서 해당 API의 일일 트래픽과 증량 가능 여부를 확인해야 한다.
