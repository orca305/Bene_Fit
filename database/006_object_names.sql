-- Match AURORE prefixes for constraints and indexes; no business row changes.
BEGIN;
SET LOCAL search_path=bene_fit,public;
DO $$ DECLARE c record; cols text; label text; prefix text; BEGIN
    FOR c IN SELECT x.*,r.relname FROM pg_constraint x JOIN pg_class r ON r.oid=x.conrelid
        JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='bene_fit' AND x.contype IN ('p','u','f','c')
    LOOP
        SELECT string_agg(a.attname,'_' ORDER BY k.ord) INTO cols FROM unnest(c.conkey) WITH ORDINALITY k(num,ord)
        JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.num;
        prefix := CASE c.contype WHEN 'p' THEN 'pk' WHEN 'u' THEN 'uq' WHEN 'f' THEN 'fk' ELSE 'ck' END;
        IF c.contype='p' THEN label := 'pk_'||c.relname;
        ELSE label := left(prefix||'_'||c.relname||'_'||coalesce(cols,'rule'),54)||'_'||substr(md5(pg_get_constraintdef(c.oid)),1,8); END IF;
        IF c.conname!=label THEN EXECUTE format('ALTER TABLE bene_fit.%I RENAME CONSTRAINT %I TO %I',c.relname,c.conname,label); END IF;
    END LOOP;
    FOR c IN SELECT i.*,t.relname AS table_name,x.relname AS index_name FROM pg_index i
        JOIN pg_class t ON t.oid=i.indrelid JOIN pg_class x ON x.oid=i.indexrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='bene_fit'
        AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid=i.indexrelid)
    LOOP
        SELECT string_agg(a.attname,'_' ORDER BY k.ord) INTO cols FROM unnest(c.indkey) WITH ORDINALITY k(num,ord)
        JOIN pg_attribute a ON a.attrelid=c.indrelid AND a.attnum=k.num;
        prefix := CASE WHEN c.indisunique THEN 'uq' ELSE 'idx' END;
        label := left(prefix||'_'||c.table_name||'_'||coalesce(cols,'expr'),54)||'_'||substr(md5(c.indkey::text||coalesce(pg_get_expr(c.indexprs,c.indrelid),'')||coalesce(pg_get_expr(c.indpred,c.indrelid),'')),1,8);
        IF c.index_name!=label THEN EXECUTE format('ALTER INDEX bene_fit.%I RENAME TO %I',c.index_name,label); END IF;
    END LOOP;
END $$;
COMMIT;
