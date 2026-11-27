# Bene_Fit 작업 규칙

- 새 PC에서 이어갈 때는 docs/DESKTOP_HANDOFF.md를 먼저 읽는다. docs/HANDOFF.md의 과거 상태를 최신 상태로 오인하지 않는다.
- 사용자 지시와 [설계 결정](docs/DECISIONS.md)을 따른다. 오로르 코드를 참고할 때 오로르 프로젝트의 작업 승인 범위를 베네핏에 적용하지 않는다.
- DB 컨벤션은 [CONVENTIONS.md](docs/CONVENTIONS.md)를 따른다. 오로르의 실제 DB 문서와 스키마가 참고 기준이다.
- 테이블/컬럼은 snake_case, 의미가 드러나는 테이블명과 관례적인 컬럼 약어를 사용한다. Boolean은 *_yn, 일시는 *_dttm, 날짜는 *_dt, 상태는 stat_cd다.
- 공통코드는 자기참조 cmmn_cd와 cmmn_cd_hist로 관리한다. API에는 의미형 코드를 전달한다.
- 업무 삭제는 del_yn/del_dttm/del_id를 갱신한다. SQL DELETE나 물리 ON DELETE CASCADE를 사용하지 않는다. 공개 조회에서 삭제된 부모와 자식을 제외한다. 개인정보 파기는 별도 정책이다.
- 원문·가공 조각·규칙·임베딩을 분리한다. 원문과 승인 규칙의 내용은 새 버전으로 남긴다. 미검토 초안으로 자격을 확정하지 않는다.
- 개인정보는 현재 선택형 브라우저 암호화 보관을 유지한다. 개인 답변·API 키·DB 비밀번호를 코드/Git/임베딩에 넣지 않는다.
- 기존 SQLite는 이전 검증 자료로 보존한다. 웹은 PostgreSQL을 읽는다. 현재 벡터는 삭제 상태이며 데스크탑에서 새 모델을 정하기 전 임베딩을 자동 재시작하지 않는다.
- DB 변경 시 DDL·마이그레이션·접근 코드·문서를 함께 갱신한다. 스키마 검사는 test_postgres_schema.cjs, 실제 데이터 대조는 migrate_postgres.py --verify, 읽기 API는 test_pg_catalog.py로 확인한다. 테스트와 실데이터의 작업 범위를 구분한다.
