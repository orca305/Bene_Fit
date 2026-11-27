"use strict";
const BFMatch=typeof module!=="undefined"?require("./app.js"):{cleanProfile,rankCandidate};
const FAMILY_KEY="bene_fit_families_v1";
const ROLES={self:"나",child:"자녀",parent:"부모님",household:"우리 가구"};
const PURPOSES={birth:"출산·육아",elder:"부모님 생활·돌봄",housing:"주거 지원",living:"생활비",work:"취업·창업",medical:"건강·의료",education:"교육·장학"};
const DETAIL_OPTIONS={
 housingNeed:[["rent","월세·주거비"],["deposit","보증금·전세자금"],["public","공공임대·주택 공급"],["repair","집수리·주거 환경"],["other","기타"]],
 tenure:[["monthly","월세"],["jeonse","전세"],["own","자가 거주"],["temporary","임시 거처·시설"],["other","기타"]],
 livingNeed:[["daily","일상 생활비"],["energy","전기·가스 등 에너지 비용"],["emergency","갑작스러운 위기·긴급 지원"],["reduction","요금 감면"],["other","기타"]],
 workNeed:[["job","일자리 찾기"],["training","직업훈련·자격 준비"],["startup","창업 준비"],["business","운영 중인 사업 지원"],["other","기타"]],
 workState:[["employed","근무 중"],["seeking","일하지 않으며 구직 중"],["self_employed","자영업·사업 운영"],["student","재학 중"],["other","기타"]],
 medicalNeed:[["cost","의료비·치료비"],["checkup","건강검진·예방"],["rehab","재활·보조기기"],["care","간병·돌봄"],["other","기타"]],
 educationStage:[["preschool","취학 전"],["primary","초등학교"],["secondary","중학교·고등학교"],["university","대학교·대학원"],["adult","성인·평생교육"],["other","기타"]],
 educationNeed:[["tuition","학비·등록금"],["scholarship","장학금"],["supplies","교재·학습·교육비"],["training","평생교육·훈련"],["other","기타"]]
};
const PURPOSE_FIELDS={birth:["stage","months","order","children","care","recognized"],elder:["cohabitation","need"],
 housing:["housingNeed","tenure"],living:["livingNeed"],work:["workNeed","workState"],medical:["medicalNeed"],education:["educationStage","educationNeed"]};
