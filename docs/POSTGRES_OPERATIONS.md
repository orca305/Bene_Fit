# PostgreSQL 실행·이전 기록

2026-11-27: SQLite 공공데이터를 약칭 스키마로 적재하고 웹 읽기를 PostgreSQL로 전환했다. 기존 SQLite·JSONL·수집 파일은 보존했다. 개인정보를 서버로 이전하지 않았고 새 임베딩을 생성하지 않았다.

## 로컬 실행

- PostgreSQL: Docker `postgres:17-alpine`, 실제 검증 버전 17.12
- 컨테이너: `bene-fit-pg`, 볼륨: `bene-fit-pg-data`
- 접속: `127.0.0.1:55432`, DB/계정: `bene_fit`
- 접속 설정·비밀번호: 프로젝트 루트의 `.env.postgres`에 평문 보관. Git 제외. 기존 API `.env`와 별개다.
- Compose는 컨테이너 내부 PGPORT를 5432로 고정하고 호스트의 55432에 연결한다.

```powershell
docker volume create bene-fit-pg-data
docker compose -f compose.postgres.yaml up -d
.venv-embedding\Scripts\python.exe -m pip install -r requirements-db.txt
.venv-embedding\Scripts\python.exe scripts/serve_catalog.py
```

새 PC에서는 먼저 `config/postgres.env.example`을 `.env.postgres`로 복사하고 로컬 비밀번호를 정한다. 이미 사용하는 `.env.postgres`를 덮어쓰지 않는다. DB는 현재 로컬 개발 전용 계정을 사용한다. 공개 서비스 배포 전에는 수집·읽기·검토 계정 권한을 구분한다.

## 적재 및 검증

```powershell
# 빈 DB에 처음 한 번만 실행. 스키마도 없다면 001/003을 적용한다.
.venv-embedding\Scripts\python.exe scripts/migrate_postgres.py
# 이미 적재된 DB는 변경하지 않고 전체 대조만 실행:
.venv-embedding\Scripts\python.exe scripts/migrate_postgres.py --verify
.venv-embedding\Scripts\python.exe scripts/test_pg_catalog.py
```

적재는 한 트랜잭션이며 실패하면 데이터 적재를 롤백한다. 이미 원천 레코드가 있는 DB에 다시 전체 적재하려 하면 중단한다. 이름이 같은 기존 스키마를 자동 삭제하지 않는다. 이 명령은 최초 이전용이며 향후 증분 적재용 upsert는 후속이다. 기존 refresh_search.py는 SQLite 기반 후속 처리 명령이므로 PostgreSQL 갱신 명령으로 사용하지 않는다.

| 데이터 | 실제 적재 수 |
|---|---:|
| `data_src` | 5 |
| `ingest_run` | 5 |
| `benefit` / `benefit_ver` / `doc` | 각각 16,196 |
| `src_record` / `src_snapshot` | 각각 16,630 |
| `benefit_ver_src` | 16,196 |
| `doc_chunk` | 88,458 |
| `emb_input` | 77,558개 고유 입력 문자열, 벡터 아님 |
| `rule_set` | 16,196개 초안 |
| `rule_node` | 117,276 = 미확정 루트 16,196 + 기존 조건 초안 101,080 |
| `rule_evidence` | 101,109 |
| `question` | 163개 공개 질문 정의 |

마이홈 원본 355행, LH 원본 182행은 원천 키로 묶은 snapshot 배열에 모두 보존했다. 주거 공고의 제도 매핑은 검증 전이므로 임의의 application round를 만들지 않았다. 질문은 현재 UI에서 공개 정의만 옮겼으며 fact/규칙 연결은 미검토 상태다. 개인 답변·브라우저 저장소를 읽거나 적재하지 않았다. 모델 등록·승인 규칙은 0개다.

새 ID는 기존 원천/문서 ID에서 결정적으로 UUID를 만들고 원래 ID를 old_rec_id·old_doc_id에 보존했다. 조각 ID와 모든 원문 위치·미검토 조건 payload를 유지했다. 정규화 항목/메타데이터 전체, 스냅샷 해시 전체, 조각 본문/위치/근거 전체, 조건 payload 전체, 주거 원본 행 전체를 대조했다.

보고서는 `data/migration/postgres-report.json`, 복원 검증은 `data/migration/restore-report.json`이다. `ingest_run.ds_nm=sqlite-import-v1`는 이번 이전 실행을 뜻한다. 이전 수집 시각과 원천 메타데이터는 snapshot 및 meta_json에 보존한다.

## 집 데스크탑으로 가져가기

백업 파일: **`data/migration/bene_fit_pg.dump`**. 약 65MiB이며 사용자 비밀번호·브라우저 개인정보를 포함하지 않는 DB 데이터 백업이다. 오로르 컨벤션과 공통코드/이력을 포함한 최종 스키마로 갱신했다. 별도 `bene_fit_restore_check` DB에 복원해 전량 대조를 통과했고 테스트 DB는 제거했다.

코드와 이 백업을 별도로 가져간다. `data/`와 `.env.postgres`는 Git에 올라가지 않는다. 새 PC의 DB를 **비어 있는 상태로** 기동한 후 다음처럼 복원한다. 이때 migrate_postgres.py나 001_core.sql을 먼저 실행하지 않는다. 백업에 스키마·제약·데이터가 들어 있다.

```powershell
docker cp data/migration/bene_fit_pg.dump bene-fit-pg:/tmp/bene_fit.dump
docker exec --env PGHOST=/run/postgresql bene-fit-pg pg_restore --username bene_fit --dbname bene_fit --exit-on-error --no-owner --no-acl /tmp/bene_fit.dump
```

원본 SQLite와 비교하는 `--verify`를 새 PC에서도 실행하려면 기존 `data/normalized`, `data/knowledge`, `data/collection`도 가져간다. DB를 실행하는 데만 필요한 데이터는 덤프에 포함돼 있다. 개발 환경 `.venv-embedding`은 PC 간 복사하지 않고 다시 설치한다. 임베딩 모델 선택·GPU 환경과 생성 코드는 그 뒤에 연결한다.

새 백업을 만들 때:

```powershell
docker exec --env PGHOST=/run/postgresql bene-fit-pg pg_dump --username bene_fit --dbname bene_fit --format custom --no-owner --no-acl --file /tmp/bene_fit.dump
docker cp bene-fit-pg:/tmp/bene_fit.dump data/migration/bene_fit_pg.dump
```

벡터 확장 002_vectors.sql은 적용하지 않았다. 새 모델을 정한 뒤 모델/차원별 저장과 검색을 연결한다. 그 전까지 웹은 의미 검색 준비 상태를 표시하고 키워드 방식으로 동작한다.

## 오로르 컨벤션 적용

기준은 [CONVENTIONS.md](CONVENTIONS.md)다. 기존에 적재한 첫 약칭 스키마는 apply_pg_conventions.py로 한 번만 변경했다. src_snap/prgm/is_*/ *_at 등은 src_snapshot/benefit/*_yn/*_dttm 형태로 바뀌었다. 기존 행 ID와 원문 JSON·조건 payload는 보존했다. 공통코드와 이력은 각각 cmmn_cd/cmmn_cd_hist이며 현재 각각 61행이다. 삭제는 del_yn/del_dttm/del_id와 하위 소프트 삭제를 사용한다. 공개 읽기는 current_benefit_ver/current_doc_chunk 등 활성 뷰를 사용한다.
