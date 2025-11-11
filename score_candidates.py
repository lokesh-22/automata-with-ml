#!/usr/bin/env python3
import argparse
import csv
import json
import math
import random
import re
from dataclasses import dataclass, asdict
from typing import List, Tuple, Dict

# -----------------------------
# Utilities
# -----------------------------

def load_lines(path: str) -> List[str]:
    with open(path, "r") as f:
        return [ln.rstrip("\n") for ln in f if ln.strip() != ""]

def ensure_anchored(rx: str) -> str:
    rx = rx.strip()
    if not rx.startswith("^"):
        rx = "^" + rx
    if not rx.endswith("$"):
        rx = rx + "$"
    return rx

def try_compile(rx: string):
    try:
        return re.compile(rx)
    except re.error:
        return None

def fullmatch(pat: re.Pattern, s: str) -> bool:
    return pat.fullmatch(s) is not None

def split_train_val(pos: List[str], neg: List[str], val_frac: float, seed: int):
    rnd = random.Random(seed)
    pos = pos[:]
    neg = neg[:]
    rnd.shuffle(pos)
    rnd.shuffle(neg)

    n_pos_val = max(1, int(len(pos) * val_frac))
    n_neg_val = max(1, int(len(neg) * val_frac))

    pos_val = pos[:n_pos_val]
    pos_tr  = pos[n_pos_val:]
    neg_val = neg[:n_neg_val]
    neg_tr  = neg[n_neg_val:]

    return (pos_tr, neg_tr), (pos_val, neg_val)

def confusion(y_true: List[int], y_pred: List[int]) -> Tuple[int,int,int,int]:
    # returns (TP, FP, FN, TN)
    TP = sum(1 for t,p in zip(y_true,y_pred) if t==1 and p==1)
    FP = sum(1 for t,p in zip(y_true,y_pred) if t==0 and p==1)
    FN = sum(1 for t,p in zip(y_true,y_pred) if t==1 and p==0)
    TN = sum(1 for t,p in zip(y_true,y_pred) if t==0 and p==0)
    return TP, FP, FN, TN

def f1_acc_from_conf(tp:int, fp:int, fn:int, tn:int) -> Tuple[float,float]:
    prec = tp / (tp+fp) if (tp+fp)>0 else 0.0
    rec  = tp / (tp+fn) if (tp+fn)>0 else 0.0
    f1   = 2*prec*rec / (prec+rec) if (prec+rec)>0 else 0.0
    acc  = (tp+tn) / max(1,(tp+fp+fn+tn))
    return f1, acc

def op_counts(regex_body: str) -> Dict[str, int]:
    ops = {'star':0, 'plus':0, 'qmark':0, 'union':0, 'groups':0}
    ops['star']   = regex_body.count('*')
    ops['plus']   = regex_body.count('+')
    ops['qmark']  = regex_body.count('?')
    ops['union']  = regex_body.count('|')
    ops['groups'] = regex_body.count('(') + regex_body.count(')')
    return ops

def strip_anchor_and_noncap(rx: str) -> str:
    # remove ^...$ wrapper if present; it’s fine if absent
    if rx.startswith("^"): rx = rx[1:]
    if rx.endswith("$"):  rx = rx[:-1]
    # leave non-capturing as-is; length still penalizes them (?: )
    return rx

@dataclass
class Metrics:
    regex: str
    body: str
    len_body: int
    ops_total: int
    star: int
    plus: int
    qmark: int
    union: int
    groups: int
    f1_val: float
    acc_val: float
    f1_tr: float
    acc_tr: float
    score: float
    tp_val: int
    fp_val: int
    fn_val: int
    tn_val: int

# -----------------------------
# Scoring model
# -----------------------------
def score_candidate(
    compiled: re.Pattern,
    body: str,
    pos_tr: List[str], neg_tr: List[str],
    pos_val: List[str], neg_val: List[str],
    w_f1: float, w_acc: float,
    lam_len: float, lam_ops: float, lam_overfit: float
) -> Metrics:

    # Train preds
    y_true_tr = [1]*len(pos_tr) + [0]*len(neg_tr)
    y_pred_tr = []
    for s in pos_tr + neg_tr:
        y_pred_tr.append(1 if fullmatch(compiled, s) else 0)
    tp_tr, fp_tr, fn_tr, tn_tr = confusion(y_true_tr, y_pred_tr)
    f1_tr, acc_tr = f1_acc_from_conf(tp_tr, fp_tr, fn_tr, tn_tr)

    # Val preds
    y_true_v = [1]*len(pos_val) + [0]*len(neg_val)
    y_pred_v = []
    for s in pos_val + neg_val:
        y_pred_v.append(1 if fullmatch(compiled, s) else 0)
    tp_v, fp_v, fn_v, tn_v = confusion(y_true_v, y_pred_v)
    f1_val, acc_val = f1_acc_from_conf(tp_v, fp_v, fn_v, tn_v)

    # Complexity
    ops = op_counts(body)
    ops_total = ops['star'] + ops['plus'] + ops['qmark'] + ops['union'] + ops['groups']
    len_body = len(body)

    # Overfit penalty (only if train >> val)
    overfit = max(0.0, f1_tr - f1_val)

    # Score (higher is better)
    # Normalize len penalty by a soft scale so lengths ~30–60 don’t dominate
    len_pen = (len_body / 50.0)
    score = (w_f1 * f1_val) + (w_acc * acc_val) - (lam_len * len_pen) - (lam_ops * ops_total) - (lam_overfit * overfit)

    return Metrics(
        regex=ensure_anchored(body),
        body=body,
        len_body=len_body,
        ops_total=ops_total,
        star=ops['star'],
        plus=ops['plus'],
        qmark=ops['qmark'],
        union=ops['union'],
        groups=ops['groups'],
        f1_val=f1_val,
        acc_val=acc_val,
        f1_tr=f1_tr,
        acc_tr=acc_tr,
        score=score,
        tp_val=tp_v, fp_val=fp_v, fn_val=fn_v, tn_val=tn_v
    )

