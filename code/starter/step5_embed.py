"""Step 5 (optional, GPU helps): embed overnight news and average it per (stock, trading day).

    pip install "sentence-transformers>=6" "torch==2.14.*"     # GTX 1050 Ti: use the cu126 wheel
    python step5_embed.py --news data/news_cnyes.jsonl --calendar data/prices/tw_trading_dates.csv \
        --model google/embeddinggemma-300m --dim 256 --out data/emb_overnight.npz

Only the 'overnight' window (previous close 13:30 -> 08:45 of day d) is embedded, because it is
the only window the step-4 models may use for day d.  Text = title + summary.
--dim keeps the first k dimensions (valid for Matryoshka-trained models such as EmbeddingGemma);
for other models leave it at 0 and reduce with PCA in step 4.
--dry-run uses random vectors so the pipeline can be tested without downloading a model.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from step3_align import at  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--news", required=True); ap.add_argument("--calendar", required=True)
    ap.add_argument("--model", default="google/embeddinggemma-300m")
    ap.add_argument("--dim", type=int, default=0); ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--out", default="data/emb_overnight.npz"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cal = pd.read_csv(a.calendar)["date"].tolist()
    days = [pd.Timestamp(d).date() for d in cal]
    closes = np.array([at(d, 13, 30) for d in days]); lates = np.array([at(d, 8, 45) for d in days])

    groups = defaultdict(list)          # (code, date) -> article indices
    texts, seen = [], set()
    with open(a.news, encoding="utf-8") as fh:
        for line in fh:
            x = json.loads(line)
            if x["newsId"] in seen:
                continue
            seen.add(x["newsId"])
            t = int(x["publishAt"]); j = int(np.searchsorted(closes, t, side="right"))
            if j >= len(cal) or t >= lates[j]:          # not in the overnight window of any day
                continue
            codes = [c for c in map(str, x.get("stock") or []) if c.isdigit()]
            if not codes:
                continue
            texts.append(((x.get("title") or "") + "。" + (x.get("summary") or ""))[:600])
            for c in codes:
                groups[(c, cal[j])].append(len(texts) - 1)
    print(len(texts), "overnight articles,", len(groups), "(stock, day) groups")

    if a.dry_run:
        vecs = np.random.default_rng(0).normal(size=(len(texts), a.dim or 64)).astype(np.float32)
    else:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(a.model)
        vecs = model.encode(texts, batch_size=a.batch, show_progress_bar=True, normalize_embeddings=True)
        if a.dim:
            vecs = vecs[:, :a.dim]
            vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    keys = sorted(groups)
    out = np.vstack([vecs[groups[k]].mean(0) for k in keys])
    np.savez_compressed(a.out, code=np.array([k[0] for k in keys]), date=np.array([k[1] for k in keys]), vec=out)
    print("saved", out.shape, "->", a.out)


if __name__ == "__main__":
    main()
