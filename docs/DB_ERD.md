# PostgreSQL DB 구성도 · 실제 반영 기준

기준일: 2026-11-27. PostgreSQL 17.12의 실제 카탈로그에서 테이블·PK·FK를 읽어 작성했다. **현재 기본 테이블 20개**이며 아래에는 관계 키와 주요 컬럼을 표시한다. 전체 컬럼·제약은 [SQL](../database/001_core.sql)과 [관리 규칙](../database/005_aurore_lifecycle.sql)을 따른다.

## 전체 물리 ERD

```mermaid
erDiagram
    aply_round {
        uuid id PK
        uuid benefit_id FK
        uuid benefit_ver_id FK
        uuid src_record_id FK
        uuid src_snapshot_id FK
        text rnd_key
        int rev_no
        timestamptz aply_start_dttm
        timestamptz aply_end_dttm
        boolean current_yn
    }
    benefit {
        uuid id PK
    }
    benefit_ver {
        uuid id PK
        uuid benefit_id FK
        text cont_hash
        text nm
        date eff_start_dt
        date eff_end_dt
        boolean current_yn
    }
    benefit_ver_src {
        uuid benefit_ver_id PK, FK
        uuid src_snapshot_id PK, FK
    }
    cmmn_cd {
        bigint id PK
        bigint prnt_cd_id FK
        varchar cd
        varchar cd_nm
        varchar node_type_cd
        boolean use_yn
    }
    cmmn_cd_hist {
        bigint id PK
        uuid request_id
        bigint cmmn_cd_id FK
        varchar act_type_cd
    }
    data_src {
        text cd PK
        text nm
        boolean use_yn
    }
    doc {
        uuid id PK
        uuid benefit_ver_id FK
        uuid aply_round_id FK
        uuid src_snapshot_id FK
        text old_doc_id
        text cont_hash
    }
    doc_chunk {
        text id PK
        uuid doc_id FK
        text fld_nm
        int start_pos
        int end_pos
        text emb_input_hash FK
    }
    emb_input {
        text input_hash PK
    }
    emb_model {
        uuid id PK
        text model_nm
        text model_rev
        int dim_cnt
        boolean act_yn
    }
    fact_def {
        text cd PK
        text value_type_cd
        text unit_cd
        boolean compare_yn
    }
    ingest_run {
        uuid id PK
        text src_cd FK
        text stat_cd
    }
    question {
        text id PK
        int rev_no
        text fact_cd FK
        text subj_role_cd
        text qstn_txt
        boolean optional_yn
    }
    rule_evidence {
        uuid rule_node_id PK, FK
        uuid rule_set_id FK
        text chunk_id PK, FK
        int start_pos PK
        int end_pos
    }
    rule_node {
        uuid id PK
        uuid rule_set_id FK
        uuid prnt_id FK
        text type_cd
        text fact_cd FK
        text subj_role_cd
        text op_cd
        jsonb cmp_val_json
    }
    rule_question {
        uuid rule_node_id PK, FK
        uuid rule_set_id FK
        text question_id PK, FK
        text fact_cd FK
        text subj_role_cd FK
    }
    rule_set {
        uuid id PK
        uuid benefit_ver_id FK
        uuid aply_round_id FK
        int rev_no
        text stat_cd
        text coverage_cd
        date eff_start_dt
        date eff_end_dt
    }
    src_record {
        uuid id PK
        text src_cd FK
        text ext_id
        text type_cd
        uuid benefit_id FK
        text old_rec_id
    }
    src_snapshot {
        uuid id PK
        uuid src_record_id FK
        uuid run_id FK
        text cont_hash
    }
    benefit ||--o{ aply_round : benefit_id
    benefit_ver ||--o{ aply_round : benefit_ver_id_benefit_id
    src_record ||--o{ aply_round : src_record_id
    src_snapshot ||--o{ aply_round : src_snapshot_id
    benefit ||--o{ benefit_ver : benefit_id
    benefit_ver ||--o{ benefit_ver_src : benefit_ver_id
    src_snapshot ||--o{ benefit_ver_src : src_snapshot_id
    cmmn_cd o|--o{ cmmn_cd : prnt_cd_id
    cmmn_cd ||--o{ cmmn_cd_hist : cmmn_cd_id
    aply_round o|--o{ doc : aply_round_id_benefit_ver_id
    benefit_ver ||--o{ doc : benefit_ver_id
    src_snapshot ||--o{ doc : src_snapshot_id
    doc ||--o{ doc_chunk : doc_id
    emb_input o|--o{ doc_chunk : emb_input_hash
    data_src ||--o{ ingest_run : src_cd
    fact_def o|--o{ question : fact_cd
    doc_chunk ||--o{ rule_evidence : chunk_id
    rule_node ||--o{ rule_evidence : rule_node_id_rule_set_id
    fact_def o|--o{ rule_node : fact_cd
    rule_node o|--o{ rule_node : prnt_id_rule_set_id
    rule_set ||--o{ rule_node : rule_set_id
    question ||--o{ rule_question : question_id_fact_cd_subj_role_cd
    rule_node ||--o{ rule_question : rule_node_id_rule_set_id_fact_cd_subj_role_cd
    aply_round o|--o{ rule_set : aply_round_id_benefit_ver_id
    benefit_ver ||--o{ rule_set : benefit_ver_id
    benefit o|--o{ src_record : benefit_id
    data_src ||--o{ src_record : src_cd
    ingest_run ||--o{ src_snapshot : run_id
    src_record ||--o{ src_snapshot : src_record_id
```

