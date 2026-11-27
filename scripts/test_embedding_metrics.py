import json
import numpy as np
from benchmark_embedding import OUT,measure
data=json.loads((OUT/"evaluation.json").read_text(encoding="utf-8"))
docs=data["documents"]
vectors=np.eye(len(docs),dtype=np.float32)
lookup={doc["id"]:i for i,doc in enumerate(docs)}
queries=np.stack([vectors[lookup[case["relevant_chunk_ids"][0]]] for case in data["queries"]])
result=measure(vectors,queries,docs,np,None)
assert result["evidence_hit_at_1"]==1 and result["mrr"]==1
assert result["record_hit_at_5"]==1
print("Retrieval metric checks passed")
