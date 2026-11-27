"""Check resumability, current-version filtering, evidence joins and configuration isolation."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch
import numpy as np
import embedding_search as app
import refresh_search

encoded_texts = []


def fake_encode(encoder, texts, prompt):
    encoded_texts.extend(texts)
    result = np.zeros((len(texts), app.CONFIG['dimensions']), dtype='<f4')
    result[:, 0] = 1
    return result


with tempfile.TemporaryDirectory() as folder:
    index = Path(folder) / 'vectors.sqlite'
    knowledge = Path(folder) / 'knowledge.sqlite'
    with closing(sqlite3.connect(knowledge)) as db:
        db.executescript('''CREATE TABLE documents(id TEXT,record_id TEXT,current INTEGER,metadata TEXT);
            CREATE TABLE chunks(id TEXT,document_id TEXT,field TEXT,text TEXT,retrieval_text TEXT,locator TEXT);''')
        db.executemany('INSERT INTO documents VALUES (?,?,?,?)',
            [('current','program:1',1,json.dumps({'name':'Test'})), ('old','program:1',0,'{}')])
        db.executemany('INSERT INTO chunks VALUES (?,?,?,?,?,?)',
            [('a','current','target','source evidence','retrieval evidence','{}'),
             ('b','current','summary','summary','retrieval summary','{}'),
             ('code','current','source_condition_codes','code','code','{}'),
             ('stale','old','target','old','old','{}')])
        db.commit()
    original_open = app.open_index
    with patch.object(app,'KNOWLEDGE',knowledge), patch.object(app,'INDEX',index), patch.object(app,'open_index',lambda:original_open(index)), \
         patch.object(app,'model',lambda:None), patch.object(app,'encode',fake_encode):
        assert app.status()['eligible_chunks'] == 2
        app.build(1)
        assert app.status()['indexed_chunks'] == 1
        app.build(1)
        app.build(1)
        assert app.status()['complete']
        results = app.search('test')['results']
        assert {r['chunk_id'] for r in results} == {'a'}
        assert results[0]['text'] == 'source evidence'
        assert all(r['record_id']=='program:1' and r['assessment']=='확인 필요' for r in results)
        # A metadata/field update changes chunk IDs but must not re-encode identical text.
        with closing(sqlite3.connect(knowledge)) as db:
            db.execute('UPDATE documents SET current=0')
            db.execute('INSERT INTO documents VALUES (?,?,?,?)',('new','program:1',1,json.dumps({'name':'Changed'})))
            db.executemany('INSERT INTO chunks VALUES (?,?,?,?,?,?)',[
                ('a2','new','target','source evidence','retrieval evidence','{}'),
                ('b2','new','summary','new summary','changed summary','{}')])
            db.commit()
        encoded_texts.clear()
        app.build(0)
        assert encoded_texts == ['changed summary'], encoded_texts
        assert app.status()['indexed_chunks']==2 and app.status()['complete']
        assert app.search('test')['results'][0]['chunk_id']=='a2'
        with app.build_lock():
            try: app.build(1)
            except RuntimeError: pass
            else: raise AssertionError('Concurrent build accepted')
        with patch.object(app,'SIGNATURE','different'):
            try: original_open(index)
            except ValueError: pass
            else: raise AssertionError('Changed configuration accepted')
        steps=[]
        with patch.object(refresh_search.catalog,'build',lambda:steps.append('catalog')), \
             patch.object(refresh_search.build_condition_drafts,'main',lambda:steps.append('conditions')), \
             patch.object(refresh_search.build_knowledge,'build',lambda:steps.append('knowledge')), \
             patch.object(app,'build_locked',lambda limit:steps.append(('embedding',limit))):
            assert refresh_search.refresh(7)['complete']
            assert steps==['catalog','conditions','knowledge',('embedding',7)]
        with patch.object(refresh_search.catalog,'build',side_effect=RuntimeError('incomplete source')), \
             patch.object(refresh_search.build_knowledge,'build') as chunks:
            try: refresh_search.refresh()
            except RuntimeError: pass
            else: raise AssertionError('Refresh continued after source failure')
            chunks.assert_not_called()
print('embedding search checks passed')
