"use strict";
// Test-only PostgreSQL/WASM dependency lives under ignored data/, never in app dependencies.
const {PGlite}=require("../data/schema-validation/node_modules/@electric-sql/pglite");
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict");
async function main(){
 const db=new PGlite();
 const one=async(sql,args=[]) => (await db.query(sql,args)).rows[0];
 const reject=async(sql,args,pattern)=>assert.rejects(()=>db.query(sql,args),pattern);
 try{
  for(const file of ["001_core.sql","003_rule_review.sql","005_aurore_lifecycle.sql","006_object_names.sql"])
   await db.exec(fs.readFileSync(path.join(__dirname,"../database",file),"utf8"));
  await db.exec("SET search_path=bene_fit,public");
  await db.exec("INSERT INTO data_src(cd,nm) VALUES ('test','Test provider_cd'),('other','Other provider_cd')");
  const run=(await one("INSERT INTO ingest_run(src_cd,ds_nm) VALUES ('test','synthetic') RETURNING id")).id;
  const otherRun=(await one("INSERT INTO ingest_run(src_cd,ds_nm) VALUES ('other','synthetic') RETURNING id")).id;
  const program=(await one("INSERT INTO benefit DEFAULT VALUES RETURNING id")).id;
  const otherProgram=(await one("INSERT INTO benefit DEFAULT VALUES RETURNING id")).id;
  const record=(await one("INSERT INTO src_record(src_cd,ext_id,type_cd,benefit_id) VALUES ('test','1','program',$1) RETURNING id",[program])).id;
  await reject("INSERT INTO src_record(src_cd,ext_id,type_cd) VALUES ('test','1','program')",[],/unique/i);
  await reject("INSERT INTO src_snapshot(src_record_id,run_id,cont_hash,raw_json) VALUES ($1,$2,$3,'{}')",[record,otherRun,"a".repeat(64)],/different providers/);
  const snapshot=(await one("INSERT INTO src_snapshot(src_record_id,run_id,cont_hash,raw_json) VALUES ($1,$2,$3,'{}') RETURNING id",[record,run,"a".repeat(64)])).id;
  const version=(await one("INSERT INTO benefit_ver(benefit_id,cont_hash,nm) VALUES ($1,$2,'Test benefit') RETURNING id",[program,"b".repeat(64)])).id;
  await db.query("INSERT INTO benefit_ver_src(benefit_ver_id,src_snapshot_id) VALUES ($1,$2)",[version,snapshot]);
  const wrongVersion=(await one("INSERT INTO benefit_ver(benefit_id,cont_hash,nm) VALUES ($1,$2,'Other benefit') RETURNING id",[otherProgram,"c".repeat(64)])).id;
  await reject("INSERT INTO benefit_ver(benefit_id,cont_hash,nm) VALUES ($1,$2,'Duplicate current')",[program,"d".repeat(64)],/unique/i);
  await reject("INSERT INTO doc(benefit_ver_id,src_snapshot_id,parse_ver,cont_hash,fld_json) VALUES ($1,$2,'test',$3,'{}')",[wrongVersion,snapshot,"e".repeat(64)],/different or unmapped benefit/);
  const notice=(await one("INSERT INTO src_record(src_cd,ext_id,type_cd,benefit_id) VALUES ('test','notice-1','notice',$1) RETURNING id",[program])).id;
  const noticeSnapshot=(await one("INSERT INTO src_snapshot(src_record_id,run_id,cont_hash,raw_json) VALUES ($1,$2,$3,'{}') RETURNING id",[notice,run,"f".repeat(64)])).id;
  await reject("INSERT INTO aply_round(benefit_id,benefit_ver_id,src_record_id,src_snapshot_id,rnd_key,rev_no,ttl,period_type_cd,period_verify_yn) VALUES ($1,$2,$3,$4,'2026',1,'Notice','window',true)",[program,version,notice,noticeSnapshot],/check constraint/i);
  const round=(await one("INSERT INTO aply_round(benefit_id,benefit_ver_id,src_record_id,src_snapshot_id,rnd_key,rev_no,ttl) VALUES ($1,$2,$3,$4,'2026',1,'Notice') RETURNING id",[program,version,notice,noticeSnapshot])).id;
  await reject("INSERT INTO rule_set(benefit_ver_id,aply_round_id,rev_no) VALUES ($1,$2,1)",[wrongVersion,round],/foreign key/i);
  const document=(await one("INSERT INTO doc(benefit_ver_id,src_snapshot_id,parse_ver,cont_hash,fld_json) VALUES ($1,$2,'test',$3,'{}') RETURNING id",[version,snapshot,"e".repeat(64)])).id;
  await reject("UPDATE src_record SET benefit_id=$1 WHERE id=$2",[otherProgram,record],/explicit migration/);
  await reject("UPDATE ingest_run SET src_cd='other' WHERE id=$1",[run],/immutable/);
  const chunk_cont="Age 18 or older.";
  await db.query("INSERT INTO doc_chunk(id,doc_id,fld_nm,start_pos,end_pos,chunk_cont,loc_json,split_ver) VALUES ('evidence',$1,'target',0,$2,$3,'{}','test')",[document,chunk_cont.length,chunk_cont]);
  await db.exec("INSERT INTO fact_def(cd,value_type_cd,unit_cd,descr,compare_yn) VALUES ('age_years','number','years','Beneficiary age in complete years',true)");
  await db.exec("INSERT INTO question(id,rev_no,fact_cd,subj_role_cd,qstn_txt,help_cont) VALUES ('age-beneficiary@1',1,'age_years','beneficiary','Age?','Optional'),('age-applicant@1',1,'age_years','applicant','Age?','Optional')");
  await reject("INSERT INTO question(id,rev_no,subj_role_cd,qstn_txt,help_cont,optional_yn) VALUES ('required',1,'beneficiary','Age?','Help',false)",[],/check constraint/i);
  const rules=(await one("INSERT INTO rule_set(benefit_ver_id,rev_no,eff_start_dt,ref_basis,rvwr_id,review_dttm,rvw_note) VALUES ($1,1,'2026-01-01','As of application date','synthetic-reviewer',now(),'Synthetic fixture only') RETURNING id",[version])).id;
  const node=(await one("INSERT INTO rule_node(rule_set_id,type_cd,fact_cd,subj_role_cd,op_cd,cmp_val_json) VALUES ($1,'condition','age_years','beneficiary','gte','18') RETURNING id",[rules])).id;
  const approve="UPDATE rule_set SET stat_cd='approved' WHERE id=$1";
  await reject(approve,[rules],/matching question/);
  await reject("INSERT INTO rule_question(rule_node_id,rule_set_id,question_id,fact_cd,subj_role_cd) VALUES ($1,$2,'age-applicant@1','age_years','beneficiary')",[node,rules],/foreign key/i);
  await db.query("INSERT INTO rule_question(rule_node_id,rule_set_id,question_id,fact_cd,subj_role_cd) VALUES ($1,$2,'age-beneficiary@1','age_years','beneficiary')",[node,rules]);
  await reject(approve,[rules],/source evidence/);
  await db.query("INSERT INTO rule_evidence(rule_node_id,rule_set_id,chunk_id,start_pos,end_pos,quote_cont) VALUES ($1,$2,'evidence',0,$3,$4)",[node,rules,chunk_cont.length,"Age 99 or older."]);
  await reject(approve,[rules],/exact source text/);
  await db.query("UPDATE rule_evidence SET quote_cont=$2 WHERE rule_node_id=$1",[node,chunk_cont]);
  await db.query(approve,[rules]);
  assert.equal((await one("SELECT stat_cd FROM rule_set WHERE id=$1",[rules])).stat_cd,"approved");
  await reject("UPDATE rule_node SET cmp_val_json='99' WHERE id=$1",[node],/Only draft/);
  await reject("UPDATE fact_def SET unit_cd='months' WHERE cd='age_years'",[],/reviewed rules/);
  await reject("UPDATE question SET qstn_txt='Different descr' WHERE id='age-beneficiary@1'",[],/reviewed rules/);
  await reject("UPDATE doc_chunk SET chunk_cont='Age 99 or older.' WHERE id='evidence'",[],/append-only/);
  await reject("UPDATE src_snapshot SET raw_json=jsonb_build_object('changed',true) WHERE id=$1",[snapshot],/append-only/);
  await reject("UPDATE benefit_ver SET nm='Edited' WHERE id=$1",[version],/append-only/);
  assert.equal((await one("SELECT count(*)::int AS n FROM current_doc_chunk")).n,1);
  await db.query("UPDATE benefit_ver SET current_yn=false WHERE id=$1",[version]);
  assert.equal((await one("SELECT count(*)::int AS n FROM current_doc_chunk")).n,0);
  await db.query("UPDATE benefit_ver SET current_yn=true WHERE id=$1",[version]);
  await db.query("UPDATE rule_set SET stat_cd='retired' WHERE id=$1",[rules]);
  await reject(approve,[rules],/immutable/);
  const cycleRules=(await one("INSERT INTO rule_set(benefit_ver_id,rev_no) VALUES ($1,2) RETURNING id",[version])).id;
  const ids=["10000000-0000-0000-0000-000000000001","10000000-0000-0000-0000-000000000002","10000000-0000-0000-0000-000000000003"];
  await db.transaction(async tx=>{
   await tx.query("INSERT INTO rule_node(id,rule_set_id,type_cd) VALUES ($1,$2,'condition')",[ids[0],cycleRules]);
   await tx.query("INSERT INTO rule_node(id,rule_set_id,prnt_id,type_cd) VALUES ($1,$2,$3,'all'),($3,$2,$1,'all')",[ids[1],cycleRules,ids[2]]);
  });
  await reject(approve,[cycleRules],/disconnected or cyclic/);
  await reject("DELETE FROM benefit WHERE id=$1",[program],/Business deletion/);
  await reject("INSERT INTO ingest_run(src_cd,ds_nm,stat_cd) VALUES ('test','bad','NOT_A_CODE')",[],/common code/);
  const historyBefore=(await one('SELECT count(*)::int AS n FROM cmmn_cd_hist')).n;
  await db.exec("UPDATE cmmn_cd SET cd_nm='Reviewed name' WHERE cd='INGEST_STAT' AND prnt_cd_id IS NULL");
  assert.equal((await one('SELECT count(*)::int AS n FROM cmmn_cd_hist')).n,historyBefore+1);
  await db.query('UPDATE benefit SET del_yn=true WHERE id=$1',[program]);
  assert.equal((await one('SELECT count(*)::int AS n FROM current_doc_chunk')).n,0);
  assert.equal((await one('SELECT del_yn FROM doc_chunk WHERE id=$1',['evidence'])).del_yn,true);
  assert.equal((await one('SELECT del_yn FROM rule_node WHERE id=$1',[node])).del_yn,true);
  const available=await one("SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name='vector') AS vector_available");
  const report={engine:(await one("SELECT version() AS version")).version,
   tables:(await one("SELECT count(*)::int AS n FROM information_schema.tables WHERE table_schema='bene_fit' AND table_type='BASE TABLE'")).n,
   core_schema:"passed",review_guards:"passed",optional_vector_extension_available:available.vector_available};
  fs.writeFileSync(path.join(__dirname,"../data/schema-validation/result.json"),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));
 }finally{await db.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
