"use strict";
// Public question definitions only. No browser answers or encrypted profiles are read.
const {questions}=require("../web/guided.js");
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict");
const base=questions({}),roles=base.find(q=>q.key==="role").options.map(x=>x[0]);
const purposes=base.find(q=>q.key==="purpose").options.map(x=>x[0]),bank=[];
for(const role of roles)for(const purpose of purposes)
 for(const q of questions({role,purpose,stage:"born",care:"single"}))
  bank.push({id:`guided.${role}.${purpose}.${q.key}@1`,subject:q.subject||(["role","purpose"].includes(q.key)?"search_intent":role==="household"?"household":"beneficiary"),
   title:q.title,why:q.why,options:q.options||[]});
assert.equal(new Set(bank.map(q=>q.id)).size,bank.length);
const folder=path.join(__dirname,"../data/migration");fs.mkdirSync(folder,{recursive:true});
fs.writeFileSync(path.join(folder,"question_bank.json"),JSON.stringify(bank,null,2));
console.log(`Exported ${bank.length} public question definitions`);
