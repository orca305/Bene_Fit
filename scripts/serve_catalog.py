"""Local read-only benefits browser. Run: python scripts/serve_catalog.py"""
import argparse
from contextlib import closing
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import psycopg
from urllib.parse import parse_qs, urlencode, urlsplit

from catalog import OUTPUT, norm
from profile_ui import profile_body, recommended_body
from guided_ui import guided_body
from pg_db import connect as pg_connect
from pg_catalog import records as pg_records, coverage as pg_coverage
WEB = Path(__file__).resolve().parents[1] / 'web'
SEMANTIC_PURPOSES = {'birth':'출산 육아 양육 지원', 'elder':'노인 부모님 생활 돌봄 지원',
    'housing':'주거 임대 보증금 지원', 'living':'생활비 생계 지원', 'work':'취업 창업 지원',
    'medical':'건강 의료비 지원', 'education':'교육 장학금 지원'}

SOURCES = {"gov24":"정부24", "welfare-central":"복지로 중앙부처", "welfare-local":"복지로 지자체"}
LABELS = {"summary":"제도 소개","target":"지원 대상","criteria":"선정 기준","benefit":"지원 내용",
          "application":"신청 방법","documents":"구비 서류","deadline":"신청 기한",
          "reference_year":"기준 연도","effective_from":"시행 시작일","effective_to":"시행 종료일",
          "law":"근거 법령","region":"지역","district":"시군구","source_modified_at":"원천 수정일"}



def esc(value):
    return html.escape(str(value or ""), quote=True)


def safe_link(url, label, button=False):
    try:
        parsed = urlsplit(str(url or ""))
        valid = parsed.scheme in ("http","https") and bool(parsed.netloc)
    except ValueError:
        valid = False
    if not valid:
        return '<span class="missing">공식 링크 미확인</span>'
    cls = ' class="link-button"' if button else ''
    return f'<a{cls} href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)}</a>'


def layout(title, body, active="/"):
    paths = {
        "/": ("맞춤 혜택 검색", '<path d="M3 10 12 3l9 7v10H3z"/><path d="M9 20v-7h6v7"/>'),
        "/recommended": ("나의 맞춤 혜택", '<path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6-5.4-2.8L6.6 20l1-6-4.4-4.6 6.1-.9z"/>'),
        "/my": ("마이페이지", '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>'),
    }
    nav = ""
    for path,(label,icon) in paths.items():
        current = ' class="active" aria-current="page"' if active == path else ""
        nav += f'<a href="{path}"{current}><svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true">{icon}</svg>{label}</a>'
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="내 조건에 맞는 생활 혜택을 발견하는 Bene_Fit">
<title>{esc(title)} · Bene_Fit</title><link rel="stylesheet" href="/styles.css"><script src="/profile_crypto.js" defer></script><script src="/app.js" defer></script><script src="/guided.js" defer></script>
</head><body><aside class="sidebar"><a class="brand" href="/"><span class="logo">BF</span><span>Bene<em>_Fit</em></span></a>
<p class="brand-sub">Your Benefits, Your Best Friend.</p><div class="nav-label">MY BENEFITS</div><nav aria-label="주요 메뉴">{nav}</nav>
<div class="sidebar-bottom">내 삶에 딱 맞는 혜택<br>가장 가까운 생활 혜택 친구.</div></aside><div class="app">
<header class="topbar"><span>발견하는 혜택, 달라지는 일상</span><a href="/progress">데이터 준비 과정</a><a href="/my">나의 프로필</a></header>
<main class="wrap">{body}<footer>Bene_Fit · Your Benefits, Your Best Friend.<br>최종 자격과 신청 가능 여부는 해당 기관의 공식 안내를 확인해 주세요. 같은 제도가 출처별로 표시될 수 있습니다.</footer></main></div></body></html>"""


def option(value, label, selected):
    return f'<option value="{esc(value)}"{" selected" if value == selected else ""}>{esc(label)}</option>'


def listing(db, params):
    query=params.get("q",[""])[0].strip()
    if len(query)>200 or (query and not norm(query)):
        raise ValueError("한글·영문·숫자로 검색어를 입력해 주세요.")
    return layout("가족 혜택 탐색",guided_body(query))


def detail(record):
    if not record:
        return None
    f=record["fields"]
    body=f"""<a href="/">혜택 목록</a><div class="detail-top"><span class="badge">{esc(SOURCES[record['source']])}</span>
