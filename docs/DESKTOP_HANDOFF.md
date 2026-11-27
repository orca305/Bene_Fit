# 데스크탑 인수인계 · 최신 시작점

기준일: **2026-11-27 / Asia/Seoul**. 이 문서를 먼저 읽는다. HANDOFF.md는 시간순 기록이므로 과거의 ‘SQLite 사용 중’, ‘BGE 확정’, ‘임베딩 실행 중’ 문구를 현재 상태로 해석하지 않는다.

## 현재 상태와 사용자 결정

- 저장소 `https://github.com/orca305/Bene_Fit.git`, 브랜치 main, 권장 경로 `C:\dev\Bene_Fit`.
- 실제 웹 조회 DB는 **PostgreSQL 17.12**다. Docker/psycopg를 사용한다. 기존 SQLite/JSONL은 검증·재현용으로 보존했다.
- 웹은 Python 표준 HTTP 서버 + 정적 HTML/CSS/JavaScript 프로토타입이다. Next.js/FastAPI/Prisma로 구현됐다고 가정하지 않는다.
- 오로르의 실제 문서/Prisma 스키마를 확인해 DB 명명·공통코드·감사·소프트 삭제 규칙을 적용했다. 현재 기본 테이블은 20개다.
- 첫 화면에 제도 목록을 나열하지 않는다. 본인/자녀/부모님/가구와 지원 분야를 고르고 필요한 질문을 하나씩 받는다. 개인정보 질문은 전부 선택이며 건너뛰기·저장 없이 탐색 가능하다.
- 가족 답변은 브라우저에서 처리한다. 사용자가 저장을 선택할 때만 AES-GCM/PBKDF2로 암호화한다. 서버 회원/가족 프로필/기기 간 동기화는 미구현이다.
- 상세에 원문·출처·확인 시각을 표시한다. 틸 그린 임시 디자인이며 본격 디자인 개편은 보류했다.
- **노트북 임베딩은 중단했고 생성 벡터를 삭제했다.** 모델 등록/벡터/승인 자격 규칙은 0개다. 웹은 키워드/관련성 방식으로 동작한다. 의미 검색은 새 모델 연결 대기를 반환하고 UI가 폴백을 명시한다.
- 운영 PC는 **RTX 4070 12GB / RAM 32GB**다. 새 모델은 데스크탑에서 사용자와 함께 비교·선택한다. BGE CPU 설정을 자동 실행하지 않는다.
- 오로르 모델 교체는 오로르에서 나중에 다룬다. 이 프로젝트에서 오로르 코드·DB·환경을 바꾸지 않는다.
- 부모/아이/신청자/보호자/제도상 가구를 구분한다. 미응답은 탈락이 아니다. 원천 코드 Y/null·키워드·추출 수치만으로 자격을 확정하지 않는다.
- 주민번호·진단명·정확한 생년월일·소득/자산 금액을 필수로 받지 않는다. 디자인보다 데이터·조건 연결을 우선한다.
- 사이트는 ChatGPT 내부가 아닌 외부 브라우저로 연다. 자동 열기가 정책에 막히면 링크를 제공한다.

## Git 외에 반드시 가져갈 파일

로컬에 **`C:\dev\Bene_Fit\data\desktop-transfer`** 폴더를 준비했다. 이 폴더는 Git 제외다. **push/pull만으로 DB나 비밀번호가 전달되지 않는다.**

| 파일 | 내용 |
|---|---|
| Bene_Fit-desktop-data.zip | data/migration/bene_fit_pg.dump, 검증 보고서, 수집 원본·SQLite·JSONL·조건 초안, 모델 비교 표본/수치 |
| private/.env | 공공 API 키. 필요할 때만 본인 기기끼리 복사 |
| private/.env.postgres | 로컬 DB 접속 설정·비밀번호 |
| manifest.json | 파일 크기·SHA-256·생성 시각·코드 커밋 확인용 |
| README.txt | 별도 복사 요약 |

