"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vault=require("../web/profile_crypto.js");
const {cleanProfile,rankCandidate,recommend,searchCandidates}=require("../web/app.js");
async function main() {
 const profile=cleanProfile({age:0,income:0,assets:25000,children:0,region:"대전광역시",interests:["주거·부동산","주거·부동산","bad"],password:"never persist"});
 assert.equal(profile.age,0);assert.equal(profile.income,0);assert.equal(profile.children,0);
 assert.deepEqual(profile.interests,["주거·부동산"]);assert.ok(!Object.hasOwn(profile,"password"));
 assert.ok(!Object.hasOwn(cleanProfile({age:-1,income:true,children:99}),"age"));
 const password="Synthetic-Test-Only-945!";
 const a=await vault.encrypt(profile,password),b=await vault.encrypt(profile,password);
 assert.deepEqual(await vault.decrypt(a,password),profile);
 assert.notEqual(a.ciphertext,b.ciphertext);assert.notEqual(a.salt,b.salt);assert.notEqual(a.iv,b.iv);
 assert.ok(!JSON.stringify(a).includes("대전광역시"));
 assert.ok(!JSON.stringify(a).includes("income"));
 await assert.rejects(vault.decrypt(a,"wrong-password-123"));
 const bytes=Buffer.from(a.ciphertext,"base64");bytes[0]^=1;
 await assert.rejects(vault.decrypt({...a,ciphertext:bytes.toString("base64")},password));
 await assert.rejects(vault.encrypt(profile,"short"));
 await assert.rejects(vault.decrypt({...a,iterations:1},password));
 const row={id:"a",fields:{name:"주거 지원",region:"대전광역시"},source_condition_codes:{JA0110:null,JA0111:null}};
 const result=rankCandidate(row,{region:"대전광역시",interests:["주거·부동산"]});
 assert.ok(result.score>0 && result.reasons.length===2);
 assert.equal(rankCandidate(row,{income:100,assets:100}).score,0);
 assert.equal(rankCandidate(row,{age:0}).score,0);
 assert.ok(rankCandidate({...row,source_condition_codes:{JA0110:0,JA0111:18}},{age:0}).score>0);
 assert.equal(rankCandidate({...row,source_condition_codes:{JA0110:0,JA0111:120}},{age:30}).score,0);
 const fixtures=[
 {id:"housing",source:"gov24",review_group:"national_candidate",fields:{name:"주거급여",category:"주거"}},
 {id:"other",source:"gov24",fields:{name:"주거 정보",category:"일반행정"}},
 {id:"medical",source:"welfare-local",fields:{name:"의료 지원",region:"대전광역시"}}
 ];
 const interest={interests:["주거·부동산"]};
 assert.deepEqual(searchCandidates(fixtures,{}, "주거"),[]);
 assert.deepEqual(searchCandidates(fixtures,interest, ""),[]);
 assert.deepEqual(searchCandidates(fixtures,{income:3000},"주거"),[]);
 assert.deepEqual(searchCandidates(fixtures,interest,"의료"),[]);
 assert.deepEqual(searchCandidates(fixtures,interest,"주거",{scope:"national"}).map(x=>x.row.id),["housing"]);
 assert.deepEqual(searchCandidates(fixtures,interest,"주거",{source:"welfare-local"}),[]);
 assert.ok(searchCandidates(fixtures,interest,"주거 급여").length===1);
 const records=fs.readFileSync(path.join(__dirname,"../data/normalized/catalog.jsonl"),"utf8").trim().split("\n").map(JSON.parse);
 const real=recommend(records,{age:32,region:"대전광역시",children:1,interests:["주거·부동산"]});
 assert.ok(real.length>0 && real.every(x=>x.reasons.length>0 && x.score>0));
 assert.ok(real.some(x=>x.row.fields.name.includes("주거")));
 console.log("Profile validation, encrypted round trip, wrong password, tampering and ranking: PASS");
 console.log("Real catalog matching: PASS; candidates="+real.length);
}
main().catch(error=>{console.error(error);process.exitCode=1;});