const INTENT_TERMS={
 housingNeed:{rent:["월세","주거급여"],deposit:["보증금","전세"],public:["공공임대","국민임대","행복주택"],repair:["집수리","주택개량","주거환경"]},
 livingNeed:{daily:["생활비","생계"],energy:["에너지","전기","가스","난방"],emergency:["긴급","위기"],reduction:["감면","요금"]},
 workNeed:{job:["취업","일자리","구직"],training:["직업훈련","자격","내일배움"],startup:["창업"],business:["소상공인","경영","사업자"]},
 medicalNeed:{cost:["의료비","치료비"],checkup:["검진","예방"],rehab:["재활","보조기기"],care:["간병","돌봄","요양"]},
 educationNeed:{tuition:["학비","등록금","학자금"],scholarship:["장학"],supplies:["교재","학습","교육비"],training:["평생교육","훈련"]}
};
const GUIDED_REGIONS=["서울특별시","부산광역시","대구광역시","인천광역시","광주광역시","대전광역시","울산광역시","세종특별자치시","경기도","강원특별자치도","충청북도","충청남도","전북특별자치도","전라남도","경상북도","경상남도","제주특별자치도"];
function cleanAnswers(input={}) {
 const out={};
 if(!input || typeof input!=="object") return out;
 for(const [key,values] of Object.entries({role:Object.keys(ROLES),purpose:Object.keys(PURPOSES),region:GUIDED_REGIONS,
 stage:["expecting","born"],care:["together","single","grandparent","other"],recognized:["yes","pending","no"],
 cohabitation:["alone","spouse","children","other"],need:["daily","medical","living","housing"],
 ...Object.fromEntries(Object.entries(DETAIL_OPTIONS).map(([key,options])=>[key,options.map(([value])=>value)]))})) {
  if(values.includes(input[key])) out[key]=input[key];
 }
 for(const [key,min,max] of [["age",0,120],["months",0,240],["order",1,20],["children",0,20]]) {
  const value=input[key];
  if(value!=="" && value!==null && value!==undefined && ["string","number"].includes(typeof value) &&
   Number.isInteger(Number(value)) && Number(value)>=min && Number(value)<=max) out[key]=Number(value);
 }
 if(out.purpose) {
  const allowed=new Set(["role","purpose","region","age",...PURPOSE_FIELDS[out.purpose]]);
  for(const key of Object.keys(out))if(!allowed.has(key))delete out[key];
 }
 if(out.role==="household" || out.purpose==="birth")delete out.age;
 if(out.purpose==="birth") {
  if(out.stage==="expecting")delete out.months;
  if(out.care!=="single")delete out.recognized;
 }
 if(out.role==="household") {delete out.workState;delete out.educationStage;delete out.cohabitation;}
 return out;
}
function questions(input={}) {
 const a=cleanAnswers(input);
 const person={self:"본인",child:"대상 자녀",parent:"대상 부모님",household:"지원받을 가구"}[a.role]||"지원받을 분";
 const list=[
 {key:"role",title:"누구를 위한 혜택인가요?",why:"지원받을 사람을 구분합니다. 신청하는 본인의 정보를 가족에게 적용하지 않아요.",options:Object.entries(ROLES)},
 {key:"purpose",title:"어떤 도움이 필요한가요?",why:"찾는 지원 분야만 선택해도 후보를 볼 수 있어요. 가족관계나 경제 정보를 입력할 필요는 없습니다.",options:Object.entries(PURPOSES)},
 {key:"region",title:person+"의 거주 시도는 어디인가요?",why:"혜택을 찾는 대상의 거주 지역입니다. 부모님 혜택에 신청하는 자녀의 주소를 대신 넣지 않아요. 상세 주소는 받지 않습니다.",subject:a.role==="household"?"household":"beneficiary",options:GUIDED_REGIONS.map(x=>[x,x])}];
 if(a.purpose==="birth") {
  list.push({key:"stage",title:"출산 전인가요, 출산 후인가요?",why:"출산 전·후 관련 안내를 구분하는 데 사용해요. 정확한 출생일은 받지 않습니다.",options:[["expecting","임신 중·출산 예정"],["born","출산 후"]]});
  if(a.stage==="born") list.push({key:"months",title:"대상 아이는 생후 몇 개월인가요?",why:"아이의 월령을 바탕으로 관련 안내를 찾습니다. 보호자의 나이를 아이에게 적용하지 않아요.",max:240});
  list.push({key:"order",title:"대상 아이는 몇 번째 자녀인가요?",why:"출생 순서 관련 안내를 확인하기 위한 선택 정보입니다. 지급 대상 여부를 확정하지는 않아요.",min:1,max:20},
   {key:"children",title:"자녀는 모두 몇 명인가요?",why:"자녀 수와 출생 순서는 따로 보관합니다. 모르면 건너뛰어도 돼요.",max:20},
   {key:"care",title:"현재 양육 상황을 알려주실 수 있나요?",why:"양육 상황과 혼인 상태를 동일하게 판단하지 않아요. 한부모·조손 관련 안내를 찾는 데만 사용합니다.",options:[["together","부모가 함께 양육"],["single","한부모가 양육"],["grandparent","조부모가 양육"],["other","기타"]]});
  if(a.care==="single") list.push({key:"recognized",title:"한부모가족 지원대상 인정을 받았나요?",why:"혼자 양육한다는 사실과 기관의 지원대상 인정은 다릅니다. 현재 이 답변만으로 자격을 판정하지 않아요.",options:[["yes","인정받음"],["pending","신청 중"],["no","인정받지 않음"]]});
 } else if(a.purpose) {
  if(a.role!=="household")list.push({key:"age",title:person+"의 만 나이는 얼마인가요?",why:"혜택을 받을 한 사람의 나이입니다. 다른 가족의 나이를 대신 적용하지 않아요. 모르면 건너뛸 수 있습니다.",subject:"beneficiary",max:120});
  if(a.purpose==="elder") {
   if(a.role!=="household")list.push({key:"cohabitation",title:person+"의 거주 형태는 어떤가요?",why:"실제 생활 상황을 구분합니다. 함께 산다는 이유로 같은 소득 산정 가구라고 확정하지 않아요.",subject:"beneficiary",options:[["alone","혼자"],["spouse","배우자"],["children","자녀"],["other","기타"]]});
   list.push({key:"need",title:"어떤 도움이 가장 필요한가요?",why:"진단명이나 의료기록 없이 필요한 지원 종류만 선택할 수 있어요.",subject:"search_intent",options:[["daily","식사·이동 등 일상 돌봄"],["medical","의료비·건강 관리"],["living","생활비"],["housing","주거"]]});
  }
 }
 const detail=(key,title,why,subject="beneficiary")=>({key,title,why,subject,options:DETAIL_OPTIONS[key]});
 if(a.purpose==="housing")list.push(
  detail("housingNeed","주거와 관련해 어떤 도움이 필요한가요?","필요한 지원 종류를 구분합니다. 주택 소유나 소득을 입력하지 않아도 후보를 볼 수 있어요.","search_intent"),
  detail("tenure",person+"의 현재 거주 형태는 어떤가요?","현재 거주 형태만 묻습니다. 전세·월세 거주를 무주택 증명으로 판단하지 않으며, 다른 가족의 주택 소유 여부도 추정하지 않아요.",a.role==="household"?"household":"beneficiary"));
 if(a.purpose==="living")list.push(detail("livingNeed","어떤 생활비 지원이 필요한가요?","원하는 지원 종류만 선택합니다. 위기 사유나 소득·자산 금액은 지금 묻지 않아요.","search_intent"));
 if(a.purpose==="work") {
  list.push(detail("workNeed","취업·창업과 관련해 어떤 도움이 필요한가요?","지원 종류에 맞는 안내를 먼저 찾습니다. 실업급여 등 개별 제도의 수급 조건을 판정하지는 않아요.","search_intent"));
  if(a.role!=="household")list.push(detail("workState",person+"의 현재 활동 상황은 어떤가요?","선택한 한 사람의 상황입니다. 재학과 근무가 겹치는 등 맞는 항목이 없으면 건너뛰어도 됩니다. 고용보험 가입 여부를 대신 판단하지 않아요."));
 }
 if(a.purpose==="medical")list.push(detail("medicalNeed","건강·의료 분야에서 어떤 도움이 필요한가요?","진단명·장애 등록·의료기록을 받지 않고 필요한 도움만 구분합니다.","search_intent"));
 if(a.purpose==="education") {
  if(a.role!=="household")list.push(detail("educationStage",person+"의 교육 단계는 어떻게 되나요?","혜택을 받을 학습자의 단계입니다. 부모의 학력이나 나이를 자녀에게 적용하지 않아요."));
  list.push(detail("educationNeed","어떤 교육 지원을 찾으시나요?","학비·장학금·학습비 등 필요한 지원 종류만 선택합니다. 학교명과 성적은 지금 묻지 않아요.","search_intent"));
 }
 return list;
}
function targetProfile(input) {
 const a=cleanAnswers(input),topics={birth:["결혼·출산·육아"],elder:["복지·생활","보험·연금"],housing:["주거·부동산"],living:["복지·생활"],work:["취업·창업"],medical:["건강·의료"],education:["교육·장학"]};
 const out={interests:topics[a.purpose]||[]};
 if(a.region) out.region=a.region;
 if(a.purpose!=="birth" && a.age!==undefined) out.age=a.age;
 if(a.role==="self" && a.children!==undefined) out.children=a.children;
 return BFMatch.cleanProfile(out);
}
function guidedCandidates(rows,input,query="") {
 const a=cleanAnswers(input),key=String(query).toLowerCase().replace(/[^가-힣a-z0-9]/g,"");
 if(!a.purpose && !key) return [];
 const profile=targetProfile(a);
 return rows.flatMap(row=>{
  const fields=row.fields||{},text=Object.values(fields).join(" "),keyed=text.toLowerCase().replace(/[^가-힣a-z0-9]/g,"");
  if(key && !keyed.includes(key)) return [];
  const match=BFMatch.rankCandidate(row,profile);
  if(key) {match.score+=1;match.reasons.push("검색어 관련 안내");}
  const add=(terms,reason)=>{if(terms.some(word=>text.includes(word))) {match.score+=2;match.reasons.push(reason);}};
  if(a.stage==="expecting") add(["임신","임산부","출산"],"출산 전 관련 안내");
  if(a.stage==="born") add(["출산","양육","아동","육아"],"출산 후 관련 안내");
  if(a.care==="single") add(["한부모"],"한부모 양육 관련 안내 · 자격 확인 필요");
  if(a.care==="grandparent") add(["조손"],"조손 양육 관련 안내 · 자격 확인 필요");
  if(a.purpose==="elder" && a.need==="daily") add(["돌봄","요양"],"일상 돌봄 관련 안내");
  if(a.purpose==="elder" && a.need==="medical") add(["의료","건강"],"의료·건강 관련 안내");
  for(const [field,values] of Object.entries(INTENT_TERMS)) {
   const terms=values[a[field]];
   if(terms) add(terms,DETAIL_OPTIONS[field].find(([value])=>value===a[field])[1]+" 관련 안내 · 자격 확인 필요");
  }
  return match.score>0?[{...match,assessment:"확인 필요"}]:[];
 }).sort((a,b)=>b.score-a.score||a.row.id.localeCompare(b.row.id));
}
function cleanFamilies(value) {
 if(!value || value.version!==1 || !Array.isArray(value.families)) throw new Error("INVALID_FAMILIES");
 return value.families.slice(0,50).map(item=>{
  if(!item || typeof item.id!=="string" || !/^[a-zA-Z0-9-]{1,80}$/.test(item.id)) throw new Error("INVALID_FAMILY_ID");
  return {id:item.id,answers:cleanAnswers(item.answers)};
 });
}
function semanticCandidates(rows,input,hits) {
 const records=new Map(rows.map(row=>[row.id,row]));
 const local=new Map(guidedCandidates(rows,input).map(match=>[match.row.id,match]));
 return hits.flatMap(hit=>{
  const row=records.get(hit.record_id);if(!row)return [];
  const match=local.get(row.id)||BFMatch.rankCandidate(row,targetProfile(input));
  return [{...match,score:hit.cosine*10+Math.min(match.score,5),evidence:hit,
   reasons:["설명 문장 의미 검색",...match.reasons],assessment:"확인 필요"}];
 }).sort((a,b)=>b.score-a.score||a.row.id.localeCompare(b.row.id));
}
function initializeGuided() {
 const root=document.getElementById("guided-search");if(!root) return;
 const el=id=>document.getElementById(id),make=(tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined) node.textContent=text;if(cls) node.className=cls;return node;};
 let answers={},index=0,records=null,families=[],familyId=null,loadVersion=0,renderVersion=0;
 const query=root.dataset.query||"";
 const message=text=>{el("guided-message").textContent=text;};
 const hideResults=()=>{++renderVersion;el("guided-output").classList.add("hidden");el("guided-results").replaceChildren();el("save-family-panel").classList.add("hidden");};
 function showQuestion(focus=true) {
  const list=questions(answers);index=Math.min(index,list.length-1);const q=list[index];
  el("question-panel").classList.remove("hidden");el("question-progress").textContent=(index+1)+" / "+list.length+" · 모든 개인정보 질문은 선택";
  el("question-title").textContent=q.title;el("question-why").textContent=q.why;
  const input=make(q.options?"select":"input");input.id="guided-answer";input.setAttribute("aria-label",q.title);
  if(q.options) {
   const blank=make("option","선택하지 않음 · 모름");blank.value="";input.append(blank);
   for(const [value,label] of q.options) {const option=make("option",label);option.value=value;input.append(option);}
  } else {input.type="number";input.min=String(q.min||0);input.max=String(q.max);input.step="1";input.inputMode="numeric";input.placeholder="선택 입력";}
  input.value=answers[q.key]===undefined?"":String(answers[q.key]);el("question-input").replaceChildren(input);
  el("previous-question").disabled=index===0;message("");if(focus) el("question-title").focus();
 }
 function capture(skip=false) {
  const q=questions(answers)[index],old=answers[q.key],value=skip?"":el("guided-answer").value;
  if(!skip && !el("question-form").reportValidity()) return false;
  if(value==="") delete answers[q.key];else answers[q.key]=q.options?value:Number(value);
  if(q.key==="role" && old!==answers.role) {const role=answers.role;answers=role?{role}:{};familyId=null;}
  if(q.key==="purpose" && old!==answers.purpose) {
   const {role,purpose,region}=answers;answers=cleanAnswers({role,purpose,region});
  }
  if(q.key==="stage" && answers.stage!=="born") delete answers.months;
  if(q.key==="care" && answers.care!=="single") delete answers.recognized;
  answers=cleanAnswers(answers);return true;
 }
 async function showCandidates() {
  if(!answers.purpose && !query) {message("지원 분야만 선택해도 시작할 수 있어요. 개인정보는 필요하지 않습니다.");index=1;showQuestion();message("지원 분야를 선택하거나 검색어로 시작해 주세요.");return;}
  const version=++renderVersion;
  el("question-panel").classList.add("hidden");el("guided-output").classList.remove("hidden");
  el("guided-summary").textContent=[ROLES[answers.role]||"대상 미선택",PURPOSES[answers.purpose],answers.region,query&&"검색어: "+query].filter(Boolean).join(" · ");
  el("guided-results").replaceChildren();el("guided-more").classList.add("hidden");el("guided-results-status").textContent="관련 안내를 찾고 있어요.";
  try {
   if(!records) {const response=await fetch("/api/catalog",{credentials:"omit",cache:"no-store"});if(!response.ok) throw new Error("catalog");records=(await response.json()).records;}
   if(version!==renderVersion) return;
   let matches,searchNote;
   try {
    // Only public search terms and a broad purpose leave the browser; family answers stay here.
    const params=new URLSearchParams();if(query)params.set("q",query);if(answers.purpose)params.set("purpose",answers.purpose);
    const response=await fetch("/api/semantic?"+params,{credentials:"omit",cache:"no-store"});
    if(!response.ok)throw new Error("semantic");
    const semantic=await response.json();
    if(version!==renderVersion)return;
    matches=semanticCandidates(records,answers,semantic.results);
    const c=semantic.coverage;
    searchNote="BGE-M3 의미 검색 · "+(c.complete?"전체 검색 데이터":c.indexed_chunks.toLocaleString()+" / "+c.eligible_chunks.toLocaleString()+"개 조각 준비 중 · 일부 데이터만 검색")+" · ";
   } catch {
    if(version!==renderVersion)return;
    matches=guidedCandidates(records,answers,query);searchNote="의미 검색을 사용할 수 없어 기존 키워드 방식으로 표시합니다. · ";
   }
   let shown=0;
   const unanswered=questions(answers).filter(q=>!["role","purpose"].includes(q.key) && answers[q.key]===undefined).length;
   el("guided-results-status").textContent=searchNote+(matches.length?matches.length+"건의 관련 후보 · 미응답 "+unanswered+"개 항목은 확인 필요입니다.":"현재 검색 범위에서 관련 후보를 찾지 못했습니다. 자격 미충족 판정은 아닙니다.");
   function more() {
    if(version!==renderVersion) return;
    for(const item of matches.slice(shown,shown+12)) {
     const {row,reasons}=item,f=row.fields,card=make("article",undefined,"benefit-card");
     const head=make("h2"),link=make("a",f.name||"제도 안내");link.href="/benefit?"+new URLSearchParams({id:row.id});head.append(link);
     card.append(make("span","자격 조건 확인 필요","badge"),head,make("div",f.agency||"기관 미확인","meta"),make("p",f.summary||f.benefit||"설명 미확인"));
     if(item.evidence) {
      const proof=make("details"),label=make("summary","검색 근거 문장 보기");
      proof.append(label,make("p",item.evidence.text),make("small","원문 항목: "+item.evidence.field+" · 의미 유사도는 자격 확률이 아닙니다."));card.append(proof);
     }
     const tags=make("div",undefined,"reasons");for(const reason of reasons.slice(0,3)) tags.append(make("span",reason,"reason"));card.append(tags);
     const additional=make("button","선택 · 관련 질문 더 보기","secondary");additional.type="button";additional.addEventListener("click",()=>{index=Math.max(2,questions(answers).findIndex(q=>!["role","purpose"].includes(q.key)&&answers[q.key]===undefined));hideResults();showQuestion();});card.append(additional);
     el("guided-results").append(card);
    }
    shown=Math.min(shown+12,matches.length);el("guided-more").classList.toggle("hidden",shown>=matches.length);
   }
   el("guided-more").onclick=more;more();
  } catch {if(version===renderVersion) el("guided-results-status").textContent="목록을 불러오지 못했습니다. 가족 답변은 브라우저에 유지됩니다. 다시 시도해 주세요.";}
 }
 el("question-form").addEventListener("submit",event=>{event.preventDefault();if(!capture())return;if(index+1<questions(answers).length){index++;showQuestion();}else showCandidates();});
 el("skip-question").addEventListener("click",()=>{capture(true);if(index+1<questions(answers).length){index++;showQuestion();}else showCandidates();});
 el("preview-candidates").addEventListener("click",()=>{if(capture())showCandidates();});
 el("previous-question").addEventListener("click",()=>{if(capture()){index=Math.max(0,index-1);showQuestion();}});
 el("edit-answers").addEventListener("click",()=>{hideResults();index=0;showQuestion();});
 el("continue-questions").addEventListener("click",()=>{hideResults();index=Math.max(2,questions(answers).findIndex(q=>!["role","purpose"].includes(q.key)&&answers[q.key]===undefined));showQuestion();});
 el("new-exploration").addEventListener("click",()=>{loadVersion++;answers={};families=[];familyId=null;index=0;hideResults();el("family-unlock-form").reset();el("family-save-form").reset();el("family-picker").classList.add("hidden");el("family-options").replaceChildren();el("family-unlock").classList.add("hidden");showQuestion();});
 function stored() {return sessionStorage.getItem(FAMILY_KEY)||localStorage.getItem(FAMILY_KEY);}
 el("load-family").addEventListener("click",()=>{try {if(!stored()) {message("저장한 가족 정보가 없습니다. 저장 없이 바로 탐색해도 됩니다.");return;}el("family-unlock").classList.remove("hidden");}catch {message("브라우저 저장소를 사용할 수 없습니다. 저장 없이 탐색해 주세요.");}});
 el("close-family-unlock").addEventListener("click",()=>{loadVersion++;el("family-unlock-form").reset();el("family-unlock").classList.add("hidden");});
 el("family-unlock-form").addEventListener("submit",async event=>{
  event.preventDefault();const version=++loadVersion,button=event.submitter;button.disabled=true;
  try {
   const loaded=await BFVault.decrypt(JSON.parse(stored()),el("family-unlock-password").value);
   if(version!==loadVersion)return;
   families=cleanFamilies(loaded);el("family-unlock-form").reset();el("family-unlock").classList.add("hidden");el("family-picker").classList.remove("hidden");el("family-options").replaceChildren();
   families.forEach((family,i)=>{const button=make("button",(ROLES[family.answers.role]||"대상 미선택")+" · "+(i+1)+"번째 저장","secondary");button.type="button";button.addEventListener("click",()=>{hideResults();answers={...family.answers};familyId=family.id;index=0;showQuestion();});el("family-options").append(button);});
  } catch {el("family-unlock-status").textContent="암호가 다르거나 저장 정보가 손상되었습니다.";}finally {button.disabled=false;}
 });
 el("delete-families").addEventListener("click",()=>{try {loadVersion++;sessionStorage.removeItem(FAMILY_KEY);localStorage.removeItem(FAMILY_KEY);families=[];familyId=null;el("family-options").replaceChildren();el("family-picker").classList.add("hidden");el("family-unlock-form").reset();el("family-unlock").classList.add("hidden");message("저장한 가족 정보를 삭제했습니다.");}catch {el("family-unlock-status").textContent="삭제하지 못했습니다. 브라우저 사이트 데이터를 확인해 주세요.";}});
 el("show-save-family").addEventListener("click",()=>{el("save-family-panel").classList.remove("hidden");el("family-save-status").textContent="";});
 el("cancel-save-family").addEventListener("click",()=>{el("family-save-form").reset();el("save-family-panel").classList.add("hidden");});
 el("family-save-form").addEventListener("submit",async event=>{
  event.preventDefault();const message=el("family-save-status"),password=el("family-password"),confirmation=el("family-password-confirm"),button=event.submitter;
  if(password.value!==confirmation.value) {message.textContent="보관 암호가 일치하지 않습니다.";return;}
  button.disabled=true;const saveVersion=renderVersion,saveLoadVersion=loadVersion;
  try {
   if(stored() && !families.length) {message.textContent="기존 가족 정보를 먼저 불러와 주세요. 덮어쓰지 않고 가족별로 추가합니다.";return;}
   const id=familyId||crypto.randomUUID(),next=families.filter(x=>x.id!==id).concat([{id,answers:cleanAnswers(answers)}]);
   if(next.length>50)throw new Error("LIMIT");
   const envelope=await BFVault.encrypt({version:1,families:next},password.value),raw=JSON.stringify(envelope);
   if(saveVersion!==renderVersion || saveLoadVersion!==loadVersion)return;
   if(el("family-remember").checked){localStorage.setItem(FAMILY_KEY,raw);sessionStorage.removeItem(FAMILY_KEY);}else{sessionStorage.setItem(FAMILY_KEY,raw);localStorage.removeItem(FAMILY_KEY);}
   families=next;familyId=id;el("family-save-form").reset();message.textContent="선택한 가족 정보를 암호화해 저장했습니다.";
  }catch {message.textContent="암호화 저장하지 못했습니다. 저장하지 않아도 계속 탐색할 수 있습니다.";}finally {button.disabled=false;}
 });
 el("question-controls").disabled=false;showQuestion(false);
}
if(typeof module!=="undefined"&&module.exports) module.exports={cleanAnswers,questions,targetProfile,guidedCandidates,semanticCandidates,cleanFamilies};
if(typeof document!=="undefined") initializeGuided();
