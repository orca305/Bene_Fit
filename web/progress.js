"use strict";
async function refreshEmbeddingProgress() {
 const panel=document.getElementById("embedding-progress");if(!panel)return;
 const text=(id,value)=>{document.getElementById(id).textContent=value;};
 try {
  const response=await fetch("/api/embedding-status",{cache:"no-store",credentials:"omit"});
  if(!response.ok)throw new Error("status");
  const data=await response.json(),s=data.coverage,p=data.progress||{};
  const pct=s.eligible_chunks?100*s.indexed_chunks/s.eligible_chunks:0;
  const meter=document.getElementById("embedding-meter");meter.max=s.eligible_chunks||1;meter.value=s.indexed_chunks;
  text("embedding-count",s.indexed_chunks.toLocaleString()+" / "+s.eligible_chunks.toLocaleString()+"개 ("+pct.toFixed(2)+"%)");
  const fresh=p.updated_at && Date.now()/1000-p.updated_at<120;
  const deleted=p.phase==="vectors_deleted";
  text("embedding-state",deleted?"기존 벡터 삭제 완료 · 데스크탑에서 새 모델 선택 예정":s.complete?"전체 생성 완료":p.running&&fresh?"전체 임베딩 생성 중":p.running?"새 진행 기록을 기다리는 중 · 작업 상태 확인 필요":"생성 대기 또는 중단 · 저장된 지점부터 재개 가능");
  const speed=p.run_completed&&p.elapsed_seconds?p.run_completed/p.elapsed_seconds:0;
  text("embedding-speed",deleted?"현재 생성 작업은 실행하지 않습니다.":speed?"실측 "+speed.toFixed(2)+"개/초 · 남은 시간 약 "+(s.pending_chunks/speed/3600).toFixed(1)+"시간 (현재 속도 기준, 변동 가능)":"처리 속도를 측정하고 있습니다.");
  text("embedding-updated",p.updated_at?"마지막 저장: "+new Date(p.updated_at*1000).toLocaleTimeString("ko-KR"):"아직 진행 기록이 없습니다.");
  text("embedding-step-two",deleted?"중단 · 새 모델 선택 대기":s.complete?"완료":"진행 중 · 생성된 범위만 검색 가능");
 } catch {text("embedding-state","진행 정보를 읽지 못했습니다. 5초 후 다시 확인합니다.");}
 setTimeout(refreshEmbeddingProgress,5000);
}
refreshEmbeddingProgress();
