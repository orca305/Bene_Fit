"""Read-only checks of migrated PostgreSQL and its real HTTP catalog/detail routes."""
from contextlib import closing
import json
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen
from pg_db import ROOT, connect
from pg_catalog import records, coverage
from serve_catalog import Handler


def main():
    with closing(sqlite3.connect((ROOT/'data/normalized/catalog.sqlite').as_uri()+'?mode=ro',uri=True)) as sqlite:
        original={rid:json.loads(raw) for rid,raw in sqlite.execute('SELECT id,record FROM benefits')}
    with connect() as db:
        migrated={row['id']:row for row in records(db)}
        assert migrated==original
    assert coverage()['indexed_chunks']==0 and coverage()['model'] is None
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    def get(path):
        try: response=urlopen(base+path,timeout=60)
        except HTTPError as error: response=error
        with response:return response.status,response.read().decode('utf-8')
    try:
        assert get('/')[0]==200
        status,body=get('/api/catalog');assert status==200
        actual=json.loads(body)['records']
        fields=('name','agency','category','summary','target','criteria','benefit','region','district','life_stage')
        expected=[]
        for rid in sorted(original):
            row=original[rid]
            expected.append({k:row.get(k) for k in ('id','source','review_group','detail_available')} | {
                'fields':{k:v for k,v in row['fields'].items() if k in fields},
                'source_condition_codes':{k:v for k,v in row.get('source_condition_codes',{}).items() if k in ('JA0110','JA0111')}})
        assert actual==expected
        rid=sorted(original)[0]
        assert get('/benefit?'+urlencode({'id':rid}))[0]==200
        assert get('/benefit?id=missing')[0]==404
        assert get('/.env.postgres')[0]==404
        assert get('/api/semantic?purpose=birth')[0]==503
        assert get('/api/semantic?purpose=birth&age=30')[0]==400
        status,payload=get('/api/embedding-status')
        assert status==200 and json.loads(payload)['coverage']['backend']=='postgresql'
        assert json.loads(payload)['coverage']['indexed_chunks']==0
    finally:
        server.shutdown();server.server_close();thread.join()
    print('PostgreSQL: all catalog records equal SQLite; real HTTP catalog, detail, privacy and vector-pending checks passed')


if __name__=='__main__':main()
