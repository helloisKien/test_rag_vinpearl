"""DA10 — Phase 3b: Indexing. chunks.jsonl + embeddings.npy -> OpenSearch + Qdrant.

OpenSearch (BM25, source-of-truth chunk text):
  index `idx_hotel_chunks_v1.0` (alias `hotel_chunks`); _id = chunk_id;
  search field = embed_text (analyzer vi); lưu cả text RAW (cite) + field filter.
Qdrant (vector): collection `col_documents_v1.0`, 1024 cosine, payload nhẹ;
  point.id = uuid5(chunk_id) (Qdrant cần int/UUID), chunk_id nằm trong payload.

Chạy:  python pipeline/index.py   (sau embed.py)
"""
from __future__ import annotations
import json
import os
import sys
import uuid

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import settings  # noqa: E402

CHUNKS = "chunks.jsonl"
VEC = "embeddings.npy"
NS = uuid.UUID("00000000-0000-0000-0000-0000da10c0de")  # namespace cố định -> uuid5 deterministic

OS_MAPPING = {
    "settings": {
        "index": {
            "analysis": {
                "analyzer": {
                    "vi_default": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding"],
                    }
                }
            }
        }
    },
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "hotel_id": {"type": "long"},
            "source_type": {"type": "keyword"},
            "source_table": {"type": "keyword"},
            "source_column": {"type": "keyword"},
            "record_id": {"type": "integer"},
            "lang": {"type": "keyword"},
            "text": {"type": "text", "analyzer": "vi_default"},
            "embed_text": {"type": "text", "analyzer": "vi_default"},
            "city": {"type": "keyword"},
            "accommodation_type": {"type": "keyword"},
            "star_rating": {"type": "float"},
        }
    },
}


def load():
    chunks = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]
    vecs = np.load(VEC)
    if len(chunks) != len(vecs):
        sys.exit(f"Lệch số lượng: chunks={len(chunks)} vs vectors={len(vecs)}. Chạy lại embed.py.")
    return chunks, vecs


def index_opensearch(chunks):
    from opensearchpy import OpenSearch, helpers
    client = OpenSearch([{"host": settings.os_host, "port": settings.os_port}], http_compress=True)
    idx = settings.os_index
    if client.indices.exists(idx):
        client.indices.delete(idx)
    client.indices.create(idx, body=OS_MAPPING)

    def actions():
        for c in chunks:
            yield {"_index": idx, "_id": c["chunk_id"], "_source": c}

    ok, errs = helpers.bulk(client, actions(), chunk_size=1000, request_timeout=120)
    # alias hotel_chunks -> idx
    if client.indices.exists_alias(name=settings.os_alias):
        client.indices.delete_alias(index="_all", name=settings.os_alias)
    client.indices.put_alias(index=idx, name=settings.os_alias)
    cnt = client.count(index=idx)["count"]
    print(f"  OpenSearch: indexed ok={ok} errors={len(errs) if isinstance(errs, list) else errs} | _count={cnt} | alias={settings.os_alias}")


def index_qdrant(chunks, vecs):
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    coll = settings.qdrant_collection
    client.recreate_collection(
        collection_name=coll,
        vectors_config=VectorParams(size=settings.embed_dim, distance=Distance.COSINE),
    )
    BATCH = 512
    buf = []
    total = 0
    for c, v in zip(chunks, vecs):
        buf.append(PointStruct(
            id=str(uuid.uuid5(NS, c["chunk_id"])),
            vector=v.tolist(),
            payload={
                "chunk_id": c["chunk_id"], "hotel_id": c["hotel_id"],
                "source_type": c["source_type"], "city": c.get("city"),
                "accommodation_type": c.get("accommodation_type"),
                "star_rating": c.get("star_rating"),
            },
        ))
        if len(buf) >= BATCH:
            client.upsert(collection_name=coll, points=buf)
            total += len(buf); buf = []
    if buf:
        client.upsert(collection_name=coll, points=buf); total += len(buf)
    info = client.get_collection(coll)
    print(f"  Qdrant: upserted={total} | points_count={info.points_count} | collection={coll}")


def run():
    if not os.path.exists(VEC):
        sys.exit(f"Thiếu {VEC} — chạy pipeline/embed.py trước.")
    chunks, vecs = load()
    print(f"Index {len(chunks)} chunks (dim {vecs.shape[1]}) ...")
    index_opensearch(chunks)
    index_qdrant(chunks, vecs)
    print("✓ Indexing xong.")


if __name__ == "__main__":
    run()
