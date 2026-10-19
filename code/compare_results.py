"""Compare reproduced JSON results with the original ones, number by number.

    python compare_results.py <original_dir> <reproduced_dir> <out.csv> [file ...]

Every numeric leaf is matched by its JSON path.  Output columns:
file, path, original, reproduced, abs_diff, rel_diff.  Leaves present on only one side are
listed with an empty value on the other side.
"""
import csv
import json
import sys
from pathlib import Path


def leaves(x, prefix=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from leaves(v, f"{prefix}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from leaves(v, f"{prefix}[{i}]")
    elif isinstance(x, bool) or x is None:
        return
    elif isinstance(x, (int, float)):
        yield prefix, float(x)


def main():
    orig, repro, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    files = sys.argv[4:] or sorted(p.name for p in repro.glob("*.json") if (orig / p.name).exists())
    rows = []
    for f in files:
        a = dict(leaves(json.loads((orig / f).read_text(encoding="utf-8"))))
        b = dict(leaves(json.loads((repro / f).read_text(encoding="utf-8"))))
        for k in list(a) + [k for k in b if k not in a]:
            va, vb = a.get(k), b.get(k)
            d = abs(va - vb) if va is not None and vb is not None else None
            r = d / abs(va) if d is not None and va else None
            rows.append({"file": f, "path": k, "original": va, "reproduced": vb,
                         "abs_diff": d, "rel_diff": None if r is None else round(r, 6)})
        n = sum(1 for r in rows if r["file"] == f)
        same = sum(1 for r in rows if r["file"] == f and r["abs_diff"] == 0)
        close = sum(1 for r in rows if r["file"] == f and r["abs_diff"] is not None and r["abs_diff"] <= 0.005)
        only = sum(1 for r in rows if r["file"] == f and r["abs_diff"] is None)
        print(f"{f}: {n} numbers, identical {same}, |diff|<=0.005 {close}, only on one side {only}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "path", "original", "reproduced", "abs_diff", "rel_diff"])
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
