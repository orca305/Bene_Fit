"""Optional guided exploration; no personal values in rendered server HTML."""
from html import escape
from profile_ui import REGIONS

def guided_body(query=""):
    return f"""<section id="guided-search" data-query="{escape(query,quote=True)}">
<div class="page-heading"><span class="eyebrow">BENEFITS FOR YOUR FAMILY</span><h1>필요한 것부터, 하나씩 찾아요.</h1>
<p class="lead">나·자녀·부모님·우리 가구를 위한 지원을 찾아보세요.<br>개인정보는 모두 선택 입력입니다. 저장하거나 암호를 만들지 않아도 탐색할 수 있어요.</p></div>
<noscript><div class="note">선택형 탐색에는 JavaScript가 필요합니다. 개인정보는 서버로 보내지 않습니다.</div></noscript>
<div class="form-actions"><button type="button" id="load-family" class="secondary">저장한 가족 정보 불러오기</button><button type="button" id="new-exploration" class="secondary">새 탐색 · 입력 초기화</button></div>
<section id="family-unlock" class="panel hidden"><h2>저장한 가족 정보</h2>
<form id="family-unlock-form"><label for="family-unlock-password">보관 암호</label><input id="family-unlock-password" type="password" minlength="10" maxlength="256" autocomplete="current-password" required>
<div class="form-actions"><button type="submit">잠금 해제</button><button id="close-family-unlock" type="button" class="secondary">불러오지 않고 계속</button><button id="delete-families" type="button" class="danger">저장한 가족 정보 삭제</button></div></form><p id="family-unlock-status" role="status"></p></section>
<div id="family-picker" class="panel hidden"><h2>어느 가족의 정보를 사용할까요?</h2><div id="family-options" class="form-actions"></div></div>
<section class="panel" id="question-panel"><p id="question-progress" class="meta"></p><h2 id="question-title" tabindex="-1"></h2><p id="question-why" class="lead"></p>
<form id="question-form"><fieldset id="question-controls" disabled class="question-controls"><div id="question-input"></div>
<div class="form-actions"><button type="submit">다음</button><button id="skip-question" type="button" class="secondary">모름 · 건너뛰기</button><button id="preview-candidates" type="button" class="secondary">지금 정보로 후보 보기</button><button id="previous-question" type="button" class="secondary">이전</button></div></fieldset></form>
<p id="guided-message" role="status" aria-live="polite"></p></section>
<section id="guided-output" class="hidden"><div class="profile-summary"><div><h2>이번 탐색 조건</h2><p id="guided-summary"></p></div><button id="edit-answers" class="secondary" type="button">답변 수정</button></div>
<div class="note">현재는 원천 안내와의 관련성을 기준으로 후보를 찾습니다. 답하지 않은 항목은 ‘확인 필요’입니다. 자격 충족을 뜻하지 않으며, 소득·자산 규칙은 아직 검토 중이라 자동 판정하지 않습니다.</div>
<p id="guided-results-status" role="status" aria-live="polite"></p><div id="guided-results" class="grid"></div>
<div class="form-actions"><button id="guided-more" type="button" class="secondary hidden">후보 더 보기</button><button id="continue-questions" class="secondary" type="button">관련 질문에 더 답하기</button><button id="show-save-family" type="button" class="secondary">선택 · 이번 가족 정보 저장</button></div>
<section id="save-family-panel" class="panel hidden"><h2>선택 · 가족 정보 암호화 저장</h2><p class="meta">저장하지 않아도 결과를 볼 수 있습니다. 저장하는 경우에만 보관 암호가 필요합니다. 암호는 보관하지 않으며 분실하면 복구할 수 없습니다.</p>
<form id="family-save-form"><label for="family-password">보관 암호 · 10자 이상</label><input id="family-password" type="password" minlength="10" maxlength="256" autocomplete="new-password" required>
<label for="family-password-confirm">보관 암호 확인</label><input id="family-password-confirm" type="password" minlength="10" maxlength="256" autocomplete="new-password" required>
<label class="storage-option"><input id="family-remember" type="checkbox">이 브라우저에 계속 저장 · 선택하지 않으면 이번 탭에만 암호화 보관</label>
<div class="form-actions"><button type="submit">암호화 저장</button><button id="cancel-save-family" type="button" class="secondary">저장하지 않기</button></div></form><p id="family-save-status" role="status"></p></section></section>
<p class="meta">나이·지역·가족 답변은 브라우저에서만 사용합니다. 검색어와 지원 분야만 이 PC의 검색 서버로 보내며 외부 AI로 전송하지 않습니다. 저장하지 않은 정보는 페이지 이동·새로고침 시 사라집니다.</p>
</section>"""
