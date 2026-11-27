-- PostgreSQL 16+ design v1. Apply once to a new database, never over SQLite files.
BEGIN;
CREATE SCHEMA bene_fit;
SET LOCAL search_path = bene_fit, public;

CREATE TABLE data_src (
    cd text PRIMARY KEY,
    nm text NOT NULL,
    home_url text,
    use_yn boolean NOT NULL DEFAULT true
);

CREATE TABLE ingest_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    src_cd text NOT NULL REFERENCES data_src(cd),
    ds_nm text NOT NULL,
    start_dttm timestamptz NOT NULL DEFAULT now(),
    end_dttm timestamptz,
    stat_cd text NOT NULL DEFAULT 'running' CHECK (stat_cd IN ('running','complete','partial','failed')),
    fetch_cnt integer NOT NULL DEFAULT 0 CHECK (fetch_cnt >= 0),
    total_cnt integer CHECK (total_cnt >= 0),
    err_cd text,
    CHECK (end_dttm IS NULL OR end_dttm >= start_dttm),
    CHECK (stat_cd = 'running' OR end_dttm IS NOT NULL)
);

CREATE TABLE benefit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rgst_dttm timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE src_record (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    src_cd text NOT NULL REFERENCES data_src(cd),
    ext_id text NOT NULL,
    type_cd text NOT NULL CHECK (type_cd IN ('program','notice')),
    benefit_id uuid REFERENCES benefit(id),
    map_stat_cd text NOT NULL DEFAULT 'unreviewed' CHECK (map_stat_cd IN ('unreviewed','confirmed')),
    old_rec_id text UNIQUE,
    first_seen_dttm timestamptz NOT NULL DEFAULT now(),
    last_seen_dttm timestamptz NOT NULL DEFAULT now(),
    presence_stat_cd text NOT NULL DEFAULT 'seen' CHECK (presence_stat_cd IN ('seen','missing','withdrawn_confirmed')),
    UNIQUE (src_cd, ext_id, type_cd),
    CHECK (map_stat_cd != 'confirmed' OR benefit_id IS NOT NULL),
    CHECK (last_seen_dttm >= first_seen_dttm)
);
CREATE INDEX source_records_program ON src_record(benefit_id);

CREATE TABLE src_snapshot (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    src_record_id uuid NOT NULL REFERENCES src_record(id),
    run_id uuid NOT NULL REFERENCES ingest_run(id),
    cont_hash text NOT NULL CHECK (cont_hash ~ '^[0-9a-f]{64}$'),
    raw_json jsonb NOT NULL CHECK (jsonb_typeof(raw_json) IN ('object','array')),
    repr_type_cd text NOT NULL DEFAULT 'extracted_api_records' CHECK (repr_type_cd IN ('extracted_api_records','raw_response')),
    src_cont text,
    src_url text,
    src_mod_dttm timestamptz,
    fetch_dttm timestamptz NOT NULL DEFAULT now(),
    UNIQUE (src_record_id, run_id, cont_hash),
    CHECK (repr_type_cd != 'raw_response' OR src_cont IS NOT NULL)
);
CREATE INDEX snapshots_record_time ON src_snapshot(src_record_id, fetch_dttm DESC);