이 폴더는 비공개 자료다. 저장소나 공유 링크에 올리지 않는다. env 파일은 일반 UTF-8 평문이며 암호화 파일이 아니다. AnySign4PC 표시는 Windows 연결 프로그램 문제였다. 브라우저 보관 암호와 API/DB 설정은 별개다.

가상환경·모델 가중치/캐시·node_modules·로그·Docker 볼륨 파일은 제외했다. 새 PC에서 패키지를 다시 설치한다. 브라우저의 암호화 가족 정보는 이 백업에 포함하지 않으며 자동 동기화도 없다. 보관 암호는 어시스턴트/서버가 보관하지 않는다.

## 데스크탑 복원 절차

### 1. 코드와 자료 준비

```powershell
git clone https://github.com/orca305/Bene_Fit.git C:\dev\Bene_Fit
Set-Location C:\dev\Bene_Fit
```

이미 저장소가 있으면 먼저 git status --short를 확인하고, 수정 사항이 없는 상태에서 git pull --ff-only로 받는다. 기존 작업에 reset --hard·강제 push를 사용하지 않는다.

별도 zip은 **프로젝트 루트**에 푼다. 내부 경로는 data/...로 시작한다. private의 .env와 .env.postgres도 필요한 경우 루트로 복사한다. 기존 파일은 확인 없이 덮어쓰지 않는다.

API를 다시 호출하지 않고 기존 DB만 실행할 때는 API .env가 없어도 된다. DB .env.postgres는 필요하다. 새로 만들려면 config/postgres.env.example을 참고하고 **DB 볼륨을 처음 만들기 전에** 비밀번호를 정한다.

### 2. 최소 실행 환경

검증 버전: Python **3.13.15**, Node.js **24.22.2**, psycopg **3.3.9**. Docker Desktop을 기동한다.

```powershell
py -3.13 -m venv .venv-embedding
.venv-embedding\Scripts\python.exe -m pip install -r requirements-db.txt
docker volume create bene-fit-pg-data
docker compose -f compose.postgres.yaml up -d
docker compose -f compose.postgres.yaml ps
```

DB 접속은 127.0.0.1:55432, DB/계정은 bene_fit, 컨테이너 bene-fit-pg, 볼륨 bene-fit-pg-data다. Compose에서 컨테이너 내부 PGPORT를 5432로 고정한다.

기존에 같은 DB/볼륨이 있으면 먼저 확인한다. 다른 프로젝트나 이전 데이터를 지워서 빈 상태로 만들지 않고 별도 DB/볼륨을 준비한다.

### 3. 빈 DB에 백업 복원

DB가 healthy/접속 가능해진 뒤 **테이블이 없는 DB**에 복원한다.

```powershell
docker cp data/migration/bene_fit_pg.dump bene-fit-pg:/tmp/bene_fit.dump
docker exec --env PGHOST=/run/postgresql bene-fit-pg pg_restore --username bene_fit --dbname bene_fit --exit-on-error --no-owner --no-acl /tmp/bene_fit.dump
```

덤프에는 최종 테이블·데이터·함수·뷰·트리거가 모두 있다. **복원 전후에 001/003/005/006이나 migrate_postgres.py, apply_pg_conventions.py를 다시 적용하지 않는다.** 004는 이미 적재한 첫 약칭 DB를 개정하는 과거 업그레이드다.

### 4. 검증과 웹 실행

```powershell
.venv-embedding\Scripts\python.exe scripts/migrate_postgres.py --verify
.venv-embedding\Scripts\python.exe scripts/test_pg_catalog.py
.venv-embedding\Scripts\python.exe scripts/serve_catalog.py
```

외부 브라우저에서 http://127.0.0.1:8765 를 연다. /progress는 벡터 삭제·모델 선택 대기여야 한다. 요청 로그는 남기지 않는다.