공통 감사 컬럼 rgst_id/rgst_dttm/upt_id/upt_dttm/del_yn/del_dttm/del_id는 반복 표시를 생략했다. 삭제된 부모·자식은 공개 조회에서 제외한다. 복합 FK는 관계선에 컬럼 조합으로 표기했다.

## 원문에서 검색·조건으로 이어지는 흐름

```mermaid
flowchart LR
    S[원천·수집 이력] --> R[src_record / src_snapshot]
    R --> V[benefit / benefit_ver]
    V --> A[aply_round · 회차]
    V --> D[doc / doc_chunk]
    D --> E[rule_evidence]
    V --> N[rule_set / rule_node]
    E --> N
    N --> Q[rule_question / question]
    D --> I[emb_input · 입력 문자열]
```

- 공통코드와 이력은 cmmn_cd/cmmn_cd_hist다. 문자열 코드 검증은 트리거로 수행하므로 모든 업무 테이블에 FK 관계선을 그리지 않았다.
- 규칙 초안의 근거 연결과 실제 승인·자격 판정은 구분한다. 승인 규칙은 현재 0개다.
- aply_round는 테이블만 준비된 상태로 현재 0행이다. 원천 주거 공고를 임의의 제도에 연결하지 않았다.
- 사용자 프로필·가족 답변은 이 DB에 없다. 현재는 선택형 브라우저 암호화 보관이다.

## 모델 선택 후 적용할 벡터 확장

다음 emb_vector는 **현재 미생성**이다. 데스크탑에서 새 모델을 선택한 뒤 [002_vectors.sql](../database/002_vectors.sql)을 적용한다. emb_input은 입력 문자열이며 벡터가 아니다.

```mermaid
erDiagram
    emb_model ||--o{ emb_vector : emb_model_id_dim_cnt
    emb_input ||--o{ emb_vector : input_hash
    emb_input o|--o{ doc_chunk : emb_input_hash
    emb_vector {
        uuid emb_model_id PK, FK
        text input_hash PK, FK
        int dim_cnt FK
        vector vec_val
        timestamptz gen_dttm
    }
```

상세 명세: [DATABASE.md](DATABASE.md) · 컨벤션: [CONVENTIONS.md](CONVENTIONS.md) · 데스크탑 복원: [DESKTOP_HANDOFF.md](DESKTOP_HANDOFF.md)
