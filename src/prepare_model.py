from paths import ROOT, MODEL
from fastembed import TextEmbedding
import json

if __name__ == "__main__":
    model = TextEmbedding(model_name=MODEL, cache_dir=str(ROOT / "cache/models"), threads=2)
    vector = next(model.embed(["Vera Rubin memory capacity"]))
    print(json.dumps({"model": MODEL, "dimensions": len(vector), "ready": True}))
