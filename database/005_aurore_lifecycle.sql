-- AURORE conventions: common codes/history, *_yn, *_dttm and soft deletion.
BEGIN;
SET LOCAL search_path = bene_fit, public;

CREATE TABLE IF NOT EXISTS cmmn_cd (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prnt_cd_id bigint REFERENCES cmmn_cd(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    cd varchar(60) NOT NULL,
    cd_nm varchar(200) NOT NULL,
    cd_desc text,
    node_type_cd varchar(20) NOT NULL CHECK (node_type_cd IN ('GROUP','ITEM')),
    sort_seq integer NOT NULL DEFAULT 0,
    use_yn boolean NOT NULL DEFAULT true,
    sys_yn boolean NOT NULL DEFAULT false,
    UNIQUE NULLS NOT DISTINCT (prnt_cd_id,cd),
    CHECK (id IS DISTINCT FROM prnt_cd_id),
    CHECK (node_type_cd != 'ITEM' OR prnt_cd_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_cmmn_cd_parent_sort ON cmmn_cd(prnt_cd_id,sort_seq,id);
CREATE TABLE IF NOT EXISTS cmmn_cd_hist (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL DEFAULT gen_random_uuid(),
    cmmn_cd_id bigint NOT NULL REFERENCES cmmn_cd(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    act_type_cd varchar(20) NOT NULL,
    bf_data jsonb,
    af_data jsonb
);
CREATE INDEX IF NOT EXISTS idx_cmmn_cd_hist_date ON cmmn_cd_hist(cmmn_cd_id,id DESC);

DO $$ DECLARE t record; BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='bene_fit' LOOP
        EXECUTE format('ALTER TABLE bene_fit.%I ADD COLUMN IF NOT EXISTS rgst_id bigint, ADD COLUMN IF NOT EXISTS rgst_dttm timestamptz NOT NULL DEFAULT date_trunc(''second'',CURRENT_TIMESTAMP), ADD COLUMN IF NOT EXISTS upt_id bigint, ADD COLUMN IF NOT EXISTS upt_dttm timestamptz NOT NULL DEFAULT date_trunc(''second'',CURRENT_TIMESTAMP), ADD COLUMN IF NOT EXISTS del_yn boolean NOT NULL DEFAULT false, ADD COLUMN IF NOT EXISTS del_dttm timestamptz, ADD COLUMN IF NOT EXISTS del_id bigint',t.tablename);
    END LOOP;
END $$;

CREATE FUNCTION maintain_audit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='UPDATE' THEN
        IF NEW.rgst_dttm IS DISTINCT FROM OLD.rgst_dttm OR NEW.rgst_id IS DISTINCT FROM OLD.rgst_id THEN
            RAISE EXCEPTION 'Registration audit fields are immutable';
        END IF;
        NEW.upt_dttm := date_trunc('second',clock_timestamp());
    END IF;
    IF NEW.del_yn THEN NEW.del_dttm := coalesce(NEW.del_dttm,date_trunc('second',clock_timestamp()));
    ELSE NEW.del_dttm := NULL; NEW.del_id := NULL; END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION reject_physical_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Business deletion must update del_yn, del_dttm and del_id'; END $$;

CREATE FUNCTION cascade_soft_delete() RETURNS trigger LANGUAGE plpgsql
SET search_path=bene_fit,public AS $$
DECLARE child record; predicate text;
BEGIN
    IF NOT NEW.del_yn OR OLD.del_yn THEN RETURN NEW; END IF;
    -- ponytail: row-level correctness first; use a bulk archival job for source-wide removal.
    FOR child IN SELECT con.oid,con.conrelid::regclass AS target
        FROM pg_constraint con JOIN pg_class cl ON cl.oid=con.conrelid
        JOIN pg_namespace ns ON ns.oid=cl.relnamespace
        WHERE con.contype='f' AND con.confrelid=TG_RELID AND ns.nspname='bene_fit'
    LOOP
        SELECT string_agg(format('x.%I IS NOT NULL AND to_jsonb(x)->%L = $1->%L',a.attname,a.attname,b.attname),' AND ')
        INTO predicate FROM pg_constraint con
        CROSS JOIN LATERAL unnest(con.conkey,con.confkey) AS k(child_att,parent_att)
        JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=k.child_att
        JOIN pg_attribute b ON b.attrelid=con.confrelid AND b.attnum=k.parent_att WHERE con.oid=child.oid;
        IF child.target::oid=TG_RELID THEN
            IF pg_trigger_depth()>1 THEN CONTINUE; END IF;
            EXECUTE format('WITH RECURSIVE tree(id) AS (SELECT x.id FROM %s x WHERE NOT x.del_yn AND %s UNION SELECT x.id FROM tree d JOIN %s p ON p.id=d.id JOIN %s x ON %s WHERE NOT x.del_yn) UPDATE %s z SET del_yn=true,del_id=$2 FROM tree d WHERE z.id=d.id AND NOT z.del_yn',
                child.target,predicate,child.target,child.target,replace(predicate,'$1','to_jsonb(p)'),child.target)
            USING to_jsonb(NEW),NEW.del_id;
            CONTINUE;
        END IF;
        EXECUTE format('UPDATE %s x SET del_yn=true,del_id=$2 WHERE NOT x.del_yn AND %s',child.target,predicate)
        USING to_jsonb(NEW),NEW.del_id;
    END LOOP;
    RETURN NEW;
END $$;

DO $$ DECLARE t record; BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='bene_fit' LOOP
        EXECUTE format('CREATE TRIGGER trg_audit BEFORE INSERT OR UPDATE ON bene_fit.%I FOR EACH ROW EXECUTE FUNCTION bene_fit.maintain_audit()',t.tablename);
        EXECUTE format('CREATE TRIGGER trg_no_delete BEFORE DELETE ON bene_fit.%I FOR EACH ROW EXECUTE FUNCTION bene_fit.reject_physical_delete()',t.tablename);
        IF t.tablename!='cmmn_cd_hist' THEN
            EXECUTE format('CREATE TRIGGER trg_soft_cascade AFTER UPDATE OF del_yn ON bene_fit.%I FOR EACH ROW EXECUTE FUNCTION bene_fit.cascade_soft_delete()',t.tablename);
        END IF;
    END LOOP;
END $$;

CREATE FUNCTION log_cmmn_cd() RETURNS trigger LANGUAGE plpgsql
SET search_path=bene_fit,public AS $$
BEGIN
    INSERT INTO cmmn_cd_hist(cmmn_cd_id,act_type_cd,bf_data,af_data,rgst_id)
    VALUES (NEW.id,CASE WHEN TG_OP='INSERT' THEN 'CREATE' WHEN NEW.del_yn AND NOT OLD.del_yn THEN 'DELETE_MARK' ELSE 'UPDATE' END,
        CASE WHEN TG_OP='UPDATE' THEN to_jsonb(OLD) END,to_jsonb(NEW),coalesce(NEW.upt_id,NEW.rgst_id));
    RETURN NEW;
END $$;
CREATE TRIGGER trg_cmmn_cd_hist AFTER INSERT OR UPDATE ON cmmn_cd FOR EACH ROW EXECUTE FUNCTION log_cmmn_cd();

CREATE FUNCTION validate_cmmn_codes() RETURNS trigger LANGUAGE plpgsql
SET search_path=bene_fit,public AS $$
DECLARE i integer; value text;
BEGIN
    IF TG_OP='UPDATE' AND NEW.del_yn THEN RETURN NEW; END IF;
    FOR i IN 0..TG_NARGS/2-1 LOOP
        value := to_jsonb(NEW)->>TG_ARGV[i*2+1];
        IF value IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM cmmn_cd g JOIN cmmn_cd c ON c.prnt_cd_id=g.id
            WHERE g.prnt_cd_id IS NULL AND g.cd=TG_ARGV[i*2] AND c.cd=value
                AND g.use_yn AND c.use_yn AND NOT g.del_yn AND NOT c.del_yn
        ) THEN RAISE EXCEPTION 'Unknown or inactive common code: %.%',TG_ARGV[i*2],value; END IF;
    END LOOP;
    RETURN NEW;
END $$;

INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('INGEST_STAT','INGEST_STAT','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'running','running','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='INGEST_STAT';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'complete','complete','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='INGEST_STAT';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'partial','partial','ITEM',2,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='INGEST_STAT';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'failed','failed','ITEM',3,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='INGEST_STAT';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('SRC_REC_TYPE','SRC_REC_TYPE','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'program','program','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='SRC_REC_TYPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'notice','notice','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='SRC_REC_TYPE';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('MAP_STAT','MAP_STAT','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'unreviewed','unreviewed','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='MAP_STAT';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'confirmed','confirmed','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='MAP_STAT';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('PRESENCE_STAT','PRESENCE_STAT','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'seen','seen','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='PRESENCE_STAT';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'missing','missing','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='PRESENCE_STAT';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'withdrawn_confirmed','withdrawn_confirmed','ITEM',2,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='PRESENCE_STAT';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('REPR_TYPE','REPR_TYPE','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'extracted_api_records','extracted_api_records','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='REPR_TYPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'raw_response','raw_response','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='REPR_TYPE';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('GEO_SCOPE','GEO_SCOPE','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'unknown','unknown','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='GEO_SCOPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'nationwide','nationwide','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='GEO_SCOPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'regional','regional','ITEM',2,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='GEO_SCOPE';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('PERIOD_TYPE','PERIOD_TYPE','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'unknown','unknown','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='PERIOD_TYPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'window','window','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='PERIOD_TYPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'always_open','always_open','ITEM',2,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='PERIOD_TYPE';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('VALUE_TYPE','VALUE_TYPE','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'number','number','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='VALUE_TYPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'boolean','boolean','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='VALUE_TYPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'enum','enum','ITEM',2,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='VALUE_TYPE';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('SUBJ_ROLE','SUBJ_ROLE','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'applicant','applicant','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='SUBJ_ROLE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'beneficiary','beneficiary','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='SUBJ_ROLE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'guardian','guardian','ITEM',2,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='SUBJ_ROLE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'household','household','ITEM',3,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='SUBJ_ROLE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'search_intent','search_intent','ITEM',4,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='SUBJ_ROLE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'unresolved','unresolved','ITEM',5,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='SUBJ_ROLE';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('RULE_STAT','RULE_STAT','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'draft','draft','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='RULE_STAT';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'approved','approved','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='RULE_STAT';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'retired','retired','ITEM',2,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='RULE_STAT';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('RULE_COVERAGE','RULE_COVERAGE','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'partial','partial','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='RULE_COVERAGE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'complete','complete','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='RULE_COVERAGE';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('RULE_NODE_TYPE','RULE_NODE_TYPE','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'all','all','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='RULE_NODE_TYPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'any','any','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='RULE_NODE_TYPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'not','not','ITEM',2,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='RULE_NODE_TYPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'condition','condition','ITEM',3,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='RULE_NODE_TYPE';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'unresolved','unresolved','ITEM',4,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='RULE_NODE_TYPE';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('COMPARE_OP','COMPARE_OP','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'eq','eq','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='COMPARE_OP';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'neq','neq','ITEM',1,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='COMPARE_OP';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'gt','gt','ITEM',2,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='COMPARE_OP';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'gte','gte','ITEM',3,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='COMPARE_OP';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'lt','lt','ITEM',4,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='COMPARE_OP';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'lte','lte','ITEM',5,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='COMPARE_OP';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'in','in','ITEM',6,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='COMPARE_OP';
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'not_in','not_in','ITEM',7,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='COMPARE_OP';
INSERT INTO cmmn_cd(cd,cd_nm,node_type_cd,sys_yn) VALUES ('DOC_TYPE','DOC_TYPE','GROUP',true);
INSERT INTO cmmn_cd(prnt_cd_id,cd,cd_nm,node_type_cd,sort_seq,sys_yn) SELECT id,'api_fields','api_fields','ITEM',0,true FROM cmmn_cd WHERE prnt_cd_id IS NULL AND cd='DOC_TYPE';
CREATE TRIGGER trg_codes BEFORE INSERT OR UPDATE ON ingest_run FOR EACH ROW EXECUTE FUNCTION validate_cmmn_codes('INGEST_STAT','stat_cd');
CREATE TRIGGER trg_codes BEFORE INSERT OR UPDATE ON src_record FOR EACH ROW EXECUTE FUNCTION validate_cmmn_codes('SRC_REC_TYPE','type_cd','MAP_STAT','map_stat_cd','PRESENCE_STAT','presence_stat_cd');
CREATE TRIGGER trg_codes BEFORE INSERT OR UPDATE ON src_snapshot FOR EACH ROW EXECUTE FUNCTION validate_cmmn_codes('REPR_TYPE','repr_type_cd');
CREATE TRIGGER trg_codes BEFORE INSERT OR UPDATE ON benefit_ver FOR EACH ROW EXECUTE FUNCTION validate_cmmn_codes('GEO_SCOPE','geo_scope_cd');
CREATE TRIGGER trg_codes BEFORE INSERT OR UPDATE ON aply_round FOR EACH ROW EXECUTE FUNCTION validate_cmmn_codes('PERIOD_TYPE','period_type_cd');
CREATE TRIGGER trg_codes BEFORE INSERT OR UPDATE ON fact_def FOR EACH ROW EXECUTE FUNCTION validate_cmmn_codes('VALUE_TYPE','value_type_cd');
CREATE TRIGGER trg_codes BEFORE INSERT OR UPDATE ON question FOR EACH ROW EXECUTE FUNCTION validate_cmmn_codes('SUBJ_ROLE','subj_role_cd');
CREATE TRIGGER trg_codes BEFORE INSERT OR UPDATE ON rule_node FOR EACH ROW EXECUTE FUNCTION validate_cmmn_codes('SUBJ_ROLE','subj_role_cd','RULE_NODE_TYPE','type_cd','COMPARE_OP','op_cd');
CREATE TRIGGER trg_codes BEFORE INSERT OR UPDATE ON rule_set FOR EACH ROW EXECUTE FUNCTION validate_cmmn_codes('RULE_STAT','stat_cd','RULE_COVERAGE','coverage_cd');
CREATE TRIGGER trg_codes BEFORE INSERT OR UPDATE ON doc FOR EACH ROW EXECUTE FUNCTION validate_cmmn_codes('DOC_TYPE','doc_type_cd');

CREATE VIEW active_src_snapshot AS
SELECT s.* FROM src_snapshot s
JOIN src_record r ON r.id=s.src_record_id JOIN data_src p ON p.cd=r.src_cd
JOIN ingest_run b ON b.id=s.run_id
WHERE NOT s.del_yn AND NOT r.del_yn AND NOT p.del_yn AND NOT b.del_yn;

CREATE VIEW current_benefit_ver AS
SELECT v.* FROM benefit_ver v JOIN benefit b ON b.id=v.benefit_id
WHERE v.current_yn AND NOT v.del_yn AND NOT b.del_yn AND EXISTS (
    SELECT 1 FROM benefit_ver_src x JOIN active_src_snapshot s ON s.id=x.src_snapshot_id
    WHERE x.benefit_ver_id=v.id AND NOT x.del_yn
);

DROP VIEW IF EXISTS current_doc_chunk;
CREATE VIEW current_doc_chunk AS
SELECT c.* FROM doc_chunk c JOIN doc d ON d.id=c.doc_id
JOIN current_benefit_ver v ON v.id=d.benefit_ver_id
JOIN active_src_snapshot s ON s.id=d.src_snapshot_id
LEFT JOIN aply_round r ON r.id=d.aply_round_id
LEFT JOIN emb_input i ON i.input_hash=c.emb_input_hash
WHERE NOT c.del_yn AND NOT d.del_yn
    AND (c.emb_input_hash IS NULL OR NOT i.del_yn)
    AND (d.aply_round_id IS NULL OR (r.current_yn AND NOT r.del_yn AND EXISTS (
        SELECT 1 FROM active_src_snapshot rs WHERE rs.id=r.src_snapshot_id)));

CREATE VIEW active_rule_set AS
SELECT r.* FROM rule_set r JOIN current_benefit_ver v ON v.id=r.benefit_ver_id
WHERE r.stat_cd='approved' AND NOT r.del_yn
AND (r.aply_round_id IS NULL OR EXISTS (SELECT 1 FROM aply_round a JOIN active_src_snapshot s ON s.id=a.src_snapshot_id
    WHERE a.id=r.aply_round_id AND a.current_yn AND NOT a.del_yn))
AND NOT EXISTS (SELECT 1 FROM rule_node n LEFT JOIN fact_def f ON f.cd=n.fact_cd
    WHERE n.rule_set_id=r.id AND (n.del_yn OR f.del_yn))
AND NOT EXISTS (SELECT 1 FROM rule_evidence e LEFT JOIN current_doc_chunk c ON c.id=e.chunk_id
    WHERE e.rule_set_id=r.id AND (e.del_yn OR c.id IS NULL))
AND NOT EXISTS (SELECT 1 FROM rule_question q JOIN question x ON x.id=q.question_id
    WHERE q.rule_set_id=r.id AND (q.del_yn OR x.del_yn));
COMMIT;