CREATE TABLE benefit_ver (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    benefit_id uuid NOT NULL REFERENCES benefit(id),
    cont_hash text NOT NULL CHECK (cont_hash ~ '^[0-9a-f]{64}$'),
    nm text NOT NULL,
    org_nm text,
    cat_cd text,
    summary_cont text,
    fld_json jsonb NOT NULL DEFAULT '{}',
    meta_json jsonb NOT NULL DEFAULT '{}',
    src_cond_json jsonb NOT NULL DEFAULT '{}',
    eff_start_dt date,
    eff_end_dt date,
    period_verify_yn boolean NOT NULL DEFAULT false,
    ref_yr integer CHECK (ref_yr BETWEEN 1900 AND 9999),
    geo_scope_cd text NOT NULL DEFAULT 'unknown' CHECK (geo_scope_cd IN ('unknown','nationwide','regional')),
    reg_json jsonb NOT NULL DEFAULT '[]',
    geo_verify_yn boolean NOT NULL DEFAULT false,
    current_yn boolean NOT NULL DEFAULT true,
    obs_dttm timestamptz NOT NULL DEFAULT now(),
    UNIQUE (benefit_id, cont_hash),
    UNIQUE (id, benefit_id),
    CHECK (eff_end_dt IS NULL OR eff_start_dt IS NULL OR eff_end_dt >= eff_start_dt),
    CHECK (NOT period_verify_yn OR eff_start_dt IS NOT NULL),
    CHECK (jsonb_typeof(fld_json) = 'object' AND jsonb_typeof(src_cond_json) = 'object'),
    CHECK (jsonb_typeof(reg_json) = 'array'),
    CHECK (NOT geo_verify_yn OR geo_scope_cd != 'unknown')
);
CREATE UNIQUE INDEX one_current_program_version ON benefit_ver(benefit_id) WHERE current_yn;
CREATE INDEX program_versions_category ON benefit_ver(cat_cd) WHERE current_yn;

CREATE TABLE benefit_ver_src (
    benefit_ver_id uuid NOT NULL REFERENCES benefit_ver(id),
    src_snapshot_id uuid NOT NULL REFERENCES src_snapshot(id),
    fld_map_json jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (benefit_ver_id, src_snapshot_id)
);

CREATE TABLE aply_round (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    benefit_id uuid NOT NULL REFERENCES benefit(id),
    benefit_ver_id uuid NOT NULL,
    src_record_id uuid NOT NULL REFERENCES src_record(id),
    src_snapshot_id uuid NOT NULL REFERENCES src_snapshot(id),
    rnd_key text NOT NULL,
    rev_no integer NOT NULL CHECK (rev_no > 0),
    ttl text NOT NULL,
    pub_dttm timestamptz,
    aply_start_dttm timestamptz,
    aply_end_dttm timestamptz,
    period_type_cd text NOT NULL DEFAULT 'unknown' CHECK (period_type_cd IN ('unknown','window','always_open')),
    period_verify_yn boolean NOT NULL DEFAULT false,
    src_stts_txt text,
    current_yn boolean NOT NULL DEFAULT true,
    obs_dttm timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (benefit_ver_id, benefit_id) REFERENCES benefit_ver(id, benefit_id),
    UNIQUE (src_record_id, rnd_key, rev_no),
    UNIQUE (id, benefit_ver_id),
    CHECK (aply_end_dttm IS NULL OR aply_start_dttm IS NULL OR aply_end_dttm >= aply_start_dttm),
    CHECK (NOT period_verify_yn OR period_type_cd != 'unknown'),
    CHECK (NOT period_verify_yn OR period_type_cd != 'window' OR (aply_start_dttm IS NOT NULL AND aply_end_dttm IS NOT NULL)),
    CHECK (period_type_cd != 'always_open' OR (aply_start_dttm IS NULL AND aply_end_dttm IS NULL))
);
CREATE UNIQUE INDEX one_current_round_revision ON aply_round(src_record_id, rnd_key) WHERE current_yn;
CREATE INDEX rounds_version ON aply_round(benefit_ver_id);

CREATE TABLE doc (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    benefit_ver_id uuid NOT NULL REFERENCES benefit_ver(id),
    aply_round_id uuid,
    src_snapshot_id uuid NOT NULL REFERENCES src_snapshot(id),
    old_doc_id text UNIQUE,
    doc_type_cd text NOT NULL DEFAULT 'api_fields',
    parse_ver text NOT NULL,
    cont_hash text NOT NULL CHECK (cont_hash ~ '^[0-9a-f]{64}$'),
    fld_json jsonb NOT NULL,
    meta_json jsonb NOT NULL DEFAULT '{}',
    rgst_dttm timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (aply_round_id, benefit_ver_id) REFERENCES aply_round(id, benefit_ver_id),
    UNIQUE NULLS NOT DISTINCT (benefit_ver_id, aply_round_id, src_snapshot_id, parse_ver, cont_hash)
);
CREATE INDEX documents_version ON doc(benefit_ver_id);

