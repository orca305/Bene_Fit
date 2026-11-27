"""Local PostgreSQL connection; never print connection strings or credentials."""
import os
from pathlib import Path
import psycopg

ROOT = Path(__file__).resolve().parents[1]


def connect():
    values = {}
    path = ROOT / '.env.postgres'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                key, sep, value = line.partition('=')
                if not sep: raise ValueError('Invalid .env.postgres entry')
                values[key.strip()] = value.strip()
    def setting(key, fallback=''):
        return os.environ.get(key, values.get(key, fallback))
    return psycopg.connect(host=setting('PGHOST', '127.0.0.1'), port=setting('PGPORT', '55432'),
        dbname=setting('PGDATABASE', setting('POSTGRES_DB', 'bene_fit')),
        user=setting('PGUSER', setting('POSTGRES_USER', 'bene_fit')),
        password=setting('PGPASSWORD', setting('POSTGRES_PASSWORD')),
        connect_timeout=10, autocommit=True)
