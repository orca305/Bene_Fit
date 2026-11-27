# API 연결 확인

## 1. 인증키 입력

저장소 루트의 .env 파일을 편집합니다. 일반 인증키(Decoding)를 사용하세요.
공통 인증키를 DATA_GO_KR_SERVICE_KEY= 오른쪽에 입력하면 됩니다.
정부24 등의 키가 다르면 해당 API 전용 항목에 입력하면 공통 키보다 우선합니다.
Encoding 키도 한 번 디코딩한 뒤 요청에 인코딩합니다. 환경변수가 파일 값보다 우선합니다.

- GOV24_SERVICE_KEY: 대한민국 공공서비스(혜택) 정보 (15113968)
- WELFARE_CENTRAL_SERVICE_KEY: 중앙부처복지서비스 (15090532)
- WELFARE_LOCAL_SERVICE_KEY: 지자체복지서비스 (15108347)
- MYHOME_SERVICE_KEY: 마이홈 공공주택 모집공고 (15108420)
- LH_NOTICE_SERVICE_KEY: LH 분양임대공고문 (15058530)
- LH_DETAIL_SERVICE_KEY: LH 공고별 상세정보 (15057999)
- LH_SUPPLY_SERVICE_KEY: LH 공고별 공급정보 (15056765)

.env와 data/는 Git에서 제외합니다. 키를 채팅이나 커밋에 넣지 마세요.
기존 .env는 자동으로 덮어쓰지 않습니다.

## 2. 실행

Python 3.10 이상. 별도 패키지 설치는 필요 없습니다.

    cd C:\dev\Bene_Fit
    python scripts/check_apis.py

소량의 첫 페이지를 조회합니다. 정부24는 목록·상세·지원조건을 각각 조회합니다.
LH는 최근 1년 범위의 임대주택 공고 목록에서 연결 ID가 있는 첫 공고로 상세·공급을 조회합니다.
요청당 제한시간은 25초입니다. 전체 수집이나 데이터 최신성·정확성 검증은 아닙니다.

## 3. 결과

콘솔에는 상태와 수신 건수만 표시합니다.
응답 표본·필드·오류코드는 data/api-check/latest.json에 저장합니다.
매 실행 시 보고서는 덮어씁니다. 요청 URL과 인증키는 저장하지 않습니다.

- OK: API 오류코드 없이 데이터 행 수신
- EMPTY: 응답 파싱은 됐지만 데이터 행을 확인하지 못함. 수집 성공으로 간주하지 않음
- MISSING_KEY: 키 미입력
- HTTP_ERROR: HTTP 상태 확인 필요 (예: 인증, 승인, 주소)
- API_ERROR: HTTP 성공이어도 API 자체 오류코드 반환
- NETWORK_ERROR / PARSE_ERROR: 통신 또는 응답 형식 확인 필요
- BLOCKED: LH 목록에서 상세·공급 연결 ID를 확보하지 못함

모든 조회가 OK이면 종료코드 0, 나머지는 1입니다.
목록이 비거나 연결 ID가 없으면 LH 상세·공급의 인증 성공 여부도 미확인입니다.
실제 키 입력 후 최초 호출로 엔드포인트·응답 구조·승인 상태를 검증해야 합니다.

## 자체 확인

    python scripts/check_apis.py --self-test

JSON/XML 파싱, 중첩 API 오류, 인증키 숨김을 확인합니다.

## 공식 명세

- https://www.data.go.kr/data/15113968/openapi.do
- https://www.data.go.kr/data/15090532/openapi.do
- https://www.data.go.kr/data/15108347/openapi.do
- https://www.data.go.kr/data/15108420/openapi.do
- https://www.data.go.kr/data/15058530/openapi.do
- https://www.data.go.kr/data/15057999/openapi.do
- https://www.data.go.kr/data/15056765/openapi.do
## 전체 목록 수집과 비교

    python scripts/collect_catalogs.py

정부24 목록·상세·지원조건, 복지로 중앙부처·지자체 목록,
마이홈 공공임대 공고 및 LH 임대주택 공고를 페이지 순회합니다.
LH는 최초 실행일 기준 최근 1년 조회 조건이며, 모든 역사적 공고 수집을 뜻하지 않습니다.
각 API가 현재 조회 조건으로 반환하는 카탈로그를 수집합니다.
복지로 상세는 중앙부처·지자체 각각 첫 10건 표본만 조회합니다.
LH 상세·공급 전체 조회는 수행하지 않습니다.

결과 위치: data/collection/
- source별 page-*.json: 요청 조건(키 제외), 조회 시각, 응답 및 추출 행
- source별 catalog.json: 합쳐진 목록
- welfare-*-detail/: 복지 상세 표본
- scope.json: 고정된 LH 기간 및 최초 실행 시각
- summary.json: 출처별 완료 여부·건수·필드 확인
- quality.json: 필드 존재 건수 및 정부24 서비스 ID 연결 확인
- comparison.json: 이름을 정규화한 출처 간 중복 후보·미매칭 후보

성공한 페이지는 재사용하며 실패한 페이지는 다음 실행 시 다시 요청합니다.
요청당 25초, 실행당 신규 요청 최대 850회, 페이지당 100건으로 제한합니다.
오류·조기 빈 페이지·반복 페이지·광고 총건수 초과를 완료로 처리하지 않습니다.
현재 API가 돌려준 총건수 또는 빈 마지막 페이지를 기준으로 완료를 판정합니다.
순회 도중 데이터가 바뀌는 경우의 스냅샷 일관성을 보장하지는 않습니다.
최신 재수집은 기존 data/collection을 별도 이름으로 보관한 뒤 새로 실행합니다.
조회 조건이 달라진 캐시와 새 페이지는 섞지 않습니다.

동명 제도는 서로 다른 지역 사업일 수 있습니다. 중복 후보를 자동 병합하지 않습니다.
이름 미매칭은 실제 누락을 의미하지 않으며 명칭 차이·범위 차이를 수동 확인해야 합니다.
API 내용과 원문·자격 조건의 정확성 검증은 별도입니다.
XML 응답은 평탄 필드와 원문·중첩 구조를 함께 저장합니다. 이전 파서로 수집한 최초 목록 캐시는 원문·중첩 구조가 없으며 추출 행과 평탄 필드만 있습니다.

오프라인 수집 로직 검증:

    python scripts/test_collection.py