CREATE TABLE emb_input (
    input_hash text PRIMARY KEY CHECK (input_hash ~ '^[0-9a-f]{64}$'),
    input_cont text NOT NULL
);

CREATE TABLE doc_chunk (
    id text PRIMARY KEY,
    doc_id uuid NOT NULL REFERENCES doc(id),
    fld_nm text NOT NULL,
    start_pos integer NOT NULL CHECK (start_pos >= 0),
    end_pos integer NOT NULL,
    chunk_cont text NOT NULL,
    loc_json jsonb NOT NULL,
    split_ver text NOT NULL,
    emb_input_hash text REFERENCES emb_input(input_hash),
    CHECK (end_pos > start_pos AND char_length(chunk_cont) = end_pos - start_pos),
    UNIQUE (doc_id, split_ver, fld_nm, start_pos, end_pos)
);
CREATE INDEX chunks_document ON doc_chunk(doc_id, fld_nm, start_pos);
CREATE INDEX chunks_embedding_input ON doc_chunk(emb_input_hash);

CREATE TABLE fact_def (
    cd text PRIMARY KEY,
    value_type_cd text NOT NULL CHECK (value_type_cd IN ('number','boolean','enum')),
    unit_cd text,
    descr text NOT NULL,
    compare_yn boolean NOT NULL DEFAULT false
);

CREATE TABLE question (
    id text PRIMARY KEY,
    rev_no integer NOT NULL CHECK (rev_no > 0),
    fact_cd text REFERENCES fact_def(cd),
    subj_role_cd text NOT NULL CHECK (subj_role_cd IN ('applicant','beneficiary','guardian','household','search_intent')),
    qstn_txt text NOT NULL,
    help_cont text NOT NULL,
    opt_json jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(opt_json) = 'array'),
    optional_yn boolean NOT NULL DEFAULT true CHECK (optional_yn),
    UNIQUE (id, fact_cd, subj_role_cd)
);

CREATE TABLE rule_set (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    benefit_ver_id uuid NOT NULL REFERENCES benefit_ver(id),
    aply_round_id uuid,
    var_key text NOT NULL DEFAULT 'default',
    rev_no integer NOT NULL CHECK (rev_no > 0),
    stat_cd text NOT NULL DEFAULT 'draft' CHECK (stat_cd IN ('draft','approved','retired')),
    coverage_cd text NOT NULL DEFAULT 'partial' CHECK (coverage_cd IN ('partial','complete')),
    eff_start_dt date,
    eff_end_dt date,
    ref_basis text,
    rvwr_id text,
    review_dttm timestamptz,
    rvw_note text,
    rgst_dttm timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (aply_round_id, benefit_ver_id) REFERENCES aply_round(id, benefit_ver_id),
    UNIQUE NULLS NOT DISTINCT (benefit_ver_id, aply_round_id, var_key, rev_no),
    CHECK (eff_end_dt IS NULL OR eff_start_dt IS NULL OR eff_end_dt >= eff_start_dt),
    CHECK (stat_cd = 'draft' OR (eff_start_dt IS NOT NULL AND nullif(btrim(ref_basis),'') IS NOT NULL
        AND nullif(btrim(rvwr_id),'') IS NOT NULL AND review_dttm IS NOT NULL AND nullif(btrim(rvw_note),'') IS NOT NULL))
);

