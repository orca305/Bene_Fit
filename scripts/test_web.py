from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import embedding_search
from catalog import normalize
from serve_catalog import Handler, safe_link

def main():
    assert 'href=' not in safe_link("javascript:alert(1)","bad")
    with tempfile.TemporaryDirectory() as directory:
        database=Path(directory)/"catalog.sqlite"
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("CREATE TABLE benefits (id TEXT, review_group TEXT, source TEXT, name_key TEXT, search_text TEXT, record TEXT)")
            for i in range(25):
                r=normalize("welfare-central",{"servId":str(i),"servNm":"<script>alert(1)</script>","servDgst":"Test"})
                db.execute("INSERT INTO benefits VALUES (?,?,?,?,?,?)",(r["id"],r["review_group"],r["source"],"test","test",json.dumps(r)))
        class TestHandler(Handler):
            pass
        TestHandler.database=database
        TestHandler.use_postgres=False
        server=ThreadingHTTPServer(("127.0.0.1",0),TestHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base=f"http://127.0.0.1:{server.server_port}"
        def get(path):
            try:
                response=urlopen(base+path,timeout=5)
            except HTTPError as error:
                response=error
            with response:
                return response.status,response.read().decode(),response.headers
        try:
            status,body,headers=get("/")
            assert status==200 and body.count('<article class="benefit-card">')==0
            assert "<script>" not in body
            assert "frame-ancestors" in headers["Content-Security-Policy"]
            assert "script-src 'self'" in headers["Content-Security-Policy"]
            assert get("/my")[0]==200 and 'id="guided-search"' in get("/my")[1]
            assert get("/recommended")[0]==200 and 'id="question-controls"' in get("/recommended")[1]
            assert "text/css" in get("/styles.css")[2]["Content-Type"]
            assert "text/javascript" in get("/app.js")[2]["Content-Type"]
            assert get("/profile_crypto.js")[0]==200
            status,payload,_=get("/api/catalog")
            assert status==200 and len(json.loads(payload)["records"])==25
            assert all("income" not in r for r in json.loads(payload)["records"])
            assert 'personal-search' not in body
            assert 'api/catalog' not in body
            searched=get("/?q=test")[1]
            assert 'id="guided-search"' in searched and 'id="question-controls"' in searched
            assert 'data-query="test"' in searched
            assert get("/guided.js")[0]==200
            assert get('/progress')[0]==200 and 'embedding-meter' in get('/progress')[1]
            assert get('/progress.js')[0]==200
            with patch.object(embedding_search,'status',return_value={'indexed_chunks':32,'complete':False}), \
                 patch.object(embedding_search,'search',return_value={'coverage':{'complete':False},'results':[]}) as semantic:
                assert json.loads(get('/api/embedding-status')[1])['coverage']['indexed_chunks']==32
                assert get('/api/semantic?purpose=birth')[0]==200
                assert semantic.call_args.args==('출산 육아 양육 지원',20)
                assert get('/api/semantic?purpose=birth&age=30')[0]==400
                assert get('/api/semantic?purpose=unknown')[0]==400
                assert get('/api/semantic?q=')[0]==400
                assert get('/api/semantic?q=a&q=b')[0]==400
            assert '<article class="benefit-card">' not in searched
            assert 'data-query="&quot;&gt;' in get("/?"+urlencode({"q":'">test'}))[1]
            assert get("/?source=welfare-local")[1].count('<article class="benefit-card">')==0
            assert get("/?q=missing")[1].count('<article class="benefit-card">')==0
            assert get("/?q=%25%25")[0]==400
            assert get("/benefit?"+urlencode({"id":"welfare-central:0"}))[0]==200
            for path in ("/.env","/../.env","/data/normalized/catalog.sqlite","/benefit?id=missing"):
                assert get(path)[0]==404
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    print("Web HTTP checks passed")

if __name__=="__main__":
    main()
