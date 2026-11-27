"""Copy public SQLite snapshots to abbreviated PostgreSQL tables without changing source files."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import subprocess
import uuid
from psycopg import sql
from psycopg.types.json import Jsonb
from pg_db import ROOT, connect

OUT = ROOT / 'data/migration'
KNOWLEDGE = ROOT / 'data/knowledge/knowledge.sqlite'
CATALOG = ROOT / 'data/normalized/catalog.sqlite'
NS = uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/orca305/Bene_Fit')


def uid(kind, value):
    return uuid.uuid5(NS, kind + ':' + value)


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def source_db(path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)


def copy_rows(pg, table, columns, rows):
    statement = sql.SQL('COPY bene_fit.{} ({}) FROM STDIN').format(sql.Identifier(table),
        sql.SQL(',').join(map(sql.Identifier, columns.split(','))))
    count = 0
    with pg.cursor() as cursor, cursor.copy(statement) as stream:
        for row in rows:
            stream.write_row(tuple(Jsonb(v) if isinstance(v, (dict, list)) else v for v in row))
            count += 1
    print(f'{table}: {count}', flush=True)
    return count


def initialize(pg):
    if pg.execute("SELECT to_regnamespace('bene_fit')").fetchone()[0] is None:
        for name in ('001_core.sql', '003_rule_review.sql', '005_aurore_lifecycle.sql', '006_object_names.sql'):
            pg.execute((ROOT / 'database' / name).read_text(encoding='utf-8'))
    elif pg.execute("SELECT to_regclass('bene_fit.src_record')").fetchone()[0] is None:
        raise RuntimeError('An incompatible schema exists; migrate it explicitly instead of overwriting it')


def copy_data(pg):
    initialize(pg)
    if pg.execute('SELECT count(*) FROM bene_fit.src_record').fetchone()[0]:
        raise RuntimeError('Target already contains records; use --verify. No tables were erased.')
    subprocess.run(['node', str(ROOT/'scripts/export_question_bank.cjs')],cwd=ROOT,check=True)
    now = dt.datetime.now(dt.timezone.utc)
    with closing(source_db(CATALOG)) as cat, closing(source_db(KNOWLEDGE)) as kb:
        records = {rid: json.loads(raw) for rid, raw in cat.execute('SELECT id,record FROM benefits')}
        docs = [(doc, rid, version, current, json.loads(meta)) for doc, rid, version, current, meta in
                kb.execute('SELECT id,record_id,version_hash,current,metadata FROM documents')]
        if set(records) != {rid for _, rid, _, _, _ in docs}:
            raise ValueError('Catalog and knowledge records differ')
        labels = {'gov24':'정부24', 'welfare-central':'복지로 중앙부처', 'welfare-local':'복지로 지자체',
                  'myhome':'마이홈 임대주택 공고', 'lh-notice':'LH 임대 공고'}
        housing = {}
        for provider in ('myhome', 'lh-notice'):
            housing[provider] = json.loads((ROOT / 'data/collection' / provider / 'catalog.json').read_text(encoding='utf-8'))
        counts = Counter(r['source'] for r in records.values())
        counts.update({s:len(rows) for s, rows in housing.items()})
        run_ids = {s:uid('run', s + ':sqlite-import-v1') for s in labels}
        from check_apis import settings
        secrets = [value for value in settings().values() if value]
        stats = {}
        with pg.transaction():
            stats['data_src'] = copy_rows(pg, 'data_src', 'cd,nm', labels.items())
            stats['ingest_run'] = copy_rows(pg, 'ingest_run', 'id,src_cd,ds_nm,start_dttm,end_dttm,stat_cd,fetch_cnt',
                ((run_ids[s], s, 'sqlite-import-v1', now, now, 'complete', counts[s]) for s in labels))
            stats['benefit'] = copy_rows(pg, 'benefit', 'id', ((uid('program', rid),) for rid in records))
            groups = {}
            for provider, rows in housing.items():
                by_id = defaultdict(list)
                for row in rows:
                    if provider == 'myhome':
                        key = f"{row['pblancId']}:{row['houseSn']}"
                    else:
                        key = ':'.join(str(row.get(k, '')) for k in
                            ('PAN_ID','UPP_AIS_TP_CD','AIS_TP_CD','SPL_INF_TP_CD','CCR_CNNT_SYS_DS_CD'))
                    by_id[key].append(row)
                groups[provider] = by_id
            def source_records():
                for rid, r in records.items():
                    yield (uid('record',rid),r['source'],r['source_id'],'program',uid('program',rid),rid)
                for provider, by_id in groups.items():
                    for key in by_id:
                        yield (uid('notice',provider+':'+key),provider,key,'notice',None,None)
            stats['src_record'] = copy_rows(pg, 'src_record', 'id,src_cd,ext_id,type_cd,benefit_id,old_rec_id',source_records())
            def snapshots():
                for doc, rid, hashed, _, meta in docs:
                    snapshot = json.loads(kb.execute('SELECT snapshot FROM documents WHERE id=?',(doc,)).fetchone()[0])
                    if digest(packed(snapshot)) != hashed: raise ValueError('Source snapshot hash mismatch')
                    # Fail closed if an API credential somehow appears in public snapshots.
                    public = packed(snapshot)
                    if any(secret in public for secret in secrets):
                        raise ValueError('An API credential was found in a snapshot; import stopped')
                    yield (uid('snapshot',doc),uid('record',rid),run_ids[records[rid]['source']],hashed,snapshot,
                           meta.get('source_url'),meta.get('detail_checked_at') or meta.get('checked_at') or now)
                for provider, by_id in groups.items():
                    for key, rows in by_id.items():
                        payload = {'rows':rows, 'source':provider, 'mapping_status':'unreviewed'}
                        yield (uid('notice-snapshot',provider+':'+key),uid('notice',provider+':'+key),run_ids[provider],
                            digest(packed(payload)),payload,None,now)
            stats['src_snapshot'] = copy_rows(pg, 'src_snapshot',
                'id,src_record_id,run_id,cont_hash,raw_json,src_url,fetch_dttm', snapshots())
            def versions():
                for doc, rid, hashed, current, meta in docs:
                    r=records[rid]; fields=r['fields']
                    source_meta={k:v for k,v in r.items() if k!='fields'}
                    yield (uid('version',doc),uid('program',rid),hashed,fields.get('name') or rid,
                        fields.get('agency'),fields.get('category'),fields.get('summary'),fields,source_meta,
                        r.get('source_condition_codes',{}),bool(current),meta.get('checked_at') or now)
            stats['benefit_ver'] = copy_rows(pg, 'benefit_ver',
                'id,benefit_id,cont_hash,nm,org_nm,cat_cd,summary_cont,fld_json,meta_json,src_cond_json,current_yn,obs_dttm',versions())
            stats['benefit_ver_src'] = copy_rows(pg, 'benefit_ver_src', 'benefit_ver_id,src_snapshot_id,fld_map_json',
                ((uid('version',doc),uid('snapshot',doc),records[rid].get('provenance',{})) for doc,rid,_,_,_ in docs))
            stats['doc'] = copy_rows(pg, 'doc',
                'id,benefit_ver_id,src_snapshot_id,old_doc_id,parse_ver,cont_hash,fld_json,meta_json',
                ((uid('document',doc),uid('version',doc),uid('snapshot',doc),doc,meta.get('pipeline','knowledge-v1'),hashed,
                  json.loads(kb.execute('SELECT fields FROM documents WHERE id=?',(doc,)).fetchone()[0]),meta)
                 for doc,_,hashed,_,meta in docs))
            inputs = {}
            for field, text in kb.execute('SELECT field,retrieval_text FROM chunks'):
                if field != 'source_condition_codes': inputs.setdefault(digest(text),text)
            stats['emb_input'] = copy_rows(pg,'emb_input','input_hash,input_cont',inputs.items())
            stats['doc_chunk'] = copy_rows(pg,'doc_chunk',
                'id,doc_id,fld_nm,start_pos,end_pos,chunk_cont,loc_json,split_ver,emb_input_hash',
                ((cid,uid('document',doc),field,start,end,text,json.loads(locator),'knowledge-v1',
                  digest(retrieval) if field!='source_condition_codes' else None)
                 for cid,doc,field,start,end,text,retrieval,locator in kb.execute(
                    'SELECT id,document_id,field,start,end,text,retrieval_text,locator FROM chunks')))
            stats['rule_set'] = copy_rows(pg,'rule_set','id,benefit_ver_id,rev_no,rvw_note',
                ((uid('rules',group),uid('version',doc),1,packed({'legacy_group_id':group,'relation_evidence':json.loads(evidence)}))
                 for group,doc,evidence in kb.execute('SELECT id,document_id,relation_evidence FROM condition_groups')))
            def nodes():
                for group,doc in kb.execute('SELECT id,document_id FROM condition_groups'):
                    yield (uid('rule-root',group),uid('rules',group),None,'unresolved',None,{'legacy_group_id':group})
                for cid,group,payload in kb.execute('SELECT id,group_id,payload FROM condition_drafts'):
                    yield (uid('condition',cid),uid('rules',group),uid('rule-root',group),'condition','unresolved',json.loads(payload))
            stats['rule_node'] = copy_rows(pg,'rule_node','id,rule_set_id,prnt_id,type_cd,subj_role_cd,draft_json',nodes())
            def evidence():
                for cid,group,raw in kb.execute('SELECT id,group_id,payload FROM condition_drafts'):
                    payload=json.loads(raw)
                    for chunk in set(payload.get('evidence_chunk_ids',[])):
                        row=kb.execute('SELECT text,start FROM chunks WHERE id=?',(chunk,)).fetchone()
                        if not row:raise ValueError('Missing condition evidence')
                        text,chunk_start=row
                        location=payload.get('locator') or {}
                        start=location.get('start');end=location.get('end')
                        # Exact numeric spans are kept; topic hints cite the entire linked chunk.
                        if isinstance(start,int) and isinstance(end,int) and chunk_start<=start<end<=chunk_start+len(text):
                            start,end=start-chunk_start,end-chunk_start
                        else:start,end=0,len(text)
                        yield (uid('condition',cid),uid('rules',group),chunk,start,end,text[start:end])
            stats['rule_evidence'] = copy_rows(pg,'rule_evidence','rule_node_id,rule_set_id,chunk_id,start_pos,end_pos,quote_cont',evidence())
            bank_path=OUT/'question_bank.json'
            if bank_path.exists():
                bank=json.loads(bank_path.read_text(encoding='utf-8'))
                stats['question']=copy_rows(pg,'question','id,rev_no,subj_role_cd,qstn_txt,help_cont,opt_json',
                    ((q['id'],1,q['subject'],q['title'],q['why'],q['options']) for q in bank))
        return stats


def verify(pg):
    with closing(source_db(KNOWLEDGE)) as kb, closing(source_db(CATALOG)) as cat:
        expected={'benefit':cat.execute('SELECT count(*) FROM benefits').fetchone()[0],
                  'doc':kb.execute('SELECT count(*) FROM documents').fetchone()[0],
                  'doc_chunk':kb.execute('SELECT count(*) FROM chunks').fetchone()[0],
                  'rule_set':kb.execute('SELECT count(*) FROM condition_groups').fetchone()[0],
                  'rule_node':kb.execute('SELECT count(*) FROM condition_groups').fetchone()[0]+kb.execute('SELECT count(*) FROM condition_drafts').fetchone()[0]}
        actual={table:pg.execute(sql.SQL('SELECT count(*) FROM bene_fit.{}').format(sql.Identifier(table))).fetchone()[0] for table in expected}
        if actual!=expected:raise ValueError(f'Row counts differ: {actual} != {expected}')
        originals={rid:json.loads(raw) for rid,raw in cat.execute('SELECT id,record FROM benefits')}
        for rid,fields,meta in pg.execute('SELECT r.old_rec_id,v.fld_json,v.meta_json FROM bene_fit.benefit_ver v JOIN bene_fit.src_record r ON r.benefit_id=v.benefit_id WHERE v.current_yn'):
            original=originals[rid]
            if fields!=original['fields'] or meta!={k:v for k,v in original.items() if k!='fields'}:
                raise ValueError('Normalized record or metadata changed during migration')
        for snapshot,hashed in pg.execute("SELECT raw_json,cont_hash FROM bene_fit.src_snapshot"):
            if digest(packed(snapshot))!=hashed:raise ValueError('PostgreSQL snapshot content hash changed')
        chunks={cid:(doc,field,start,end,text,json.loads(locator),retrieval) for cid,doc,field,start,end,text,locator,retrieval in
            kb.execute('SELECT id,document_id,field,start,end,text,locator,retrieval_text FROM chunks')}
        for cid,doc,field,start,end,body,locator,inp in pg.execute('''SELECT c.id,d.old_doc_id,c.fld_nm,c.start_pos,c.end_pos,c.chunk_cont,c.loc_json,i.input_cont
            FROM bene_fit.doc_chunk c JOIN bene_fit.doc d ON d.id=c.doc_id LEFT JOIN bene_fit.emb_input i ON i.input_hash=c.emb_input_hash'''):
            old=chunks[cid]
            if (doc,field,start,end,body,locator)!=old[:6] or (field!='source_condition_codes' and inp!=old[6]):
                raise ValueError('Chunk content or provenance changed during migration')
        bad=pg.execute('''SELECT count(*) FROM bene_fit.rule_evidence e JOIN bene_fit.doc_chunk c ON c.id=e.chunk_id
            WHERE substring(c.chunk_cont FROM e.start_pos+1 FOR e.end_pos-e.start_pos)!=e.quote_cont''').fetchone()[0]
        conditions={cid:json.loads(raw) for cid,raw in kb.execute('SELECT id,payload FROM condition_drafts')}
        for payload, in pg.execute("SELECT draft_json FROM bene_fit.rule_node WHERE type_cd='condition'"):
            if payload!=conditions[payload['id']]:raise ValueError('Condition draft payload changed during migration')
        housing_counts={}
        for provider in ('myhome','lh-notice'):
            original=json.loads((ROOT/'data/collection'/provider/'catalog.json').read_text(encoding='utf-8'))
            copied=[]
            for payload, in pg.execute('''SELECT s.raw_json FROM bene_fit.src_snapshot s JOIN bene_fit.src_record r ON r.id=s.src_record_id
                WHERE r.src_cd=%s AND r.type_cd='notice' ''',(provider,)):
                copied.extend(payload['rows'])
            if Counter(map(packed,copied))!=Counter(map(packed,original)):
                raise ValueError('Raw housing notice rows changed or were lost')
            housing_counts[provider]=len(copied)
        approved=pg.execute("SELECT count(*) FROM bene_fit.rule_set WHERE stat_cd!='draft'").fetchone()[0]
        models=pg.execute('SELECT count(*) FROM bene_fit.emb_model').fetchone()[0]
        if bad or approved or models:raise ValueError('Invalid evidence or unexpectedly approved rules/models')
        return {'status':'passed','counts':actual,'housing_rows':housing_counts,'bad_evidence':bad,'approved_rules':approved,'embedding_models':models,
                'checks':['all normalized fields and metadata','all snapshot hashes','all chunks and exact offsets','all evidence quotations','all condition payloads','all housing raw rows'],
                'postgres_version':pg.execute('SHOW server_version').fetchone()[0]}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with connect() as pg:
        stats={} if args.verify else copy_data(pg)
        report=verify(pg)
        report['table_counts']={name:pg.execute(sql.SQL('SELECT count(*) FROM bene_fit.{}').format(sql.Identifier(name))).fetchone()[0]
            for name, in pg.execute("SELECT tablename FROM pg_tables WHERE schemaname='bene_fit'").fetchall()}
        previous=OUT/'postgres-report.json'
        previous_stats=json.loads(previous.read_text(encoding='utf-8')).get('imported_counts',{}) if previous.exists() else {}
        renamed=json.loads((ROOT/'database/aurore_name_map.json').read_text(encoding='utf-8'))['tables']
        report['imported_counts']=stats or {renamed.get(name,name):count for name,count in previous_stats.items()}
        (OUT/'postgres-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
