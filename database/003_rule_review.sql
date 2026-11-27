-- Approval validates structure, typed values, question roles and source quotations.
-- It cannot establish whether a human interpretation of an official policy is correct.
BEGIN;
SET LOCAL search_path = bene_fit, public;

CREATE UNIQUE INDEX one_approved_rule_revision
ON rule_set(benefit_ver_id, aply_round_id, var_key) NULLS NOT DISTINCT WHERE stat_cd = 'approved';

CREATE FUNCTION protect_rule_children() RETURNS trigger LANGUAGE plpgsql
SET search_path = bene_fit, public AS $$
DECLARE scope_id uuid;
BEGIN
    IF TG_OP = 'UPDATE' AND (to_jsonb(OLD) - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[]) = (to_jsonb(NEW) - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[]) THEN RETURN NEW; END IF;
    IF TG_OP = 'UPDATE' AND NEW.rule_set_id != OLD.rule_set_id THEN
        RAISE EXCEPTION 'Create a new rule node instead of moving it between rule sets';
    END IF;
    IF TG_OP = 'DELETE' THEN scope_id := OLD.rule_set_id; ELSE scope_id := NEW.rule_set_id; END IF;
    PERFORM 1 FROM rule_set WHERE id = scope_id AND stat_cd = 'draft' FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Only draft rules may be edited'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
CREATE TRIGGER protect_nodes BEFORE INSERT OR UPDATE OR DELETE ON rule_node
FOR EACH ROW EXECUTE FUNCTION protect_rule_children();
CREATE TRIGGER protect_evidence BEFORE INSERT OR UPDATE OR DELETE ON rule_evidence
FOR EACH ROW EXECUTE FUNCTION protect_rule_children();
CREATE TRIGGER protect_question_links BEFORE INSERT OR UPDATE OR DELETE ON rule_question
FOR EACH ROW EXECUTE FUNCTION protect_rule_children();

CREATE FUNCTION review_rule_set() RETURNS trigger LANGUAGE plpgsql
SET search_path = bene_fit, public AS $$
DECLARE total_nodes integer; reachable_nodes integer;
BEGIN
    IF TG_OP = 'UPDATE' AND (to_jsonb(OLD) - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[]) = (to_jsonb(NEW) - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[]) THEN RETURN NEW; END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.stat_cd != 'draft' THEN RAISE EXCEPTION 'Insert draft rules before review'; END IF;
        RETURN NEW;
    END IF;
    IF OLD.stat_cd != 'draft' THEN
        IF OLD.stat_cd = 'approved' AND NEW.stat_cd = 'retired'
           AND (to_jsonb(OLD) - 'stat_cd' - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[]) = (to_jsonb(NEW) - 'stat_cd' - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[]) THEN RETURN NEW; END IF;
        RAISE EXCEPTION 'Reviewed rules are immutable; create another rev_no';
    END IF;
    IF NEW.stat_cd = 'retired' THEN RAISE EXCEPTION 'Only approved rules may be retired'; END IF;
    IF NEW.stat_cd != 'approved' THEN RETURN NEW; END IF;
    SELECT count(*) INTO total_nodes FROM rule_node WHERE rule_set_id = NEW.id;
    IF total_nodes = 0 OR (SELECT count(*) FROM rule_node WHERE rule_set_id = NEW.id AND prnt_id IS NULL) != 1 THEN
        RAISE EXCEPTION 'Approval needs one root and at least one condition';
    END IF;
    WITH RECURSIVE walk(id) AS (
        SELECT id FROM rule_node WHERE rule_set_id = NEW.id AND prnt_id IS NULL
        UNION
        SELECT n.id FROM rule_node n JOIN walk w ON n.prnt_id = w.id WHERE n.rule_set_id = NEW.id
    ) SELECT count(*) INTO reachable_nodes FROM walk;
    IF reachable_nodes != total_nodes THEN RAISE EXCEPTION 'Rule tree is disconnected or cyclic'; END IF;
    IF EXISTS (
        SELECT 1 FROM rule_node n WHERE n.rule_set_id = NEW.id AND (
            n.type_cd = 'unresolved'
            OR (n.type_cd IN ('all','any') AND NOT EXISTS (SELECT 1 FROM rule_node child WHERE child.prnt_id = n.id))
            OR (n.type_cd = 'not' AND (SELECT count(*) FROM rule_node child WHERE child.prnt_id = n.id) != 1)
            OR (n.type_cd = 'condition' AND EXISTS (SELECT 1 FROM rule_node child WHERE child.prnt_id = n.id))
        )
    ) THEN RAISE EXCEPTION 'Invalid or unresolved logic'; END IF;
    IF EXISTS (
        SELECT 1 FROM rule_node n LEFT JOIN fact_def f ON f.cd = n.fact_cd
        WHERE n.rule_set_id = NEW.id AND n.type_cd = 'condition' AND (
            n.fact_cd IS NULL OR n.subj_role_cd IS NULL OR n.subj_role_cd = 'unresolved'
            OR NOT f.compare_yn OR n.op_cd IS NULL OR n.cmp_val_json IS NULL
            OR NOT CASE f.value_type_cd
                WHEN 'number' THEN jsonb_typeof(n.cmp_val_json) = 'number' AND n.op_cd IN ('eq','neq','gt','gte','lt','lte')
                WHEN 'boolean' THEN jsonb_typeof(n.cmp_val_json) = 'boolean' AND n.op_cd IN ('eq','neq')
                WHEN 'enum' THEN CASE
                    WHEN n.op_cd IN ('eq','neq') THEN jsonb_typeof(n.cmp_val_json) = 'string'
                    WHEN n.op_cd IN ('in','not_in') AND jsonb_typeof(n.cmp_val_json) = 'array' THEN
                        jsonb_array_length(n.cmp_val_json) > 0 AND NOT EXISTS (
                            SELECT 1 FROM jsonb_array_elements(n.cmp_val_json) x WHERE jsonb_typeof(x) != 'string')
                    ELSE false END
                ELSE false END
            OR NOT EXISTS (SELECT 1 FROM rule_question q WHERE q.rule_node_id = n.id)
        )
    ) THEN RAISE EXCEPTION 'Condition needs a supported typed fact, resolved subject and matching question'; END IF;
    IF EXISTS (
        SELECT 1 FROM rule_node n WHERE n.rule_set_id = NEW.id
        AND NOT EXISTS (SELECT 1 FROM rule_evidence e WHERE e.rule_node_id = n.id)
    ) THEN RAISE EXCEPTION 'Each condition and logical relation needs source evidence'; END IF;
    IF EXISTS (
        SELECT 1 FROM rule_evidence e JOIN doc_chunk c ON c.id = e.chunk_id
        JOIN doc d ON d.id = c.doc_id
        WHERE e.rule_set_id = NEW.id AND (
            d.benefit_ver_id != NEW.benefit_ver_id
            OR (d.aply_round_id IS NOT NULL AND d.aply_round_id IS DISTINCT FROM NEW.aply_round_id)
            OR e.end_pos > char_length(c.chunk_cont)
            OR substring(c.chunk_cont FROM e.start_pos + 1 FOR e.end_pos - e.start_pos) != e.quote_cont)
    ) THEN RAISE EXCEPTION 'Evidence must match the same policy scope and exact source text'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER review_rules BEFORE INSERT OR UPDATE ON rule_set
