# 오로르 기준 DB 코드 컨벤션

사용자 지시: 2026-11-27. 기준 자료는 오로르 [AGENTS.md](https://github.com/orca305/AURORE/blob/main/AGENTS.md), [DB 문서](https://github.com/orca305/AURORE/blob/main/docs/DATABASE.md), [실제 Prisma 스키마](https://github.com/orca305/AURORE/blob/main/backend/prisma/schema.prisma)다. 오로르 기능이나 변경 승인 범위를 베네핏에 복사하지 않고 명명·공통코드·일시·삭제 규칙을 적용한다.

## 이름

- 테이블/컬럼은 영문 snake_case. 테이블은 의미가 드러나게, 컬럼은 관례적인 약어로 작성한다.
- 테이블 예: `benefit`, `benefit_ver`, `src_record`, `src_snapshot`, `doc_chunk`, `question`, `rule_evidence`, `emb_model`.
- 컬럼 예: `nm`, `cd`, `cont`, `seq`, `dttm`, `dt`, `rgst`, `upt`, `stat`, `del`, `prnt`.
- 참거짓은 Boolean `*_yn`: `current_yn`, `optional_yn`, `del_yn`. 문자열 Y/N으로 변환하지 않는다.
- 상태는 `stat_cd`, 순서는 `sort_seq`, 부모는 `prnt_id`, 관계 키는 `benefit_ver_id`, `src_snapshot_id`처럼 대상이 드러나게 쓴다.
- PK/FK/유일/검사/일반 인덱스는 `pk_`/`fk_`/`uq_`/`ck_`/`idx_` 접두사를 쓴다. PostgreSQL 이름 길이 한도를 넘지 않도록 의미 부분과 짧은 식별 해시를 조합한다.
- 범용적으로 짧게 만드는 규칙은 아니다. 처음 만든 `prgm`, `src_snap`, `emb_mdl`, `stts`, `is_*`, `*_at`는 오로르 기준에 맞춰 개정했다.

이전→최종 이름은 `database/name_map.json`, 이미 적재한 첫 약칭→오로르 규칙 변경은 `database/aurore_name_map.json`에 기록한다. 원천 JSON 키와 공개 API JSON 키는 원래 값을 보존한다.

## 일시·이력

- 일시는 TIMESTAMPTZ와 `*_dttm`, 기준일은 DATE와 `*_dt`를 사용한다.
- 모든 테이블에 `rgst_id`, `rgst_dttm`, `upt_id`, `upt_dttm`, `del_yn`, `del_dttm`, `del_id`를 둔다.
- 새 감사 시각은 초 단위로 기록한다. 이미 수집한 원천 시각은 컬럼 정밀도를 줄이지 않고 원본 정밀도를 보존했다. JSON 메타데이터 역시 변경하지 않는다.
- 회원 테이블이 없으므로 감사 주체 BIGINT는 NULL을 허용한다. 실제 사용자가 없는 상황에서 가짜 회원 ID를 만들지 않는다.
- 기존 제도/원문/조건 UUID·조각 ID는 관계 보존을 위해 유지한다. 오로르도 테이블별 BigInt/UUID를 구분하므로 모든 PK를 일괄 타입 변환하지 않는다. 새 공통코드 ID는 BIGINT identity다.

## 공통코드

- 자기참조 단일 `cmmn_cd`와 별도 `cmmn_cd_hist`를 사용한다.
- `prnt_cd_id`, `cd`, `cd_nm`, `cd_desc`, `node_type_cd`, `sort_seq`, `use_yn`, `sys_yn`으로 그룹과 항목을 관리한다.
- 상태·유형·대상 역할·비교 연산 등에 코드 그룹을 두고 코드 변경은 이전/이후 데이터를 이력에 남긴다.
- 비즈니스/API에는 내부 공통코드 PK 숫자 대신 의미 있는 문자열을 쓴다. 기존 `draft`, `approved` 같은 코드와 원천 코드의 대소문자는 보존했다. 오로르도 공통코드 FK와 의미형 문자열 컬럼을 용도별로 사용한다.
- DB 트리거가 미등록/사용 중지 코드를 새로 넣는 것을 검사한다. 실행 가능한 연산의 추가는 코드 정의만 바꾸는 것으로 끝나지 않으며 평가 로직·검증도 필요하다.

## 삭제·조회

- 일반 업무 삭제는 `UPDATE ... SET del_yn=true`다. `del_dttm`은 감사 트리거가 채우고, 확인된 처리 주체가 있을 때 `del_id`를 지정한다.
- SQL DELETE는 DB 트리거가 거절한다. 물리 FK 연쇄 삭제를 쓰지 않는다.
- 부모 삭제는 관계를 따라 하위 행도 소프트 삭제한다. 자기참조 트리는 재귀 집합으로 처리한다. 대규모 원천 전체 삭제는 현재 행 트리거보다 배치 처리가 적절하므로 별도 작업으로 구현한다.
- 공개 조회는 `active_src_snapshot`, `current_benefit_ver`, `current_doc_chunk`, `active_rule_set`를 사용해 삭제된 부모/자료를 제외한다. 승인 규칙의 일부 노드·근거·질문이 삭제되면 그 규칙 집합 전체를 적용 대상에서 제외한다.
- 부모를 복구한다고 자식을 자동 복구하지 않는다. 각 항목의 이전 삭제 이유를 검토해야 한다.
- 원문과 승인 규칙의 내용은 계속 불변이다. 소프트 삭제·감사 필드 변경만 예외이며 내용 수정은 새 버전으로 남긴다.
- 개인정보 파기는 별도 정책이다. 현재 DB에 브라우저 개인정보를 적재하지 않는다.

## 적용 범위와 검증

SQL·PostgreSQL 접근 코드·스키마 테스트·문서를 같은 명칭으로 변경했다. Prisma 자체를 베네핏에 도입하거나 Python 서버를 NestJS로 교체하지는 않는다. Python/JavaScript는 현재 언어의 스타일을 유지한다.

`004_aurore_names.sql`은 이미 적재한 테이블/컬럼을 ALTER RENAME 한다. `005_aurore_lifecycle.sql`은 공통코드/감사/소프트 삭제, `006_object_names.sql`은 제약·인덱스 이름을 정리한다. 기존 DB 적용은 `scripts/apply_pg_conventions.py`가 한 트랜잭션으로 처리한다. 새 DB 초기 적재는 001→003→005→006을 적용하며 004를 실행하지 않는다. 벡터 002는 모델 선택 후 별도 적용한다.

새 이름의 DDL·공통코드 이력·잘못된 코드 거절·DELETE 거절·부모 소프트 삭제·하위 검색 제외를 합성 데이터로 검증했다. 실제 PostgreSQL에서도 한 제도를 소프트 삭제해 하위 비노출을 확인한 뒤 전체 테스트 변경을 롤백했다. 실데이터는 원본과 전량 대조하고 새 백업을 복원 검증한다.
