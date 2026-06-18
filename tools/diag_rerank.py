"""DA10 — DEBUG tốc độ rerank (tìm cấu hình đạt <500ms).

Đo CrossEncoder('bge-reranker-v2-m3') GPU fp16 với passage THẬT từ chunks.jsonl,
biến thiên max_length ∈ {512,256,128} và số passage ∈ {15,8,5}.
=> Biết nút thắt là compute (giảm theo max_len/n) hay overhead per-call (gần như cố định),
   và chọn cấu hình rerank cho p95 < 500ms.

Chạy:  python tools/diag_rerank.py
"""
from __future__ import annotations
import json
import time

import torch
from sentence_transformers import CrossEncoder

MODEL = "BAAI/bge-reranker-v2-m3"
QUERY = "khách sạn gần biển có hồ bơi cho gia đình"


def load_passages(n=15):
    texts = []
    for line in open("chunks.jsonl", encoding="utf-8"):
        texts.append(json.loads(line)["text"])
        if len(texts) >= n:
            break
    return texts


def main():
    print("cuda:", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")
    passages = load_passages(15)
    print("passage lengths (chars):", [len(p) for p in passages])

    for mlen in [512, 256, 128]:
        ce = CrossEncoder(MODEL, device="cuda", max_length=mlen)
        try:
            ce.model.half()
        except Exception as e:
            print("  half fail:", e)
        dev = next(ce.model.parameters()).device
        ce.predict([(QUERY, passages[0])])  # warmup
        line = [f"max_len={mlen} (device={dev})"]
        for n in [15, 8, 5]:
            pairs = [(QUERY, p) for p in passages[:n]]
            ts = []
            for _ in range(3):
                t0 = time.perf_counter()
                ce.predict(pairs)
                ts.append((time.perf_counter() - t0) * 1000)
            line.append(f"n={n}:{min(ts):.0f}ms")
        print("  " + " | ".join(line))
        del ce
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    print("\nXONG. Gửi bảng số cho assistant để chốt cấu hình rerank.")


if __name__ == "__main__":
    main()