FOR EACH ROW EXECUTE FUNCTION review_rule_set();

CREATE FUNCTION protect_question_definition() RETURNS trigger LANGUAGE plpgsql
SET search_path = bene_fit, public AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (to_jsonb(OLD) - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[]) = (to_jsonb(NEW) - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[]) THEN RETURN NEW; END IF;
    IF EXISTS (SELECT 1 FROM rule_question q JOIN rule_set r ON r.id = q.rule_set_id
               WHERE q.question_id = OLD.id AND r.stat_cd != 'draft') THEN
        RAISE EXCEPTION 'Question is used by reviewed rules; create a new question ID/rev_no';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
CREATE TRIGGER protect_questions BEFORE UPDATE OR DELETE ON question
FOR EACH ROW EXECUTE FUNCTION protect_question_definition();

CREATE FUNCTION protect_fact_definition() RETURNS trigger LANGUAGE plpgsql
SET search_path = bene_fit, public AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (to_jsonb(OLD) - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[]) = (to_jsonb(NEW) - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[]) THEN RETURN NEW; END IF;
    IF EXISTS (SELECT 1 FROM rule_node n JOIN rule_set r ON r.id = n.rule_set_id
               WHERE n.fact_cd = OLD.cd AND r.stat_cd != 'draft') THEN
        RAISE EXCEPTION 'Fact is used by reviewed rules; create a new fact cd';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END $$;
CREATE TRIGGER protect_facts BEFORE UPDATE OR DELETE ON fact_def
FOR EACH ROW EXECUTE FUNCTION protect_fact_definition();

CREATE FUNCTION protect_versioned_content() RETURNS trigger LANGUAGE plpgsql
SET search_path = bene_fit, public AS $$
DECLARE mutable_key text;
BEGIN
    IF TG_TABLE_NAME IN ('benefit_ver','aply_round') THEN mutable_key := 'current_yn';
    ELSIF TG_TABLE_NAME = 'emb_model' THEN mutable_key := 'act_yn'; END IF;
    IF TG_OP = 'UPDATE' AND
       (to_jsonb(OLD) - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[] - coalesce(mutable_key,'__none__')) =
       (to_jsonb(NEW) - ARRAY['del_yn','del_dttm','del_id','upt_dttm','upt_id']::text[] - coalesce(mutable_key,'__none__')) THEN RETURN NEW; END IF;
    RAISE EXCEPTION 'Source content and model configuration are append-only; create another version';
