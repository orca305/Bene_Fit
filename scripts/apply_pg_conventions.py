"""Apply AURORE naming/lifecycle to the already migrated public DB, without rebuilding rows."""
import argparse
from pathlib import Path
from pg_db import ROOT, connect


def apply(pg):
    if pg.execute("SELECT to_regclass('bene_fit.cmmn_cd')").fetchone()[0]:
        raise RuntimeError('AURORE convention migration already applied; do not run it twice')
    with pg.transaction():
        pg.execute("SELECT pg_advisory_xact_lock(hashtext('bene_fit_schema'))")
        # PL/pgSQL function bodies retain textual column names after ALTER RENAME.
        for table, trigger in pg.execute('''SELECT c.relname,t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='bene_fit' AND NOT t.tgisinternal''').fetchall():
            from psycopg import sql
            pg.execute(sql.SQL('DROP TRIGGER {} ON bene_fit.{}').format(sql.Identifier(trigger),sql.Identifier(table)))
        for signature, in pg.execute("SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='bene_fit'").fetchall():
            # Catalog-formatted signatures are trusted identifiers, never user input.
            pg.execute('DROP FUNCTION '+signature)
        pg.execute((ROOT/'database/004_aurore_names.sql').read_text(encoding='utf-8'))
        for name in ['003_rule_review.sql','005_aurore_lifecycle.sql','006_object_names.sql']:
            text=(ROOT/'database'/name).read_text(encoding='utf-8')
            # One atomic outer transaction across renames and new guards.
            text=text.replace('\nBEGIN;\n','\n').replace('\nCOMMIT;','\n')
            # The review index already exists under its original name.
            if name=='003_rule_review.sql':
                text=text.replace('CREATE UNIQUE INDEX one_approved_rule_revision','CREATE UNIQUE INDEX IF NOT EXISTS one_approved_rule_revision')
            pg.execute(text)


if __name__=='__main__':
    with connect() as pg: apply(pg)
    print('AURORE naming, common codes/history and soft-delete rules applied; original row IDs preserved')
