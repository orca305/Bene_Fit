-- Transaction is managed by apply_pg_conventions.py.
SET LOCAL search_path=bene_fit,public;
DROP VIEW IF EXISTS bene_fit.current_chunks;
DROP VIEW IF EXISTS bene_fit.current_doc_chunk;
ALTER TABLE IF EXISTS bene_fit.src RENAME TO data_src;
ALTER TABLE IF EXISTS bene_fit.src_rec RENAME TO src_record;
ALTER TABLE IF EXISTS bene_fit.src_snap RENAME TO src_snapshot;
ALTER TABLE IF EXISTS bene_fit.prgm RENAME TO benefit;
ALTER TABLE IF EXISTS bene_fit.prgm_ver RENAME TO benefit_ver;
ALTER TABLE IF EXISTS bene_fit.ver_src RENAME TO benefit_ver_src;
ALTER TABLE IF EXISTS bene_fit.aply_rnd RENAME TO aply_round;
ALTER TABLE IF EXISTS bene_fit.qstn RENAME TO question;
ALTER TABLE IF EXISTS bene_fit.rule_evd RENAME TO rule_evidence;
ALTER TABLE IF EXISTS bene_fit.rule_qstn RENAME TO rule_question;
ALTER TABLE IF EXISTS bene_fit.emb_inp RENAME TO emb_input;
ALTER TABLE IF EXISTS bene_fit.emb_mdl RENAME TO emb_model;
ALTER TABLE IF EXISTS bene_fit.emb_vec RENAME TO emb_vector;
DO $$ DECLARE t record; c record; BEGIN
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='bene_fit' LOOP
  FOR c IN SELECT key,value FROM jsonb_each_text('{"crt_at": "rgst_dttm", "start_at": "start_dttm", "end_at": "end_dttm", "fst_seen_at": "first_seen_dttm", "lst_seen_at": "last_seen_dttm", "src_mod_at": "src_mod_dttm", "fetch_at": "fetch_dttm", "obs_at": "obs_dttm", "pub_at": "pub_dttm", "aply_start_at": "aply_start_dttm", "aply_end_at": "aply_end_dttm", "rvw_at": "review_dttm", "gen_at": "gen_dttm", "eff_from": "eff_start_dt", "eff_to": "eff_end_dt", "is_use": "use_yn", "is_cur": "current_yn", "is_prd_vrf": "period_verify_yn", "is_geo_vrf": "geo_verify_yn", "is_cmp": "compare_yn", "is_opt": "optional_yn", "is_norm": "norm_yn", "is_act": "act_yn", "stts": "stat_cd", "map_stts": "map_stat_cd", "seen_stts": "presence_stat_cd", "typ": "type_cd", "repr_typ": "repr_type_cd", "prd_typ": "period_type_cd", "doc_typ": "doc_type_cd", "val_typ": "value_type_cd", "cov_typ": "coverage_cd", "subj_role": "subj_role_cd", "geo_scope": "geo_scope_cd", "par_id": "prnt_id", "ord_no": "sort_seq", "prgm_id": "benefit_id", "prgm_ver_id": "benefit_ver_id", "src_rec_id": "src_record_id", "snap_id": "src_snapshot_id", "rnd_id": "aply_round_id", "node_id": "rule_node_id", "qstn_id": "question_id", "mdl_id": "emb_model_id", "emb_inp_hash": "emb_input_hash", "inp_hash": "input_hash", "inp_txt": "input_cont", "raw_txt": "src_cont", "body_txt": "chunk_cont", "quote_txt": "quote_cont", "help_txt": "help_cont", "smry": "summary_cont", "prvdr_cd": "provider_cd", "mdl_nm": "model_nm", "mdl_rev": "model_rev", "cfg_hash": "config_hash"}'::jsonb) LOOP

   IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='bene_fit' AND table_name=t.tablename AND column_name=c.key) THEN
    EXECUTE format('ALTER TABLE bene_fit.%I RENAME COLUMN %I TO %I',t.tablename,c.key,c.value);
   END IF;
  END LOOP;
 END LOOP;
END $$;
