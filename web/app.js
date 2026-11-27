"use strict";
const BF_KEY = "bene_fit_profile_v1";
const NUMBER_LIMITS = {age:[0,120],household:[1,30],children:[0,20],income:[0,100000000],assets:[0,100000000],debt:[0,100000000]};
const ENUMS = {
 region:["서울특별시","부산광역시","대구광역시","인천광역시","광주광역시","대전광역시","울산광역시","세종특별자치시","경기도","강원특별자치도","충청북도","충청남도","전북특별자치도","전라남도","경상북도","경상남도","제주특별자치도"],
 marriage:["미혼","기혼","기타"],employment:["재직 중","구직 중","자영업","학생","은퇴","기타"],
 housing:["자가","전세","월세","공공임대","가족과 거주","기타"],disability:["해당","해당 없음"]
};
const TOPICS = {
 "주거·부동산":["주거","임대","주택","전세","월세","청약"],
 "복지·생활":["생활지원","생활안정","생계","긴급복지","돌봄"],
 "금융·자산형성":["금융","저축","자산형성","대출","융자"],
 "취업·창업":["취업","창업","일자리","직업훈련","고용"],
 "교육·장학":["교육","장학","학자금","학습"],
 "세금·공과금":["세금","공과금","세액","전기요금","가스요금"],
 "결혼·출산·육아":["결혼","출산","육아","보육","신혼","임신"],
 "건강·의료":["건강","의료","검진","치료"],
 "교통·자동차":["교통","자동차","대중교통"],
 "문화·여가":["문화","여가","체육","여행"],
 "보험·연금":["보험","연금","노후"],
 "민간·재단 혜택":["재단","민간"]
};
function cleanProfile(input) {
 const profile = {version:1,interests:[]};
 if (!input || typeof input !== "object" || Array.isArray(input)) return profile;
 for (const [key,[min,max]] of Object.entries(NUMBER_LIMITS)) {
  const value = input[key];
  if (value !== "" && value !== null && value !== undefined && typeof value !== "boolean" && ["number","string"].includes(typeof value)) {
   const number = Number(value);
   if (Number.isInteger(number) && number >= min && number <= max) profile[key] = number;
  }
 }
 for (const [key,values] of Object.entries(ENUMS)) if (values.includes(input[key])) profile[key] = input[key];
 if (Array.isArray(input.interests)) profile.interests = [...new Set(input.interests.filter(x=>Object.hasOwn(TOPICS,x)))];
 return profile;
}
function hasProfile(profile) { return Object.keys(profile).some(k=>!["version","interests"].includes(k)) || profile.interests.length > 0; }
function rankCandidate(row, input) {
 const profile=cleanProfile(input), f=row.fields || {};
 const haystack=[f.name,f.category,f.summary,f.target,f.life_stage].filter(Boolean).join(" ");
 const reasons=[]; let score=0;
 const add=(points,reason)=>{score+=points;reasons.push(reason);};
 for (const topic of profile.interests) if(TOPICS[topic].some(word=>haystack.includes(word))) add(4,topic+" 관심 분야");
 if (profile.region && f.region===profile.region) add(5,"거주 시도와 같은 지역 안내");
 if (profile.age !== undefined) {
  const codes=row.source_condition_codes || {};
  const low=codes.JA0110, high=codes.JA0111;
  if (low!==null && low!==undefined && low!=="" && high!==null && high!==undefined && high!=="" &&
      Number.isFinite(Number(low)) && Number.isFinite(Number(high)) &&
      Number(low)>=0 && Number(high)<=120 && Number(low)<=Number(high) &&
      !(Number(low)===0 && Number(high)===120) && profile.age>=Number(low) && profile.age<=Number(high)) {
    add(2,"원천 안내 연령 범위와 관련");
  } else if (f.life_stage) {
   const stage=profile.age<6?"영유아":profile.age<13?"아동":profile.age<19?"청소년":profile.age<35?"청년":profile.age<65?"중장년":"노년";
   if(f.life_stage.includes(stage)) add(1,"원천 생애주기 안내와 관련");
  }
 }
 if(profile.children>0 && ["자녀","아동","육아","보육","출산"].some(w=>haystack.includes(w))) add(2,"자녀·양육 관련 안내");
 if(profile.disability==="해당" && haystack.includes("장애인")) add(2,"장애인 지원 관련 안내");
 const employment={"재직 중":["근로자","직장인"],"구직 중":["구직","취업","실업"],"자영업":["소상공인","자영업","사업자"],"학생":["학생","학자금","장학"],"은퇴":["노후","연금"]};
 if((employment[profile.employment]||[]).some(w=>haystack.includes(w))) add(2,"경제활동 관련 안내");
 const housing={"전세":["전세"],"월세":["월세","임차"],"공공임대":["공공임대","임대주택"]};
 if((housing[profile.housing]||[]).some(w=>haystack.includes(w))) add(2,"현재 주거 형태 관련 안내");
 return {row,score,reasons};
}
function recommend(rows, profile) {
 return rows.map(row=>rankCandidate(row,profile)).filter(item=>item.score>0)
   .sort((a,b)=>b.score-a.score || a.row.id.localeCompare(b.row.id));
}
function searchCandidates(rows, input, query, options={}) {
 const profile=cleanProfile(input);
 const key=String(query||"").toLowerCase().replace(/[^가-힣a-z0-9]/g,"");
 if(!key || !hasProfile(profile)) return [];
 const matched=rows.filter(row=>{
  if(options.scope==="national" && row.review_group!=="national_candidate") return false;
  if(options.source && row.source!==options.source) return false;
  return Object.values(row.fields||{}).join(" ").toLowerCase().replace(/[^가-힣a-z0-9]/g,"").includes(key);
 });
 return recommend(matched,profile);
}
const VAULT_KEY = "bene_fit_profile_v2";
function e(tag,text,className) {
 const el=document.createElement(tag);
 if(text!==undefined) el.textContent=text;
 if(className) el.className=className;
 return el;
}
function storedVault() {
 try {
  const temporary=sessionStorage.getItem(VAULT_KEY),permanent=localStorage.getItem(VAULT_KEY);
  const raw=temporary||permanent;
  return raw?{envelope:JSON.parse(raw),remember:!temporary&&Boolean(permanent)}:null;
 } catch { return {invalid:true}; }
}
function eraseStored() {
 sessionStorage.removeItem(VAULT_KEY);localStorage.removeItem(VAULT_KEY);
 sessionStorage.removeItem(BF_KEY);localStorage.removeItem(BF_KEY);
}
function askUnlock(callback) {
 const saved=storedVault();
 if(!saved) {callback(cleanProfile({}),false);return;}
 const panel=document.getElementById("vault-unlock"),editor=document.getElementById("profile-editor");
 if(editor) editor.classList.add("hidden");
 panel.classList.remove("hidden");
 const form=document.getElementById("unlock-form"),message=document.getElementById("unlock-message");
 if(saved.invalid) message.textContent="저장 정보를 읽지 못했습니다. 저장 정보를 삭제한 뒤 다시 입력해 주세요.";
 form.addEventListener("submit",async event=>{
  event.preventDefault();const button=form.querySelector('[type="submit"]');button.disabled=true;
  try {
   const profile=cleanProfile(await BFVault.decrypt(saved.envelope,document.getElementById("unlock-password").value));
   form.reset();panel.classList.add("hidden");if(editor) editor.classList.remove("hidden");
   callback(profile,saved.remember);
  } catch {message.textContent="암호가 다르거나 저장 정보가 손상되었습니다. 암호를 다시 확인해 주세요.";}
  finally {button.disabled=false;}
 });
 document.getElementById("erase-locked").addEventListener("click",()=>{
  try {eraseStored();location.reload();}
  catch {message.textContent="삭제하지 못했습니다. 브라우저 사이트 데이터 설정에서 삭제해 주세요.";}
 });
}
function initializeProfile() {
 const form=document.getElementById("profile-form");
 if(!form) return;
 const message=document.getElementById("profile-message");
 askUnlock((profile,remember)=>{
  for(const key of [...Object.keys(NUMBER_LIMITS),...Object.keys(ENUMS)]) if(profile[key]!==undefined) form.elements[key].value=String(profile[key]);
  for(const box of form.querySelectorAll('[name="interests"]')) box.checked=profile.interests.includes(box.value);
  document.getElementById("remember").checked=remember;
 });
 form.addEventListener("submit",async event=>{
  event.preventDefault();
  if(!form.reportValidity()) return;
  const password=document.getElementById("vault-password"),confirmation=document.getElementById("vault-confirm");
  if(password.value!==confirmation.value) {message.textContent="보관 암호가 일치하지 않습니다.";confirmation.focus();return;}
  const values=Object.fromEntries(new FormData(form));
  values.interests=[...form.querySelectorAll('[name="interests"]:checked')].map(x=>x.value);
  const profile=cleanProfile(values);
  if(!hasProfile(profile)) {message.textContent="한 가지 이상 입력하거나 관심 분야를 선택해 주세요.";return;}
  const button=form.querySelector('[type="submit"]');button.disabled=true;
  try {
   const envelope=await BFVault.encrypt(profile,password.value),raw=JSON.stringify(envelope);
   if(document.getElementById("remember").checked) {
    localStorage.setItem(VAULT_KEY,raw);sessionStorage.removeItem(VAULT_KEY);
   } else {
    sessionStorage.setItem(VAULT_KEY,raw);localStorage.removeItem(VAULT_KEY);
   }
   sessionStorage.removeItem(BF_KEY);localStorage.removeItem(BF_KEY);
   password.value="";confirmation.value="";
   message.replaceChildren(e("span","프로필을 암호화해 저장했습니다. "));
   const link=e("a","나의 맞춤 혜택 보기");link.href="/recommended";message.append(link);message.className="success";
  } catch {
   message.textContent="암호화 저장에 실패했습니다. 브라우저 저장·암호화 기능을 허용한 뒤 다시 시도해 주세요. 입력 내용은 전송되지 않았습니다.";
  } finally {button.disabled=false;}
 });
 document.getElementById("clear-profile").addEventListener("click",()=>{
  try {eraseStored();form.reset();message.className="success";message.textContent="이 브라우저의 암호화된 프로필을 모두 삭제했습니다.";}
  catch {message.textContent="삭제하지 못했습니다. 브라우저의 사이트 데이터 설정에서 직접 삭제해 주세요.";}
 });
 document.getElementById("profile-controls").disabled=false;
}
function initializeRecommendations() {
 const container=document.getElementById("recommend-results");
 if(!container) return;
 askUnlock(async profile=>{
  if(!hasProfile(profile)) {document.getElementById("recommend-empty").classList.remove("hidden");return;}
  document.getElementById("recommend-content").classList.remove("hidden");
  const summary=[];
  if(profile.age!==undefined) summary.push("만 "+profile.age+"세");
  if(profile.region) summary.push(profile.region);
  if(profile.children!==undefined) summary.push("자녀 "+profile.children+"명");
  if(profile.interests.length) summary.push(profile.interests.join(", "));
  document.getElementById("profile-summary").textContent=summary.join(" · ") || "프로필이 저장되어 있어요.";
  const status=document.getElementById("recommend-status"),more=document.getElementById("more-results");
  try {
   // Only public benefit data is fetched. No profile or password is transmitted.
   const response=await fetch("/api/catalog",{credentials:"omit",cache:"no-store"});
   if(!response.ok) throw new Error("catalog");
   const payload=await response.json(),search=document.getElementById("personal-search");
   const ranked=search?searchCandidates(payload.records,profile,search.dataset.query,{scope:search.dataset.scope,source:search.dataset.source}):recommend(payload.records,profile);
   document.getElementById("recommend-count").textContent=ranked.length.toLocaleString()+"건의 관련 후보";
   status.textContent=ranked.length?"추천 이유를 확인한 뒤 공식 안내에서 세부 조건을 살펴보세요.":"현재 비교 가능한 정보와 관련된 후보를 찾지 못했어요. 관심 분야나 생활 정보를 추가하거나 직접 검색해 주세요.";
   let shown=0;
   function renderMore() {
    for(const {row,reasons} of ranked.slice(shown,shown+12)) {
     const f=row.fields,card=e("article",undefined,"benefit-card"),top=e("div",undefined,"card-top");
     top.append(e("span",({"gov24":"정부24","welfare-central":"복지로 중앙부처","welfare-local":"복지로 지자체"})[row.source],"badge"),
       e("span",row.detail_available?"상세 정보 있음":"상세 수집 대기","card-status"));
     const heading=e("h2"),link=e("a",f.name||"이름 미확인");
     link.href="/benefit?"+new URLSearchParams({id:row.id});heading.append(link);
     const tags=e("div",undefined,"reasons");for(const reason of reasons.slice(0,3)) tags.append(e("span",reason,"reason"));
     card.append(top,heading,e("div",f.agency||"기관 미확인","meta"),e("p",f.summary||"설명 미확인"),tags,
       e("div","세부 소득·자산 기준 및 신청 가능 여부 확인 필요","recommend-info"));
     container.append(card);
    }
    shown=Math.min(shown+12,ranked.length);more.classList.toggle("hidden",shown>=ranked.length);
   }
   more.addEventListener("click",renderMore);renderMore();
  } catch {status.textContent="혜택 목록을 불러오지 못했어요. 새로고침해 주세요. 프로필은 서버로 전송되지 않았습니다.";}
 });
}
if(typeof module!=="undefined" && module.exports) module.exports={cleanProfile,rankCandidate,recommend,hasProfile,searchCandidates};
if(typeof document!=="undefined") {initializeProfile();initializeRecommendations();}
