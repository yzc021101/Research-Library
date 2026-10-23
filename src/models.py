"""Curated models supported by the installed FastEmbed runtime; no implicit download."""
from paths import ROOT, MODEL
import hashlib
import json
from pathlib import Path
import shutil

CATALOG = [
    {"id": MODEL, "name": "Multilingual MiniLM L12", "dimensions": 384, "download_gb": 0.22,
     "description": "轻量多语言模型，当前默认。", "source": "https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"},
    {"id": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2", "name": "Multilingual MPNet Base", "dimensions": 768, "download_gb": 1.0,
     "description": "多语言备选，模型更大，需对比实际召回效果。", "source": "https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2"},
    {"id": "intfloat/multilingual-e5-large", "name": "Multilingual E5 Large", "dimensions": 1024, "download_gb": 2.24,
     "description": "多语言检索模型，运行与重建索引需要更多资源。", "source": "https://huggingface.co/intfloat/multilingual-e5-large"},
]

def spec(model_id):
    for item in CATALOG:
        if item["id"] == model_id: return item
    raise ValueError("未知模型，请选择列表中的模型。")

def asset_marker(model_id):
    return ROOT / "data/model-assets" / (hashlib.sha256(model_id.encode()).hexdigest()[:16] + ".json")

def mark_downloaded(model_id):
    path = asset_marker(model_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": model_id, "validated": True}))

def model_cache(model_id):
    private = ROOT/'cache/model-packages'/hashlib.sha256(model_id.encode()).hexdigest()[:16]
    # Reuse the existing default model without copying or changing the user's cache.
    legacy = ROOT/'cache/models'
    if model_id == MODEL and any(legacy.glob('models--qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/snapshots/*/*.onnx')):
        return legacy
    return private

def available(model_id):
    folder = model_cache(model_id)
    return folder.exists() and any(folder.rglob('*.onnx')) and (folder == ROOT/'cache/models' or asset_marker(model_id).exists())

def remove_asset(model_id):
    folder = model_cache(model_id)
    if folder == ROOT/'cache/models':
        raise ValueError('这是旧版共享模型缓存，请保留；新版独立下载的模型可以在此卸载。')
    if folder.exists(): shutil.rmtree(folder)
    asset_marker(model_id).unlink(missing_ok=True)

def catalog(active):
    return [{**item, "active": item["id"] == active,
             "downloaded": available(item["id"])} for item in CATALOG]

def create_embedder(model_id, allow_download=False):
    spec(model_id)
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from fastembed import TextEmbedding
    from resource_budget import embedding_threads
    raw = TextEmbedding(model_name=model_id, cache_dir=str(model_cache(model_id)),
                        local_files_only=not allow_download, threads=embedding_threads())
    return EmbeddingAdapter(model_id, raw)

class EmbeddingAdapter:
    def __init__(self, model_id, raw):
        self.model_id, self.raw = model_id, raw
    def query_embed(self, query):
        # Installed FastEmbed's E5 wrapper does not insert these required prefixes.
        if self.model_id == "intfloat/multilingual-e5-large":
            yield from self.raw.embed(["query: " + query])
        else: yield from self.raw.query_embed(query)
    def passage_embed(self, texts, **kwargs):
        if self.model_id == "intfloat/multilingual-e5-large":
            yield from self.raw.embed(("passage: " + text for text in texts), **kwargs)
        else: yield from self.raw.passage_embed(texts, **kwargs)

def table_schema(model_id):
    import pyarrow as pa
    return pa.schema([pa.field("chunk_id", pa.string()), pa.field("doc_id", pa.string()),
                      pa.field("vector", pa.list_(pa.float32(), spec(model_id)["dimensions"]))])