# -----------------------------
# Main pipeline
# -----------------------------
def main():
    ap = argparse.ArgumentParser(description="Score candidate regexes against good/bad strings and select the best.")
    ap.add_argument("--good", default="good.txt")
    ap.add_argument("--bad", default="bad.txt")
    ap.add_argument("--candidates", default="candidates.txt")
    ap.add_argument("--val_frac", type=float, default=0.30, help="Validation fraction (0..1).")
    ap.add_argument("--seed", type=int, default=42)

    # Weights & penalties
    ap.add_argument("--w_f1", type=float, default=0.70, help="Weight for validation F1.")
    ap.add_argument("--w_acc", type=float, default=0.20, help="Weight for validation accuracy.")
    ap.add_argument("--lam_len", type=float, default=0.10, help="Penalty weight for regex length (normalized).")
    ap.add_argument("--lam_ops", type=float, default=0.02, help="Penalty per operator (* + ? | parentheses).")
    ap.add_argument("--lam_overfit", type=float, default=0.10, help="Penalty for (F1_train - F1_val) if positive.")

    ap.add_argument("--top_k", type=int, default=10)
    ap.add_argument("--out_jsonl", default="scored_candidates.jsonl")
    ap.add_argument("--out_csv", default="top_candidates.csv")
    ap.add_argument("--out_best", default="best_regex.txt")
    args = ap.parse_args()

    # Load data
    pos = load_lines(args.good)
    neg = load_lines(args.bad)
    if not pos or not neg:
        raise SystemExit("❌ Need non-empty good.txt and bad.txt")

    # Split
    (pos_tr, neg_tr), (pos_val, neg_val) = split_train_val(pos, neg, args.val_frac, args.seed)

    # Load candidates
    raw_cands = load_lines(args.candidates)
    bodies = []
    for rx in raw_cands:
        # Allow either anchored or body; compute body for metrics consistently
        rx = rx.strip()
        if rx.startswith("^") and rx.endswith("$"):
            body = rx[1:-1]
            if body.startswith("(?:") and body.endswith(")"):
                # optional: keep as-is; we don't try to unwrap non-capturing
                pass
            bodies.append(body)
        else:
            # treat as body
            bodies.append(rx)

    # Score all
    results: List[Metrics] = []
    bad_compiles = 0
    for body in bodies:
        anchored = ensure_anchored(body)
        pat = try_compile(anchored)
        if pat is None:
            bad_compiles += 1
            continue
        m = score_candidate(
            compiled=pat, body=body,
            pos_tr=pos_tr, neg_tr=neg_tr,
            pos_val=pos_val, neg_val=neg_val,
            w_f1=args.w_f1, w_acc=args.w_acc,
            lam_len=args.lam_len, lam_ops=args.lam_ops, lam_overfit=args.lam_overfit
        )
        results.append(m)

    if not results:
        raise SystemExit("❌ No valid candidates compiled. Check candidates.txt format.")

    # Rank
    results.sort(key=lambda r: (-r.score, -r.f1_val, -r.acc_val, r.len_body, r.ops_total, r.body))

    # Save JSONL
    with open(args.out_jsonl, "w") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    # Save CSV (Top-K)
    top_k = results[:max(1, args.top_k)]
    with open(args.out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","regex","f1_val","acc_val","f1_tr","acc_tr","score","len","ops","star","plus","qmark","union","groups","tp_val","fp_val","fn_val","tn_val"])
        for i, r in enumerate(top_k, start=1):
            w.writerow([i, r.regex, f"{r.f1_val:.4f}", f"{r.acc_val:.4f}", f"{r.f1_tr:.4f}", f"{r.acc_tr:.4f}",
                        f"{r.score:.6f}", r.len_body, r.ops_total, r.star, r.plus, r.qmark, r.union, r.groups,
                        r.tp_val, r.fp_val, r.fn_val, r.tn_val])

    # Save best regex
    with open(args.out_best, "w") as f:
        f.write(results[0].regex + "\n")

    # Console summary
    print(f"✅i Scored {len(results)} candidates (skipped {bad_compiles} that failed to compile).")
    print(f"📄 Saved: {args.out_jsonl}, {args.out_csv}, {args.out_best}")
    print("\n🏆 Top candidates:")
    for i, r in enumerate(top_k, start=1):
        print(f"{i:2d}. {r.regex} | F1_val={r.f1_val:.4f} Acc_val={r.acc_val:.4f}  "
              f"F1_tr={r.f1_tr:.4f}  Score={r.score:.5f}  len={r.len_body} ops={r.ops_total}")

if __name__ == "__main__":
    main()
