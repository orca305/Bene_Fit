"""Run one pinned embedding model against the frozen welfare retrieval pilot."""
import argparse,json,os,sys,time,threading,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/model-comparison"
MODELS={"bge-m3":("BAAI/bge-m3","5617a9f61b028005a4858fdac845db406aefb181"),
        "kure-v3":("nlpai-lab/KURE-v3","5b0494e801cd5cc21234012df1b83cfdb42b2065")}

def measure(vectors,queries,docs,np,dimensions):
    if dimensions:
        vectors=vectors[:,:dimensions];queries=queries[:,:dimensions]
    vectors=vectors/np.linalg.norm(vectors,axis=1,keepdims=True)
    queries=queries/np.linalg.norm(queries,axis=1,keepdims=True)
    matrix=queries@vectors.T
    data=json.loads((OUT/"evaluation.json").read_text(encoding="utf-8"))
    details=[]
    for i,case in enumerate(data["queries"]):
        order=np.argsort(-matrix[i],kind="stable")
        gold=set(case["relevant_chunk_ids"])
        ranks=[rank for rank,j in enumerate(order,1) if docs[int(j)]["id"] in gold]
        record_rank=next((rank for rank,j in enumerate(order,1) if docs[int(j)]["record_id"]==case["record_id"]),None)
        details.append({"id":case["id"],"query":case["query"],"first_evidence_rank":min(ranks),"first_record_rank":record_rank,
                        "top10":[{"chunk_id":docs[int(j)]["id"],"record_id":docs[int(j)]["record_id"],"cosine":float(matrix[i,j])} for j in order[:10]]})
    return {"dimension":int(vectors.shape[1]),"evidence_hit_at_1":sum(x["first_evidence_rank"]<=1 for x in details)/len(details),
      "evidence_hit_at_5":sum(x["first_evidence_rank"]<=5 for x in details)/len(details),
      "evidence_hit_at_10":sum(x["first_evidence_rank"]<=10 for x in details)/len(details),
      "mrr":sum(1/x["first_evidence_rank"] for x in details)/len(details),
      "record_hit_at_5":sum(x["first_record_rank"]<=5 for x in details)/len(details),
      "per_query":details}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("model",choices=MODELS);args=parser.parse_args()
    os.environ["HF_HOME"]=str(OUT/"hf-cache")
    os.environ["TOKENIZERS_PARALLELISM"]="false"
    import numpy as np
    import torch,psutil,transformers,sentence_transformers,huggingface_hub
    from sentence_transformers import SentenceTransformer
    from huggingface_hub import snapshot_download
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    evaluation=(OUT/"evaluation.json").read_bytes()
    if hashlib.sha256(evaluation).hexdigest()!=(OUT/"evaluation.sha256").read_text():
        raise ValueError("Evaluation changed after freezing")
    repo,revision=MODELS[args.model]
    folder=OUT/"models"/args.model
    print(f"Downloading pinned model {repo} {revision}",flush=True)
    start=time.perf_counter()
    snapshot_download(repo_id=repo,revision=revision,local_dir=folder,token=False,
      allow_patterns=["*.json","*.safetensors","pytorch_model.bin","*.model","merges.txt","vocab.txt","1_Pooling/*","2_Normalize/*"],
      max_workers=2)
    download=time.perf_counter()-start
    data=json.loads((OUT/"evaluation.json").read_text(encoding="utf-8"))
    docs=data["documents"];texts=[d["input"] for d in docs]
    questions=[q["query"] for q in data["queries"]]
    process=psutil.Process();memory={"peak_rss":process.memory_info().rss};stop=threading.Event()
    def sample():
        while not stop.wait(.1):
            memory["peak_rss"]=max(memory["peak_rss"],process.memory_info().rss)
    thread=threading.Thread(target=sample,daemon=True);thread.start()
    print(f"Loading {args.model} on CPU, float32, 4 threads",flush=True)
    start=time.perf_counter()
    model=SentenceTransformer(str(folder),device="cpu",model_kwargs={"dtype":torch.float32,"attn_implementation":"sdpa"},trust_remote_code=False)
    model.max_seq_length=8192
    load=time.perf_counter()-start
    doc_prefix="passage: " if args.model=="kure-v3" else ""
    query_prefix="query: " if args.model=="kure-v3" else ""
    model.prompts["document"]=doc_prefix;model.prompts["query"]=query_prefix
    lengths=[len(x) for x in model.tokenizer([doc_prefix+t for t in texts]+[query_prefix+q for q in questions],truncation=False)["input_ids"]]
    if max(lengths)>8192:raise ValueError("Input exceeds model context; no truncation allowed")
    model.encode([questions[0]],prompt_name="query",batch_size=1,normalize_embeddings=True,show_progress_bar=False)
    print(f"Encoding {len(docs)} documents; max input tokens={max(lengths)}",flush=True)
    document_vectors=[];start=time.perf_counter()
    for i in range(0,len(texts),16):
        block=model.encode(texts[i:i+16],prompt_name="document",batch_size=2,normalize_embeddings=True,show_progress_bar=False,convert_to_numpy=True)
        document_vectors.append(block.astype(np.float32))
        print(f"{args.model}: documents {min(i+16,len(texts))}/{len(texts)}; elapsed {time.perf_counter()-start:.1f}s",flush=True)
    document_seconds=time.perf_counter()-start;vectors=np.concatenate(document_vectors)
    query_vectors=[];latencies=[]
    for i,query in enumerate(questions):
        start=time.perf_counter()
        value=model.encode([query],prompt_name="query",batch_size=1,normalize_embeddings=True,show_progress_bar=False,convert_to_numpy=True)
        latencies.append(time.perf_counter()-start);query_vectors.append(value.astype(np.float32))
        if (i+1)%8==0:print(f"{args.model}: queries {i+1}/{len(questions)}",flush=True)
    query_vectors=np.concatenate(query_vectors)
    results=[measure(vectors,query_vectors,docs,np,None)]
    if args.model=="kure-v3":results.append(measure(vectors,query_vectors,docs,np,1024))
    stop.set();thread.join();memory["peak_rss"]=max(memory["peak_rss"],process.memory_info().rss)
    np.savez_compressed(OUT/(args.model+"-vectors.npz"),documents=vectors,queries=query_vectors)
    result={"model":repo,"revision":revision,"device":"cpu","dtype":"float32","threads":4,"batch_size":2,
      "document_count":len(docs),"query_count":len(questions),"max_input_tokens":max(lengths),"truncated_inputs":0,
      "document_prompt":doc_prefix,"query_prompt":query_prefix,"download_seconds":download,"model_load_seconds":load,
      "document_encoding_seconds":document_seconds,"documents_per_second":len(docs)/document_seconds,
      "query_latency_median_ms":float(np.median(latencies)*1000),"query_latency_p95_ms":float(np.percentile(latencies,95)*1000),
      "peak_process_rss_gib":memory["peak_rss"]/2**30,"query_latencies_ms":[x*1000 for x in latencies],
      "vector_bytes":vectors.nbytes,"evaluation_sha256":(OUT/"evaluation.sha256").read_text(),
      "packages":{p.__name__:p.__version__ for p in (torch,transformers,sentence_transformers,huggingface_hub,np,psutil)},
      "results":results}
    (OUT/(args.model+"-result.json")).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("results","query_latencies_ms")},ensure_ascii=False,indent=2),flush=True)
    print(json.dumps([{k:v for k,v in r.items() if k!="per_query"} for r in results],ensure_ascii=False),flush=True)

if __name__=="__main__":main()
