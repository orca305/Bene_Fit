# PostgreSQL 약칭 스키마

설계·ERD·테이블 명세·개인정보 경계·이전 계획: [DATABASE.md](../docs/DATABASE.md).

이 파일들은 새 전용 데이터베이스에 한 번 적용한다. 기존 SQLite 데이터나 운영 DB에 덮어쓰는 스크립트가 아니며, 설치·접속 비밀번호를 포함하지 않는다.

```powershell
# 접속 정보는 별도로 설정한다. 모든 오류에서 중단한다.
psql -X -v ON_ERROR_STOP=1 -f database/001_core.sql
psql -X -v ON_ERROR_STOP=1 -f database/003_rule_review.sql
psql -X -v ON_ERROR_STOP=1 -f database/005_aurore_lifecycle.sql
psql -X -v ON_ERROR_STOP=1 -f database/006_object_names.sql
# 새 모델과 pgvector 확장 환경을 정한 뒤에만 적용:
psql -X -v ON_ERROR_STOP=1 -f database/002_vectors.sql
```

- `001_core.sql`: 공공데이터·버전·회차·문서·조건·질문·모델 메타데이터 18개 테이블.
- `003_rule_review.sql`: 승인 시 구조·타입·질문 대상·인용문 검사, 승인본·원문 불변 처리.
- `002_vectors.sql`: 선택 pgvector 확장과 모델별 벡터 테이블. 아직 모델은 등록하지 않는다.

PostgreSQL 17.12에 실제 적재·검증했고 웹 읽기 경로를 전환했다. [실행·이전·백업 안내](../docs/POSTGRES_OPERATIONS.md)를 따른다. 기존 SQLite는 보관하며 수집기·기존 refresh_search.py는 아직 SQLite 기반이다. 새 PG 증분 적재는 후속 작업이다.

최종 컨벤션은 [CONVENTIONS.md](../docs/CONVENTIONS.md), 원래 이름 대응은 [name_map.json](name_map.json), 이미 적재한 약칭을 바꾸는 규칙은 [aurore_name_map.json](aurore_name_map.json)이다. 테이블은 의미가 드러나게 쓰고 컬럼은 *_yn, *_dttm, *_dt, stat_cd, rgst/upt/del 등 오로르의 관례적인 약어를 따른다.

현재 코어 18개와 공통코드/이력 2개를 사용한다. 새 DB에는 001→003→005→006을 적용한다. 004는 첫 약칭으로 이미 적재한 DB의 명칭 변경 전용이다. 선택 002는 새 모델을 정한 뒤 적용한다.