<h1>{esc(f.get('name','이름 미확인'))}</h1><p class="lead">{esc(f.get('agency','기관 미확인'))}</p>
{safe_link(f.get('source_url'),'공식 안내 보기',True)}
{safe_link(f['apply_url'],'공식 신청처 보기',True) if f.get('apply_url') else ''}</div>"""
    if not record["detail_available"]:
        body+='<div class="note">상세 정보를 아직 수집하지 못했습니다. 현재는 목록의 요약 정보이며, 누락 항목은 공식 안내에서 확인해 주세요.</div>'
    body+='<div class="note">적용 지역과 신청 자격은 검증 전입니다. 신청 기한이 표시되어 있어도 현재 접수 중이라는 뜻은 아닙니다.</div>'
    for field,label in LABELS.items():
        if field in ("target","criteria","benefit","application","documents","deadline") or f.get(field):
            value=f.get(field)
            body+=f'<section class="panel"><h2>{label}</h2><div class="content{"" if value else " missing"}">{esc(value) if value else "미확인 · 공식 안내를 확인해 주세요."}</div></section>'
    for field,label in (("baslawList","관련 법령"),("basfrmList","서식·자료"),("inqplCtadrList","문의처"),("inqplHmpgReldList","관련 사이트")):
        refs=record.get("source_references",{}).get(field,[])
        if isinstance(refs,dict): refs=[refs]
        if not isinstance(refs,list): continue
        items=[]
        for item in refs:
            if not isinstance(item,dict): continue
            name=item.get("servSeDetailNm") or "자료"
            url=item.get("servSeDetailLink") or ""
            items.append("<li>"+(safe_link(url,name) if url.startswith(("http://","https://")) else esc(name+" "+url))+"</li>")
        if items:
            body+=f'<section class="panel"><h2>{label}</h2><ul>{"".join(items)}</ul></section>'
    body+=f"""<section class="panel"><h2>정보 확인</h2><p class="meta">목록 조회: {esc(record.get('checked_at') or '미확인')}<br>