END $$;
CREATE TRIGGER immutable_snapshots BEFORE UPDATE OR DELETE ON src_snapshot
FOR EACH ROW EXECUTE FUNCTION protect_versioned_content();
CREATE TRIGGER immutable_versions BEFORE UPDATE OR DELETE ON benefit_ver
FOR EACH ROW EXECUTE FUNCTION protect_versioned_content();
CREATE TRIGGER immutable_rounds BEFORE UPDATE OR DELETE ON aply_round
FOR EACH ROW EXECUTE FUNCTION protect_versioned_content();
CREATE TRIGGER immutable_documents BEFORE UPDATE OR DELETE ON doc
FOR EACH ROW EXECUTE FUNCTION protect_versioned_content();
CREATE TRIGGER immutable_chunks BEFORE UPDATE OR DELETE ON doc_chunk
FOR EACH ROW EXECUTE FUNCTION protect_versioned_content();
CREATE TRIGGER immutable_embedding_inputs BEFORE UPDATE OR DELETE ON emb_input
FOR EACH ROW EXECUTE FUNCTION protect_versioned_content();
CREATE TRIGGER immutable_model_config BEFORE UPDATE OR DELETE ON emb_model
FOR EACH ROW EXECUTE FUNCTION protect_versioned_content();

CREATE FUNCTION check_source_scope() RETURNS trigger LANGUAGE plpgsql
SET search_path = bene_fit, public AS $$
DECLARE record_program uuid; version_program uuid; snapshot_record uuid; record_kind text;
BEGIN
    SELECT r.benefit_id, r.id, r.type_cd INTO record_program, snapshot_record, record_kind
    FROM src_snapshot s JOIN src_record r ON r.id = s.src_record_id WHERE s.id = NEW.src_snapshot_id;
    SELECT benefit_id INTO version_program FROM benefit_ver WHERE id = NEW.benefit_ver_id;
    IF record_program IS NULL OR record_program IS DISTINCT FROM version_program THEN
        RAISE EXCEPTION 'Snapshot and policy version belong to different or unmapped benefit';
    END IF;
    IF TG_TABLE_NAME = 'aply_round' THEN
        IF snapshot_record != NEW.src_record_id OR record_kind != 'notice' THEN
            RAISE EXCEPTION 'A round must cite its own notice snapshot';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER version_source_scope BEFORE INSERT OR UPDATE ON benefit_ver_src
FOR EACH ROW EXECUTE FUNCTION check_source_scope();
CREATE TRIGGER document_source_scope BEFORE INSERT OR UPDATE ON doc
FOR EACH ROW EXECUTE FUNCTION check_source_scope();
CREATE TRIGGER round_source_scope BEFORE INSERT OR UPDATE ON aply_round
FOR EACH ROW EXECUTE FUNCTION check_source_scope();

CREATE FUNCTION check_snapshot_run_source() RETURNS trigger LANGUAGE plpgsql
SET search_path = bene_fit, public AS $$
BEGIN
    IF (SELECT src_cd FROM src_record WHERE id = NEW.src_record_id)
       IS DISTINCT FROM (SELECT src_cd FROM ingest_run WHERE id = NEW.run_id) THEN
        RAISE EXCEPTION 'Collection run and record have different providers';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER snapshot_run_scope BEFORE INSERT ON src_snapshot
FOR EACH ROW EXECUTE FUNCTION check_snapshot_run_source();

CREATE FUNCTION protect_source_identity() RETURNS trigger LANGUAGE plpgsql
SET search_path = bene_fit, public AS $$
BEGIN
    IF ROW(OLD.src_cd, OLD.ext_id, OLD.type_cd) IS DISTINCT FROM ROW(NEW.src_cd, NEW.ext_id, NEW.type_cd) THEN
        RAISE EXCEPTION 'Source identity is immutable';
    END IF;
    IF OLD.benefit_id IS DISTINCT FROM NEW.benefit_id AND (
        EXISTS (SELECT 1 FROM aply_round WHERE src_record_id = OLD.id)
        OR EXISTS (SELECT 1 FROM doc d JOIN src_snapshot s ON s.id = d.src_snapshot_id WHERE s.src_record_id = OLD.id)
        OR EXISTS (SELECT 1 FROM benefit_ver_src v JOIN src_snapshot s ON s.id = v.src_snapshot_id WHERE s.src_record_id = OLD.id)
    ) THEN RAISE EXCEPTION 'Used source mappings require an explicit migration, not reassignment'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER source_identity BEFORE UPDATE ON src_record
FOR EACH ROW EXECUTE FUNCTION protect_source_identity();

CREATE FUNCTION protect_run_identity() RETURNS trigger LANGUAGE plpgsql
SET search_path = bene_fit, public AS $$
BEGIN
    IF ROW(OLD.src_cd, OLD.ds_nm) IS DISTINCT FROM ROW(NEW.src_cd, NEW.ds_nm) THEN
        RAISE EXCEPTION 'Collection run provider_cd and ds_nm are immutable';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER run_identity BEFORE UPDATE ON ingest_run
FOR EACH ROW EXECUTE FUNCTION protect_run_identity();
COMMIT;
