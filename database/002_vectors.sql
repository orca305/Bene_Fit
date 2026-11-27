-- Optional: install after selecting the desktop vec_val model and pgvector.
-- The core schema does not require this extension or any downloaded model.
BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;
SET LOCAL search_path = bene_fit, public;
CREATE TABLE emb_vector (
    emb_model_id uuid NOT NULL,
    input_hash text NOT NULL REFERENCES emb_input(input_hash),
    dim_cnt integer NOT NULL,
    vec_val vector NOT NULL,
    gen_dttm timestamptz NOT NULL DEFAULT now(),
    rgst_id bigint,
    rgst_dttm timestamptz NOT NULL DEFAULT date_trunc('second',CURRENT_TIMESTAMP),
    upt_id bigint,
    upt_dttm timestamptz NOT NULL DEFAULT date_trunc('second',CURRENT_TIMESTAMP),
    del_yn boolean NOT NULL DEFAULT false,
    del_dttm timestamptz,
    del_id bigint,
    PRIMARY KEY (emb_model_id, input_hash),
    FOREIGN KEY (emb_model_id, dim_cnt) REFERENCES emb_model(id, dim_cnt),
    CHECK (vector_dims(vec_val) = dim_cnt)
);
CREATE TRIGGER trg_audit BEFORE INSERT OR UPDATE ON emb_vector FOR EACH ROW EXECUTE FUNCTION maintain_audit();
CREATE TRIGGER trg_no_delete BEFORE DELETE ON emb_vector FOR EACH ROW EXECUTE FUNCTION reject_physical_delete();
-- Always filter by emb_model_id and current_doc_chunk before comparing vectors.
-- Add a model-specific ANN index only after dimension and precision are selected.
COMMIT;