CREATE TABLE rule_node (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_set_id uuid NOT NULL REFERENCES rule_set(id),
    prnt_id uuid,
    sort_seq integer NOT NULL DEFAULT 0 CHECK (sort_seq >= 0),
    type_cd text NOT NULL CHECK (type_cd IN ('all','any','not','condition','unresolved')),
    fact_cd text REFERENCES fact_def(cd),
    subj_role_cd text CHECK (subj_role_cd IN ('applicant','beneficiary','guardian','household','unresolved')),
    op_cd text CHECK (op_cd IN ('eq','neq','gt','gte','lt','lte','in','not_in')),
    cmp_val_json jsonb,
    draft_json jsonb NOT NULL DEFAULT '{}',
    UNIQUE (id, rule_set_id),
    UNIQUE (id, rule_set_id, fact_cd, subj_role_cd),
    FOREIGN KEY (prnt_id, rule_set_id) REFERENCES rule_node(id, rule_set_id) DEFERRABLE INITIALLY DEFERRED,
    CHECK (prnt_id IS NULL OR prnt_id != id),
    CHECK (type_cd IN ('condition','unresolved') OR (fact_cd IS NULL AND subj_role_cd IS NULL AND op_cd IS NULL AND cmp_val_json IS NULL))
);
CREATE UNIQUE INDEX one_rule_root ON rule_node(rule_set_id) WHERE prnt_id IS NULL;
CREATE INDEX rule_nodes_parent ON rule_node(rule_set_id, prnt_id);

CREATE TABLE rule_evidence (
    rule_node_id uuid NOT NULL,
    rule_set_id uuid NOT NULL,
    chunk_id text NOT NULL REFERENCES doc_chunk(id),
    start_pos integer NOT NULL CHECK (start_pos >= 0),
    end_pos integer NOT NULL,
    quote_cont text NOT NULL,
    PRIMARY KEY (rule_node_id, chunk_id, start_pos),
    FOREIGN KEY (rule_node_id, rule_set_id) REFERENCES rule_node(id, rule_set_id),
    CHECK (end_pos > start_pos AND char_length(quote_cont) = end_pos - start_pos)
);
CREATE INDEX rule_evidence_chunk ON rule_evidence(chunk_id);

CREATE TABLE rule_question (
    rule_node_id uuid NOT NULL,
    rule_set_id uuid NOT NULL,
    question_id text NOT NULL,
    fact_cd text NOT NULL,
    subj_role_cd text NOT NULL,
    PRIMARY KEY (rule_node_id, question_id),
    FOREIGN KEY (rule_node_id, rule_set_id, fact_cd, subj_role_cd) REFERENCES rule_node(id, rule_set_id, fact_cd, subj_role_cd),
    FOREIGN KEY (question_id, fact_cd, subj_role_cd) REFERENCES question(id, fact_cd, subj_role_cd)
);

CREATE TABLE emb_model (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_cd text NOT NULL,
    model_nm text NOT NULL,
    model_rev text NOT NULL,
    dim_cnt integer NOT NULL CHECK (dim_cnt BETWEEN 1 AND 16000),
    norm_yn boolean NOT NULL,
    qry_pfx text NOT NULL DEFAULT '',
    doc_pfx text NOT NULL DEFAULT '',
    max_tok_cnt integer NOT NULL CHECK (max_tok_cnt > 0),
    out_cfg_json jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(out_cfg_json) = 'object'),
    config_hash text NOT NULL UNIQUE CHECK (config_hash ~ '^[0-9a-f]{64}$'),
    act_yn boolean NOT NULL DEFAULT false,
    rgst_dttm timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, dim_cnt)
);
CREATE UNIQUE INDEX one_active_embedding_model ON emb_model((true)) WHERE act_yn;

CREATE VIEW current_doc_chunk AS
SELECT c.* FROM doc_chunk c
JOIN doc d ON d.id = c.doc_id
JOIN benefit_ver v ON v.id = d.benefit_ver_id
LEFT JOIN aply_round r ON r.id = d.aply_round_id
WHERE v.current_yn AND (d.aply_round_id IS NULL OR r.current_yn);

COMMIT;