상세 조회: {esc(record.get('detail_checked_at') or '별도 조회시각 미확인')}<br>원천 ID: {esc(record['source_id'])}</p>
<details><summary>항목별 정보 출처</summary><ul>"""
    for field,provenance in record.get("provenance",{}).items():
        if field in LABELS:
            origin="상세" if provenance["record"]=="detail" else "목록"
            body+=f'<li>{esc(LABELS[field])}: {esc(SOURCES[record["source"]])} {origin}</li>'
    return layout(f.get("name","제도 상세"),body+"</ul></details></section>")


class Handler(BaseHTTPRequestHandler):
    database=OUTPUT/"catalog.sqlite"
    use_postgres=True

    def log_message(self,*args):
        pass

    def respond(self,status,body,content_type="text/html; charset=utf-8"):
        data=body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            parsed=urlsplit(self.path)
            params=parse_qs(parsed.query,keep_blank_values=True,max_num_fields=12)
            if parsed.path in ("/styles.css","/app.js","/profile_crypto.js","/guided.js","/progress.js"):
                content_type = "text/css; charset=utf-8" if parsed.path.endswith(".css") else "text/javascript; charset=utf-8"
                return self.respond(200,(WEB/parsed.path[1:]).read_text(encoding="utf-8-sig"),content_type)
            if parsed.path == '/progress':
                body='''<h1>검색 데이터 준비 과정</h1><p>공공 제도 설명만 처리합니다. 개인정보는 임베딩하지 않습니다.</p>
<section class="panel" id="embedding-progress"><h2>임베딩 준비 현황</h2>
<p id="embedding-state" role="status">진행 상황 확인 중</p><progress id="embedding-meter" max="1" value="0" style="width:100%"></progress>
<p id="embedding-count"></p><p id="embedding-speed"></p><p id="embedding-updated" class="meta"></p></section>
<ol><li>수집한 원문·검색 조각 준비: 완료</li><li>전체 임베딩 생성: <span id="embedding-step-two">확인 중</span></li>
<li>검색 기능 검증: 이전 모델 표본 확인 · 새 모델 검증 예정</li><li>웹 연결: 현재 키워드 검색 · 새 모델 연결 예정</li></ol>
<p>페이지는 5초마다 갱신됩니다. 창을 닫아도 생성은 계속됩니다. 유사도 검색은 자격 충족 판정이 아닙니다.</p>
<a href="/">혜택 검색으로 이동</a><script src="/progress.js" defer></script>'''
                return self.respond(200,layout('데이터 준비 과정',body))
            if parsed.path == '/api/embedding-status':
                import embedding_search
                progress={}
                if embedding_search.PROGRESS.exists():
                    progress=json.loads(embedding_search.PROGRESS.read_text(encoding='utf-8'))
                coverage=pg_coverage() if self.use_postgres else embedding_search.status()
                return self.respond(200,json.dumps({'coverage':coverage,'progress':progress}), 'application/json; charset=utf-8')
            if parsed.path == '/api/semantic':
                if set(params)-{'purpose','q'} or any(len(v)!=1 for v in params.values()):
                    raise ValueError('검색어와 지원 분야만 전송할 수 있습니다.')
                purpose=params.get('purpose',[''])[0]
                query=params.get('q',[''])[0].strip()
                if purpose and purpose not in SEMANTIC_PURPOSES: raise ValueError('지원 분야를 확인해 주세요.')
                if len(query)>200 or not (query or purpose): raise ValueError('검색어나 지원 분야를 선택해 주세요.')
                if self.use_postgres:
                    return self.respond(503,json.dumps({'error':'EMBEDDING_MODEL_PENDING','message':'데스크탑에서 새 모델을 선택한 뒤 연결합니다.'},ensure_ascii=False),'application/json; charset=utf-8')
                import embedding_search
                result=embedding_search.search(' '.join(filter(None,[query,SEMANTIC_PURPOSES.get(purpose,'')])),20)
                return self.respond(200,json.dumps(result,ensure_ascii=False),'application/json; charset=utf-8')
            if parsed.path == "/my":
                return self.respond(200,layout("가족 정보·탐색",guided_body(),"/my"))
            if parsed.path == "/recommended":
                return self.respond(200,layout("나의 맞춤 혜택",guided_body(),"/recommended"))
            with closing(pg_connect() if self.use_postgres else sqlite3.connect(self.database.as_uri()+"?mode=ro",uri=True)) as db:
                if parsed.path == "/api/catalog":
                    records=[]
                    fields=("name","agency","category","summary","target","criteria","benefit","region","district","life_stage")
                    rows=pg_records(db) if self.use_postgres else (json.loads(raw) for raw, in db.execute("SELECT record FROM benefits ORDER BY id"))
                    for row in rows:
                        records.append({k:row.get(k) for k in ("id","source","review_group","detail_available")} |
                            {"fields":{k:v for k,v in row["fields"].items() if k in fields},
                             "source_condition_codes":{k:v for k,v in row.get("source_condition_codes",{}).items() if k in ("JA0110","JA0111")}})
                    return self.respond(200,json.dumps({"records":records},ensure_ascii=False),"application/json; charset=utf-8")
                if parsed.path=="/":
                    return self.respond(200,listing(db,params))
                if parsed.path=="/benefit":
                    identifier=params.get("id",[""])[0]
                    if len(identifier)>200:
                        raise ValueError("제도 ID를 확인해 주세요.")
                    if self.use_postgres:
                        record=next(pg_records(db,identifier),None)
                    else:
                        raw=db.execute('SELECT record FROM benefits WHERE id=?',(identifier,)).fetchone()
                        record=json.loads(raw[0]) if raw else None
                    body=detail(record)
                    if body is not None:
                        return self.respond(200,body)
            self.respond(404,layout("찾을 수 없음","<h1>페이지를 찾을 수 없습니다.</h1><a href='/'>혜택 검색</a>"))
        except ValueError as error:
            self.respond(400,layout("검색 조건 확인",f"<h1>검색 조건을 확인해 주세요.</h1><p>{esc(error)}</p><a href='/'>혜택 검색</a>"))
        except (sqlite3.Error, psycopg.Error, OSError, ImportError):
            self.respond(503,layout("데이터 확인 필요","<h1>검색 데이터를 읽을 수 없습니다.</h1><p>검색 목록을 준비한 뒤 다시 시도해 주세요.</p>"))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=8765)
    args=parser.parse_args()
    try:
        with pg_connect() as db: db.execute('SELECT 1 FROM bene_fit.benefit_ver LIMIT 1')
    except psycopg.Error:
        parser.error('PostgreSQL is unavailable or not migrated; check .env.postgres and run migrate_postgres.py')
    # Prevent a second Windows server from sharing the same listening port.
    ThreadingHTTPServer.allow_reuse_address=False
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    print(f"Local: http://127.0.0.1:{server.server_port}",flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=="__main__":
    main()
