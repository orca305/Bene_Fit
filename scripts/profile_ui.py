"""Profile forms and recommendation shells; personal values stay in the browser."""
from html import escape
REGIONS = ("서울특별시","부산광역시","대구광역시","인천광역시","광주광역시","대전광역시","울산광역시","세종특별자치시","경기도","강원특별자치도","충청북도","충청남도","전북특별자치도","전라남도","경상북도","경상남도","제주특별자치도")
INTERESTS = ("주거·부동산","복지·생활","금융·자산형성","취업·창업","교육·장학","세금·공과금","결혼·출산·육아","건강·의료","교통·자동차","문화·여가","보험·연금","민간·재단 혜택")


def field(name, label, options=None, maximum=None, hint="", minimum=0):
    if options is not None:
        control=f'<select name="{name}" id="{name}"><option value="">선택하지 않음</option>'+''.join(f'<option value="{escape(v)}">{escape(v)}</option>' for v in options)+'</select>'
    else:
        control=f'<input type="number" name="{name}" id="{name}" min="{minimum}" max="{maximum}" step="1" inputmode="numeric" placeholder="선택 입력">'
    return f'<div><label for="{name}">{label}</label>{control}<p class="field-help">{hint or "모르거나 입력을 원하지 않으면 비워 두세요."}</p></div>'


def unlock_body():
    return """<section id="vault-unlock" class="panel hidden"><span class="badge">암호화된 프로필</span><h2 style="margin-top:18px">내 정보를 안전하게 불러오기</h2>
<p class="meta">보관 암호를 입력하면 이 페이지에서만 정보를 해제합니다. 암호는 서버로 전송하거나 저장하지 않습니다.</p>
<form id="unlock-form"><label for="unlock-password">프로필 보관 암호</label><input id="unlock-password" type="password" minlength="10" maxlength="256" autocomplete="current-password" required>
<div class="form-actions"><button type="submit">프로필 잠금 해제</button><button type="button" id="erase-locked" class="danger">저장 정보 삭제</button></div><p id="unlock-message" role="status" aria-live="polite"></p></form>
<p class="field-help">암호를 잊으면 복구할 수 없습니다. 저장 정보를 삭제한 뒤 새로 입력해 주세요. 암호 해제 후 페이지를 이동하면 다시 잠깁니다.</p></section>"""


