"""Read the PostgreSQL public catalog while preserving the existing browser API contract."""
from pg_db import connect


def records(db, identifier=None):
    statement = 'SELECT meta_json,fld_json FROM bene_fit.current_benefit_ver WHERE true'
    args = ()
    if identifier is not None:
        statement += " AND meta_json->>'id'=%s"
        args = (identifier,)
    statement += " ORDER BY meta_json->>'id'"
    for meta, fields in db.execute(statement, args):
        yield {**meta, 'fields':fields}


def coverage():
    with connect() as db:
        total=db.execute('SELECT count(*) FROM bene_fit.current_doc_chunk WHERE emb_input_hash IS NOT NULL').fetchone()[0]
        model=db.execute('SELECT id,model_nm FROM bene_fit.emb_model WHERE act_yn AND NOT del_yn').fetchone()
        ready=0
        if model and db.execute("SELECT to_regclass('bene_fit.emb_vector')").fetchone()[0]:
            ready=db.execute('''SELECT count(*) FROM bene_fit.current_doc_chunk c JOIN bene_fit.emb_vector e
                ON e.input_hash=c.emb_input_hash WHERE e.emb_model_id=%s AND NOT e.del_yn''',(model[0],)).fetchone()[0]
        return {'model':model[1] if model else None,'eligible_chunks':total,'indexed_chunks':ready,
                'pending_chunks':total-ready,'complete':bool(model) and total==ready,
                'eligibility_verified':False,'backend':'postgresql'}
