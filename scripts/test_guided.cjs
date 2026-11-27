"use strict";
const assert=require("node:assert/strict");
const {cleanAnswers,questions,targetProfile,guidedCandidates,semanticCandidates,cleanFamilies}=require("../web/guided.js");
const vault=require("../web/profile_crypto.js");
async function main() {
 assert.deepEqual(cleanAnswers({age:"",months:null,children:0,order:0,income:999,region:"unknown"}),{children:0});
 const general=questions({});assert.ok(general.every(q=>!q.required));
 assert.ok(!general.some(q=>q.key==="age"));
 const expected={housing:["housingNeed","tenure"],living:["livingNeed"],work:["workNeed","workState"],medical:["medicalNeed"],education:["educationStage","educationNeed"]};
 for(const [purpose,keys] of Object.entries(expected)) {
  const qs=questions({role:"child",purpose});
  assert.ok(keys.every(key=>qs.some(q=>q.key===key)),purpose);
  assert.ok(qs.every(q=>!q.required));
  assert.ok(qs.find(q=>q.key==="age").title.includes("대상 자녀"));
  assert.ok(!qs.some(q=>["income","assets","diagnosis","birthdate"].includes(q.key)));
 }
 assert.ok(!questions({role:"household",purpose:"work"}).some(q=>["age","workState"].includes(q.key)));
 assert.ok(!questions({role:"household",purpose:"education"}).some(q=>["age","educationStage"].includes(q.key)));
 assert.ok(!questions({role:"household",purpose:"elder"}).some(q=>["age","cohabitation"].includes(q.key)));
 assert.deepEqual(cleanAnswers({role:"household",purpose:"work",age:40,workState:"employed",workNeed:"training",medicalNeed:"cost"}),{role:"household",purpose:"work",workNeed:"training"});
 assert.deepEqual(cleanAnswers({purpose:"housing",tenure:"own",housingNeed:"unknown",stage:"born",months:6}),{purpose:"housing",tenure:"own"});
 assert.ok(!Object.hasOwn(cleanAnswers({purpose:"birth",stage:"expecting",months:6,age:35}),"months"));
 assert.ok(!Object.hasOwn(cleanAnswers({purpose:"birth",care:"together",recognized:"yes"}),"recognized"));
 const child=questions({role:"child",purpose:"birth",stage:"born",care:"single"});
 assert.ok(child.some(q=>q.key==="months"));assert.ok(child.some(q=>q.key==="recognized"));
 assert.ok(!questions({purpose:"birth",care:"together"}).some(q=>q.key==="recognized"));
 assert.ok(!questions({purpose:"birth",stage:"expecting"}).some(q=>q.key==="months"));
 const parent=questions({role:"parent",purpose:"elder"});
 assert.ok(parent.some(q=>q.key==="cohabitation") && parent.some(q=>q.key==="need"));
 assert.ok(!parent.some(q=>["income","assets","debt","recognized"].includes(q.key)));
 assert.ok(!Object.hasOwn(targetProfile({role:"child",purpose:"birth",age:35,months:6}),"age"));
 assert.equal(targetProfile({role:"parent",purpose:"elder",age:72}).age,72);
 const rows=[
 {id:"birth",fields:{name:"출산 지원",category:"출산",summary:"안내"}},
 {id:"single",fields:{name:"한부모 육아 지원",category:"육아"}},
 {id:"care",fields:{name:"노인 생활 돌봄",category:"생활지원"}}
 ];
 assert.deepEqual(guidedCandidates(rows,{}),[]);
 const minimal=guidedCandidates(rows,{purpose:"birth"});
 assert.ok(minimal.length && minimal.every(x=>x.assessment==="확인 필요"));
 assert.ok(minimal.some(x=>x.row.id==="single"));
 assert.ok(guidedCandidates(rows,{purpose:"birth",care:"single"}).find(x=>x.row.id==="single").reasons.some(x=>x.includes("한부모")));
 assert.ok(guidedCandidates(rows,{},"출산").length);
 const housingRows=[{id:"deposit",fields:{name:"전세 보증금 지원",category:"주거"}},{id:"rent",fields:{name:"청년 월세 지원",category:"주거"}}];
 assert.equal(guidedCandidates(housingRows,{purpose:"housing",housingNeed:"rent"})[0].row.id,"rent");
 assert.equal(guidedCandidates(housingRows,{purpose:"housing",housingNeed:"deposit"})[0].row.id,"deposit");
 assert.ok(guidedCandidates(housingRows,{purpose:"housing",tenure:"own"}).every(x=>x.assessment==="확인 필요"));
 const semantic=semanticCandidates(rows,{role:"child",purpose:"birth",age:35,months:6},[
  {record_id:"birth",cosine:0.8,text:"출산 후 지원",field:"target"},{record_id:"missing",cosine:0.9}]);
 assert.equal(semantic.length,1);assert.equal(semantic[0].row.id,"birth");
 assert.equal(semantic[0].evidence.text,"출산 후 지원");assert.equal(semantic[0].assessment,"확인 필요");
 const family={version:1,families:[{id:"child-1",answers:{role:"child",purpose:"birth",months:6}},{id:"parent-1",answers:{role:"parent",purpose:"elder",age:72}},
  {id:"self-1",answers:{role:"self",purpose:"housing",housingNeed:"rent",tenure:"monthly"}}]};
 const envelope=await vault.encrypt(family,"Synthetic-Family-Only-2026!");
 const loaded=cleanFamilies(await vault.decrypt(envelope,"Synthetic-Family-Only-2026!"));
 assert.equal(loaded[0].answers.months,6);assert.equal(loaded[1].answers.age,72);
 assert.equal(loaded[2].answers.housingNeed,"rent");assert.equal(loaded[2].answers.tenure,"monthly");
 assert.ok(!Object.hasOwn(loaded[0].answers,"age"));
 assert.throws(()=>cleanFamilies({version:1,families:[{id:"../bad"}]}));
 console.log("Guided questions, skipping, missing information, family separation and encrypted family storage: PASS");
}
main().catch(error=>{console.error(error);process.exitCode=1;});