def profile_body():
    base=field("age","나이 · 만 나이",maximum=120)+field("region","거주 시도",REGIONS)
    base+=field("household","가구원 수 · 본인 포함",maximum=30,minimum=1)+field("children","자녀 수",maximum=20)
    base+=field("marriage","혼인 상태",("미혼","기혼","기타"))+field("employment","경제활동 상태",("재직 중","구직 중","자영업","학생","은퇴","기타"))
    base+=field("housing","주거 형태",("자가","전세","월세","공공임대","가족과 거주","기타"))
    base+=field("disability","등록 장애 여부",("해당","해당 없음"))
    money=field("income","연 소득 · 세전, 만원",maximum=100000000,hint="예: 3,600만원이면 3600. 제도별 소득인정액과 다릅니다.")
    money+=field("assets","가구 총자산 · 만원",maximum=100000000,hint="부동산·금융자산 등의 대략적인 합계. 제도별 산정 기준과 다릅니다.")
    money+=field("debt","가구 부채 · 만원",maximum=100000000)
    interests=''.join(f'<label class="interest-option"><input type="checkbox" name="interests" value="{escape(v)}">{v}</label>' for v in INTERESTS)
    return f"""<div class="page-heading"><span class="eyebrow">MY PROFILE</span><h1>나를 알수록, 더 가까운 혜택.</h1>
<p class="lead">내 정보를 등록하면 관심 분야와 생활 상황에 맞는 혜택 후보를 먼저 찾아드려요.<br>모든 항목은 선택 사항이며 언제든 수정하거나 삭제할 수 있어요.</p></div>
<noscript><div class="note">프로필 저장과 맞춤 탐색에는 JavaScript가 필요합니다. 일반 혜택 검색은 계속 사용할 수 있습니다.</div></noscript>
{unlock_body()}<div id="profile-editor"><div class="profile-layout"><form id="profile-form" class="profile-form"><fieldset id="profile-controls" class="profile-controls" disabled>
<fieldset><legend>기본 정보</legend><p class="section-description">현재의 생활 상황을 알려주세요. 입력하지 않은 조건은 추측하지 않아요.</p><div class="fields">{base}</div></fieldset>
<fieldset><legend>소득과 자산</legend><p class="section-description">입력값은 보관·수정할 수 있어요. 아직 제도별 소득·자산 기준의 자동 비교에는 사용하지 않아요.</p><div class="fields">{money}</div></fieldset>
<fieldset><legend>관심 있는 혜택</legend><p class="section-description">관심 분야를 골라주세요. 확보된 데이터 안에서 관련 제도를 먼저 보여드려요.</p><div class="interest-grid">{interests}</div></fieldset>
<section class="panel"><h2>프로필 보관 설정</h2><div class="fields">
<div><label for="vault-password">보관 암호</label><input id="vault-password" type="password" minlength="10" maxlength="256" autocomplete="new-password" required><p class="field-help">10자 이상. 암호는 보관하지 않으며 분실 시 복구할 수 없습니다.</p></div>
<div><label for="vault-confirm">보관 암호 확인</label><input id="vault-confirm" type="password" minlength="10" maxlength="256" autocomplete="new-password" required></div></div>
<label class="storage-option"><input type="checkbox" id="remember"><span>이 브라우저에 계속 저장하기<br><span class="meta">기본은 이번 탭에 암호화해서 보관합니다. 공용 기기에서는 선택하지 마세요.</span></span></label>
<p class="field-help">프로필은 AES-GCM 방식으로 암호화해 보관하며 서버·외부 AI로 전송하지 않습니다. 브라우저 데이터 삭제 시 함께 삭제되며 계정 간 동기화는 지원하지 않습니다.</p>
<div class="form-actions"><button type="submit">암호화해서 저장하기</button><button type="button" id="clear-profile" class="danger">내 정보 삭제</button></div>
<p id="profile-message" role="status" aria-live="polite"></p></section></fieldset></form>
<aside class="profile-aside"><section class="panel"><span class="badge">나의 혜택 프로필</span><h3 style="margin-top:18px">내 정보는 내 손안에</h3>
<ul><li>이름·연락처·주민등록번호는 받지 않아요.</li><li>입력값은 암호화해 이 기기에만 보관해요.</li><li>마이페이지에서 전체 삭제할 수 있어요.</li></ul></section>
<section class="panel"><h3>추천과 자격 확인은 달라요</h3><p class="meta">현재는 관심 분야·지역·나이·생활 상황에 관련된 후보를 정렬합니다. 소득·자산 등 세부 자격은 공식 안내에서 확인해야 해요.</p></section></aside></div></div>"""


def recommended_body():
    return unlock_body()+"""<div class="page-heading"><span class="eyebrow">FOR YOU</span><h1>내 삶에 맞는 혜택을 발견해요.</h1>
<p class="lead">마이페이지에 입력한 조건으로 관련 혜택 후보를 먼저 모았어요.</p></div>
<noscript><div class="note">맞춤 탐색에는 JavaScript가 필요합니다. <a href="/">전체 혜택 검색</a>을 이용해 주세요.</div></noscript>
<div id="recommend-empty" class="panel empty hidden"><h2>나의 상황부터 알려주세요.</h2><p>관심 분야나 생활 정보를 한 가지 이상 입력하면 관련 후보를 찾아드려요.</p><a class="link-button" href="/my">프로필 입력하기</a></div>
<div id="recommend-content" class="hidden"><div class="profile-summary"><div><h3>나의 혜택 프로필</h3><p id="profile-summary"></p></div><a href="/my" class="link-button secondary">정보 수정</a></div>
<div class="note">현재 추천은 입력 정보와 원천 안내의 연관성을 기준으로 한 후보 탐색입니다. 자격 충족이나 접수 중을 뜻하지 않습니다. 소득·자산·부채·혼인·가구원 수는 아직 자동 비교하지 않아요.</div>
<div class="count"><strong>먼저 살펴볼 혜택</strong><span id="recommend-count" class="meta"></span></div><p id="recommend-status" role="status" aria-live="polite">후보를 불러오고 있어요.</p>
<div id="recommend-results" class="grid"></div><div class="form-actions"><button id="more-results" class="secondary hidden">후보 더 보기</button><a href="/" class="link-button secondary">직접 검색하기</a></div></div>"""
