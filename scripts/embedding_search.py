"""Resumable local BGE-M3 indexing and evidence retrieval (no eligibility decisions)."""
import argparse
from contextlib import closing, contextmanager
import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import threading

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / 'data/knowledge/knowledge.sqlite'
INDEX = ROOT / 'data/knowledge/embeddings.sqlite'
CONFIG = json.loads((ROOT / 'config/embedding.json').read_text(encoding='utf-8-sig'))
SIGNATURE = hashlib.sha256(json.dumps(CONFIG, sort_keys=True).encode()).hexdigest()
PROGRESS = ROOT / 'data/knowledge/embedding-progress.json'
MODEL_LOCK = threading.Lock()


@contextmanager
def build_lock():
    """One writer across refresh and embedding, released by the OS on process exit."""
    lock_path = INDEX.with_suffix('.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0: stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError('Another data refresh or embedding build is running.') from error
        try:
            # The initial long-running build predates this lock. Respect its real process too.
            if INDEX == ROOT / 'data/knowledge/embeddings.sqlite' and PROGRESS.exists():
                progress = json.loads(PROGRESS.read_text(encoding='utf-8'))
                if progress.get('running') and progress.get('pid') != os.getpid():
                    import psutil
                    try:
                        process = psutil.Process(progress['pid'])
                        command = process.cmdline()
                        if ('build' in command and any(Path(arg).name == 'embedding_search.py' for arg in command)
                                and Path(process.cwd()).resolve() == ROOT.resolve()):
                            raise RuntimeError('The existing embedding build is still running; wait before refreshing data.')
                    except psutil.NoSuchProcess:
                        pass
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt': msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(stream, fcntl.LOCK_UN)


def open_index(path=INDEX):
    db = sqlite3.connect(Path(path).resolve().as_uri(), uri=True)
    db.execute('CREATE TABLE IF NOT EXISTS settings (signature TEXT NOT NULL)')
    row = db.execute('SELECT signature FROM settings').fetchone()
    if row and row[0] != SIGNATURE:
        db.close()
        raise ValueError('Embedding configuration changed; use a separate index or rebuild explicitly.')
    if not row:
        db.execute('INSERT INTO settings VALUES (?)', (SIGNATURE,))
    db.execute('''CREATE TABLE IF NOT EXISTS vectors
        (chunk_id TEXT PRIMARY KEY, input_sha256 TEXT NOT NULL, vector BLOB NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS vectors_input_hash ON vectors(input_sha256)')
    db.commit()
    return db


def current_chunks(db):
    db.execute('ATTACH DATABASE ? AS knowledge', (KNOWLEDGE.as_uri() + '?mode=ro',))
    return '''FROM knowledge.chunks c JOIN knowledge.documents d ON d.id=c.document_id
              LEFT JOIN vectors v ON v.chunk_id=c.id
              WHERE d.current=1 AND c.field!='source_condition_codes' '''


@lru_cache(maxsize=1)
def model():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(CONFIG['threads'])
    encoder = SentenceTransformer(str(ROOT / CONFIG['local_directory']), device=CONFIG['device'],
        local_files_only=True, trust_remote_code=False,
        model_kwargs={'dtype': torch.float32, 'attn_implementation': 'sdpa'})
    encoder.max_seq_length = CONFIG['max_sequence_length']
    return encoder


def encode(encoder, texts, prompt):
    import numpy as np
    texts = [prompt + text for text in texts]
    lengths = encoder.tokenizer(texts, truncation=False)['input_ids']
    if any(len(ids) > CONFIG['max_sequence_length'] for ids in lengths):
        raise ValueError('Input too long; refusing silent truncation')
    vectors = encoder.encode(texts, prompt='', normalize_embeddings=True,
        batch_size=CONFIG['batch_size'], show_progress_bar=False, convert_to_numpy=True)
    vectors = np.asarray(vectors, dtype='<f4')
    validate(vectors)
    return vectors


def validate(vectors):
    import numpy as np
    if vectors.ndim != 2 or vectors.shape[1] != CONFIG['dimensions'] or not np.isfinite(vectors).all():
        raise ValueError('Invalid embedding shape or values')
    if not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4):
        raise ValueError('Embeddings must be normalized')


def build(limit):
    with build_lock():
        build_locked(limit)


def build_locked(limit):
    with closing(open_index()) as db:
        base = current_chunks(db)
        rows = db.execute('SELECT c.id,c.retrieval_text ' + base +
            ' AND v.chunk_id IS NULL ORDER BY CASE c.field WHEN \'target\' THEN 0 WHEN \'criteria\' THEN 1 ELSE 2 END,c.id LIMIT ?',
            (limit if limit else -1,)).fetchall()
        if not rows:
            print('No pending chunks'); return
        started = time.time()
        progress = {'pid': os.getpid(), 'running': True, 'started_at': started,
                    'run_total': len(rows), 'run_completed': 0, 'phase': 'encoding',
                    'generated_chunks': 0, 'reused_chunks': 0}
        def save_progress():
            if INDEX != ROOT / 'data/knowledge/embeddings.sqlite': return
            progress['updated_at'] = time.time()
            temp = PROGRESS.with_suffix('.tmp')
            temp.write_text(json.dumps(progress), encoding='utf-8')
            temp.replace(PROGRESS)
        save_progress()
        try:
            encoder = None
            for start in range(0, len(rows), 16):
                block = rows[start:start + 16]
                inputs = [(cid, hashlib.sha256(text.encode()).hexdigest(), text) for cid, text in block]
                available, missing = {}, {}
                for _, hashed, text in inputs:
                    cached = db.execute('SELECT vector FROM vectors WHERE input_sha256=? LIMIT 1', (hashed,)).fetchone()
                    if cached:
                        import numpy as np
                        validate(np.frombuffer(cached[0], dtype='<f4').reshape(1, -1))
                        available[hashed] = cached[0]
                    else:
                        missing[hashed] = text
                if missing:
                    if encoder is None: encoder = model()
                    vectors = encode(encoder, list(missing.values()), CONFIG['document_prompt'])
                    available.update((hashed, vector.tobytes()) for hashed, vector in zip(missing, vectors))
                generated = len(missing)
                with db:
                    db.executemany('INSERT INTO vectors VALUES (?,?,?)',
                        [(cid, hashed, available[hashed]) for cid, hashed, _ in inputs])
                progress['generated_chunks'] += generated
                progress['reused_chunks'] += len(block) - generated
                progress['run_completed'] = min(start + 16, len(rows))
                progress['elapsed_seconds'] = round(time.time() - started, 1)
                save_progress()
                print(f"Committed {progress['run_completed']}/{len(rows)} new chunks; elapsed {progress['elapsed_seconds']}s", flush=True)
            progress['phase'] = 'finished'
        except BaseException as error:
            progress['phase'] = 'stopped'
            progress['error_type'] = type(error).__name__
            raise
        finally:
            progress['running'] = False
            save_progress()


def status():
    with closing(open_index()) as db:
        base = current_chunks(db)
        total, ready = db.execute('SELECT count(*),count(v.chunk_id) ' + base).fetchone()
        return {'model': CONFIG['model'], 'eligible_chunks': total, 'indexed_chunks': ready,
                'pending_chunks': total-ready, 'complete': total == ready, 'eligibility_verified': False}


def search(query, limit=5):
    import numpy as np
    if not query.strip() or len(query) > 500 or not 1 <= limit <= 20:
        raise ValueError('Query needs 1-500 characters; limit must be 1-20')
    with closing(open_index()) as db:
        base = current_chunks(db)
        rows = db.execute('SELECT c.id,d.record_id,c.field,c.text,c.locator,d.metadata,v.vector,c.retrieval_text,v.input_sha256 ' +
                          base + ' AND v.chunk_id IS NOT NULL ORDER BY c.id').fetchall()
        if not rows:
            raise ValueError('No embeddings yet; run build first')
        total = db.execute('SELECT count(*) ' + base).fetchone()[0]
        coverage = {'model':CONFIG['model'], 'eligible_chunks':total, 'indexed_chunks':len(rows),
                    'pending_chunks':total-len(rows), 'complete':total==len(rows), 'eligibility_verified':False}
        for row in rows:
            if hashlib.sha256(row[7].encode()).hexdigest() != row[8]:
                raise ValueError('Stored embedding input changed')
        vectors = np.stack([np.frombuffer(row[6], dtype='<f4') for row in rows])
        validate(vectors)
        with MODEL_LOCK:
            query_vector = encode(model(), [query.strip()], CONFIG['query_prompt'])[0]
        scores = vectors @ query_vector
        results = []
        seen = set()
        for i in np.argsort(-scores, kind='stable'):
            cid, rid, field, text, locator, meta = rows[int(i)][:6]
            if rid in seen: continue
            seen.add(rid)
            results.append({'record_id': rid, 'chunk_id': cid, 'field': field, 'text': text,
                'locator': json.loads(locator), 'source': json.loads(meta), 'cosine': float(scores[i]),
                'assessment': '확인 필요'})
            if len(results) == limit: break
        return {'coverage': coverage, 'results': results}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    build_parser = sub.add_parser('build')
    build_parser.add_argument('--limit', type=int, default=0, help='0 means all pending chunks')
    search_parser = sub.add_parser('search')
    search_parser.add_argument('query')
    search_parser.add_argument('--limit', type=int, default=5)
    args = parser.parse_args()
    if args.command == 'build':
        if args.limit < 0: parser.error('limit must be nonnegative')
        build(args.limit)
        print(json.dumps(status(), ensure_ascii=False))
    else:
        print(json.dumps(status() if args.command == 'status' else search(args.query, args.limit), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