검증 명령은 SQLite/collection 원본과 대조한다. 이번 zip에는 그 자료도 포함했다. 백업만 가져오면 대조 파일이 없어 검사가 실패할 수 있다. 최소 웹 실행에는 Torch/임베딩 모델이 필요 없다. 환경 이름 .venv-embedding은 기존 경로를 유지한 것이다.

## DB 인수 기준

| 데이터 | 기준 수 |
|---|---:|
| 기본 테이블 | 20 |
| benefit / benefit_ver / doc | 각각 16,196 |
| src_record / src_snapshot | 각각 16,630 |
| doc_chunk | 88,458 |
| emb_input | 고유 입력 문자열 77,558개 — 벡터 아님 |
| rule_set | 16,196개 초안 |
| rule_node | 117,276 = 미확정 루트 16,196 + 조건 초안 101,080 |
| rule_evidence | 101,109 |
| question | 공개 질문 정의 163 |
| cmmn_cd / cmmn_cd_hist | 각각 61 |
| fact_def / rule_question / emb_model / 승인 규칙 | 0 |

emb_vector는 아직 생성하지 않았다. 마이홈 355행/LH 182행은 snapshot 배열에 모두 보존했지만 제도 매핑 미검증이므로 aply_round는 0개다. 최근 수집·원문 표시가 현재 접수/전국 적용을 뜻하지 않는다.

## 임베딩 상태와 다음 작업

과거 모델은 BGE-M3 1024차원, CPU/float32/4스레드/배치2였다. 사용자가 벡터 삭제를 요청했고 약 2,448개의 생성 벡터와 비교 벡터를 삭제했다. config/embedding.json은 **과거 CPU 시험 설정**이다.

시험 환경은 Torch 2.15.0+cpu, sentence-transformers 6.3.0이다. eval/embedding-runtime-lock.txt는 과거 실험 기록이며 **CUDA 환경 설치용 lock 파일이 아니다.**

198개 복지 근거 조각·32개 합성 질문 비교에서 첫 정답 근거 BGE 28/32, KURE 30/32, top5 둘 다 32/32였다. 일부 상세·불완전한 정답 주석이므로 전체 검색 품질로 일반화하지 않는다. 평가셋과 수치는 zip에 포함했다. KURE 가중치는 삭제했고 노트북 BGE 가중치는 이전에서 제외했다.

데스크탑에서는:

1. DB 복원과 웹 실행부터 확인한다.
2. nvidia-smi로 실제 GPU/드라이버를 확인한다. 공식 설치 안내에 맞춰 GPU용 PyTorch 환경을 준비하고 torch.cuda.is_available()을 확인한다. CPU lock을 그대로 설치하지 않는다.
3. 사용자와 비교 모델을 정한다. BGE 기준선, KURE-v3, Qwen3-Embedding-4B 등이 논의됐지만 운영 모델은 미확정이다. 12GB에서 실제 메모리·입력 길이·배치·정밀도를 측정한다.
4. 같은 입력·질문·근거로 소량 비교하고 결과를 보여준 뒤 선택한다. 8B FP16을 12GB에 그대로 올릴 수 있다고 가정하지 않는다.
5. pgvector가 있는 PostgreSQL 17 환경을 별도로 준비·검증한다. 현재 postgres:17-alpine에는 pgvector가 없다. 필요하면 새 확장 지원 환경에 덤프를 복원해 검증한다.
6. 002_vectors.sql을 적용하고 revision/차원/프롬프트/정규화/출력 설정을 emb_model에 등록한다. 서로 다른 모델의 벡터는 섞지 않는다.
7. **PG용** 생성·재개·검증·검색을 구현한다. embedding_search.py / refresh_search.py / benchmark_embedding.py는 과거 SQLite/CPU 경로라 config만 바꾸고 전체 실행하면 안 된다. Qwen 비교도 별도 어댑터가 필요하다.
8. 단계별 진행률과 실제 근거를 사용자에게 보여주며 전체 생성→품질 평가→활성 모델 전환을 진행한다.

