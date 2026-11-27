"""Download the selected public model into the project's local model directory."""
import json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    config=json.loads((ROOT/"config/embedding.json").read_text(encoding="utf-8-sig"))
    folder=(ROOT/config["local_directory"]).resolve()
    if not folder.is_relative_to((ROOT/"data").resolve()):
        raise ValueError("Model directory must be under project data/")
    os.environ["HF_HOME"]=str(ROOT/"data/model-comparison/hf-cache")
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=config["model"],revision=config["revision"],local_dir=folder,token=False,
        allow_patterns=["*.json","pytorch_model.bin","*.safetensors","*.model","vocab.txt","merges.txt","1_Pooling/*","2_Normalize/*"],max_workers=2)
    if not any(folder.glob("*.bin")) and not any(folder.glob("*.safetensors")):
        raise ValueError("Model weights missing")
    print("Selected embedding model ready:",config["model"],config["revision"])

if __name__=="__main__":main()