## 임베딩 외 남은 개발

- **PG 증분 갱신:** 현재 importer는 최초 이전 전용이며 기존 DB 재적재를 거절한다. 수집 갱신→새 버전/조각/초안→변경 입력만 생성하는 PG 경로가 필요하다.
- **규칙 연결:** 조건은 전부 미승인/대상 불명이고 fact/질문 매핑도 비어 있다. 공식 원문·단위·대상·AND/OR·예외·기간을 검토해야 한다.
- **조건 계산:** 확인한 조건 충족/미충족/정보 부족/기관 확인 필요를 구분한다. 일부 충족을 전체 자격으로 승격하지 않는다.
- **수집:** 중앙부처 상세 88/461개, 지자체 상세 10개 표본. 나머지 중앙부처 373개는 HTTP429 일일 한도로 보류했다. 쿼터·재개 상태 확인 후 진행한다.
- **갱신 캐시:** collect_catalogs.py는 페이지 재개 캐시다. 반복 실행이 최신 갱신을 뜻하지 않으므로 새 수집 배치/캐시 정책이 필요하다.
- **시점·지역:** 과거 기준 안내가 포함돼 있으며 미검증 기간/지역을 임의로 확정하지 않는다.
- **UI:** 본격 디자인과 브라우저/모바일 시각 검증은 보류했다. CUA/node_repl은 kernel assets 오류가 있었고 최근 검증은 HTTP/Node 중심이다.
- **운영:** 서버 회원·공개 배포·프로필 동기화는 미구현이다. 로컬 DB 소유자 계정을 공개 서비스 계정으로 쓰지 않는다.

## 파일과 검증 안내

| 파일 | 역할 |
|---|---|
| AGENTS.md / docs/CONVENTIONS.md | 다음 작업 규칙과 오로르 기준 컨벤션 |
| docs/DATABASE.md / database/001..006 | ERD·DDL·과거 업그레이드·관리 규칙 |
| compose.postgres.yaml / pg_db.py / requirements-db.txt | DB 실행·접속 |
| migrate_postgres.py / apply_pg_conventions.py | 완료된 최초 이전·컨벤션 변경 |
| pg_catalog.py / serve_catalog.py | 현재 PG 읽기 API·웹 |
| web/guided.js / profile_crypto.js | 선택 질문·가족 분리·브라우저 암호화 |
| collect_catalogs.py / collect_central_details.py | 기존 API 수집·재개 |
| catalog.py / build_knowledge.py / build_condition_drafts.py | 기존 SQLite 가공·검증 |
| docs/POSTGRES_OPERATIONS.md | DB 실행·백업 상세 |
| docs/EMBEDDING_COMPARISON_RESULTS.md | 과거 CPU 비교와 제한 |

위 Python 파일은 scripts/ 아래에 있다. 전체 기록은 docs/HANDOFF.md를 참고한다.

완료한 검증: 네이티브 PG DDL, 정규화/메타데이터·스냅샷 해시·조각/위치·조건 payload·근거·주거 원본 전량 대조, HTTP 목록/상세/민감 파일 차단/모델 대기, 질문·가족 암호화, 공통코드/소프트 삭제. 최종 덤프를 별도 DB에 복원해 다시 대조했고 테스트 DB는 제거했다. 실데이터 소프트 삭제 검사는 롤백했다.

다음 채팅 시작 문구:

> C:\dev\Bene_Fit의 AGENTS.md와 docs/DESKTOP_HANDOFF.md를 읽고 이어서 작업해줘. 먼저 백업 복원과 PostgreSQL 웹 실행을 확인하자. 임베딩은 자동 시작하지 말고 RTX 4070 12GB에서 비교 모델과 GPU 환경부터 같이 확인하자.
