#!/usr/bin/env python3
import argparse
import itertools
import json
import math
import os
import re
from collections import defaultdict, Counter
from typing import List, Tuple, Set, Dict, Optional

DEFAULT_ALPHABET = ["a", "b"] 

class Expr:
    def kind(self) -> str: ...
    def children(self) -> Tuple["Expr", ...]: ...
    def op_count(self) -> int: ...
    def to_regex(self) -> str: ...
    def __hash__(self): return hash(self.to_key())
    def __eq__(self, other): return isinstance(other, Expr) and self.to_key() == other.to_key()
    def to_key(self) -> Tuple: ...

class Atom(Expr):
    __slots__ = ("lit",)
    def __init__(self, lit: str):
        self.lit = lit
    def kind(self): return "atom"
    def children(self): return tuple()
    def op_count(self): return 0
    def to_regex(self): return re.escape(self.lit) if len(self.lit) == 1 else f"(?:{re.escape(self.lit)})"
    def to_key(self): return ("atom", self.lit)

class Concat(Expr):
    __slots__ = ("parts",)
    def __init__(self, parts: List[Expr]):

        flat = []
        for p in parts:
            if isinstance(p, Concat):
                flat.extend(p.parts)
            else:
                flat.append(p)
        self.parts = tuple(flat)
    def kind(self): return "concat"
    def children(self): return self.parts
    def op_count(self): return 0 if len(self.parts) <= 1 else len(self.parts) - 1
    def to_regex(self):
        out = []
        for p in self.parts:
            if isinstance(p, Union):
                out.append(f"(?:{p.to_regex()})")
            else:
                out.append(p.to_regex())
        return "".join(out)
    def to_key(self): return ("concat", tuple(c.to_key() for c in self.parts))

class Union(Expr):
    __slots__ = ("alts",)
    def __init__(self, alts: List[Expr]):

        flat = []
        for a in alts:
            if isinstance(a, Union):
                flat.extend(a.alts)
            else:
                flat.append(a)

        uniq = {a.to_key(): a for a in flat}

        self.alts = tuple(uniq[k] for k in sorted(uniq.keys()))
    def kind(self): return "union"
    def children(self): return self.alts
    def op_count(self): return 0 if len(self.alts) <= 1 else len(self.alts) - 1
    def to_regex(self):
        return "|".join(a.to_regex() for a in self.alts)
    def to_key(self): return ("union", tuple(a.to_key() for a in self.alts))

class Unary(Expr):
    __slots__ = ("op","inner")
    def __init__(self, op: str, inner: Expr):
        self.op = op  # one of '*', '+', '?'
        self.inner = inner
    def kind(self): return f"unary:{self.op}"
    def children(self): return (self.inner,)
    def op_count(self): return 1
    def to_regex(self):

        if isinstance(self.inner, Atom):
            base = self.inner.to_regex()
        else:
            base = f"(?:{self.inner.to_regex()})"
        return f"{base}{self.op}"
    def to_key(self): return ("unary", self.op, self.inner.to_key())

def expr_length(expr: Expr) -> int:
    """Approximate regex textual length (for pruning/beam)."""
    return len(expr.to_regex())

def total_ops(expr: Expr) -> int:
    """Total operator count (binary + unary)."""
    c = expr.op_count()
    for ch in expr.children():
        c += total_ops(ch)
    return c

def anchor(regex_body: str) -> str:
    return f"^{regex_body}$"

def valid_literals_only(regex_body: str, alphabet: List[str]) -> bool:
    s = regex_body.replace("?", "").replace("*", "").replace("+", "").replace("|", "")
    s = s.replace("(", "").replace(")", "").replace(":", "").replace("^","").replace("$","\"")
    return set(ch for ch in s if ch.isalpha()).issubset(set("".join(alphabet)))

def ngrams_from_good(good_path: Optional[str], max_n: int, alphabet: List[str]) -> List[str]:
    grams: Set[str] = set()
    if not good_path or not os.path.exists(good_path):
        return []
    with open(good_path, "r") as f:
        for line in f:
            s = line.strip()
            if any(ch not in alphabet for ch in s):
                continue
            for n in range(2, max_n+1):
                for i in range(0, max(0, len(s)-n+1)):
                    grams.add(s[i:i+n])
    grams = {g for g in grams if all(ch in alphabet for ch in g)}
    return sorted(list(grams), key=lambda x: (-len(x), x))

def load_example_lines(path: Optional[str]) -> List[str]:
    if not path or not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [ln.strip() for ln in f if ln.strip()]


def make_wildcard(alphabet: List[str]) -> Expr:
    if len(alphabet) == 1:
        return Unary("*", Atom(alphabet[0]))
    return Unary("*", Union([Atom(ch) for ch in alphabet]))


def derive_templates_from_examples(good: List[str], bad: List[str], alphabet: List[str], max_templates: int = 50, ngram_max: int = 3) -> List[Expr]:
    """Derive candidate Exprs from positive examples (prefix/suffix/contains/repeat/position unions).
    These are biased to be 'close' to the observed positives and contrasted by negatives.
    """
    out: List[Expr] = []
    seen = set()
    wildcard = make_wildcard(alphabet)

    def add_expr(e: Expr):
        k = e.to_key()
        if k in seen: return
        seen.add(k); out.append(e)

    if not good:
        return []

    def longest_common_suffix(strings: List[str]) -> str:
        if not strings: return ""
        s_min = min(strings, key=len)
        L = len(s_min)
        for i in range(L):
            suf = s_min[i:]
            if all(s.endswith(suf) for s in strings):
                return suf
        return ""

    for s in good[: max(200, len(good))]:
        if any(ch not in alphabet for ch in s):
            continue
        add_expr(Atom(s))
        L = len(s)
        # repetition
        for p in range(1, max(1, L//2) + 1):
            if p > 0 and L % p == 0 and s == s[:p] * (L // p):
                add_expr(Unary("+", Atom(s[:p])))
                break
        for k in range(1, min(ngram_max, len(s)) + 1):
            pref = s[:k]
            suff = s[-k:]
            add_expr(Concat([Atom(ch) for ch in pref] + [wildcard]))
            add_expr(Concat([wildcard] + [Atom(ch) for ch in suff]))
            for i in range(0, max(0, len(s) - k + 1)):
                sub = s[i : i + k]
                add_expr(Concat([wildcard] + [Atom(ch) for ch in sub] + [wildcard]))

    lcsuf = longest_common_suffix(good)
    if lcsuf:
        add_expr(Concat([wildcard] + [Atom(ch) for ch in lcsuf]))

    by_len = defaultdict(list)
    for s in good:
        by_len[len(s)].append(s)
    for L, group in list(by_len.items()):
        if L == 0 or len(group) < 2:
            continue
        for a, b in itertools.islice(itertools.permutations(group, 2), 0, 60):
            diffs = [i for i in range(L) if a[i] != b[i]]
            if not diffs or len(diffs) > 3:
                continue
            parts = []
            for i in range(L):
                if i in diffs:
                    choices = sorted({s[i] for s in group if len(s) > i})
                    if len(choices) == 1:
                        parts.append(Atom(choices[0]))
                    else:
                        parts.append(Union([Atom(c) for c in choices]))
                else:
                    parts.append(Atom(a[i]))
            add_expr(Concat(parts))

    return out[:max_templates]


def score_candidate_on_samples(expr: Expr, good: List[str], bad: List[str]) -> Tuple[int, int]:
    """Return (pos_matches, neg_matches) for this expr against sample lists."""
    body = expr.to_regex()
    pat = anchor(body)
    try:
        cre = re.compile(pat)
    except re.error:
        return 0, len(bad)
    pos = sum(1 for s in good if cre.fullmatch(s))
    neg = sum(1 for s in bad if cre.fullmatch(s))
    return pos, neg


def best_suffixes_by_signal(good: List[str], bad: List[str], max_len: int = 5, min_support: int = 3) -> List[Tuple[str,float,int,int]]:
    """Return list of (suffix, score, pos_count, neg_count) sorted by descending score.
    score = pos_frac - neg_frac, filtered by min_support on pos_count.
    """
    if not good:
        return []
    pos_counts = Counter()
    neg_counts = Counter()
    for s in good:
        for k in range(1, min(max_len, len(s)) + 1):
            pos_counts[s[-k:]] += 1
    for s in bad:
        for k in range(1, min(max_len, len(s)) + 1):
            neg_counts[s[-k:]] += 1
    candidates = []
    G = len(good)
    B = len(bad) if bad else 1
    for suf, pcount in pos_counts.items():
        if pcount < min_support:
            continue
        ncount = neg_counts.get(suf, 0)
        pos_frac = pcount / G
        neg_frac = ncount / B
        score = pos_frac - neg_frac
        candidates.append((suf, score, pcount, ncount))
    candidates.sort(key=lambda t: (-t[1], -t[2], len(t[0])))
    return candidates


def generate_candidates(
    alphabet: List[str],
    good_path: Optional[str],
    use_ngrams: bool,
    ngram_max: int,
    max_depth: int,
    beam_size: int,
    max_regex_length: int,
    max_candidates: int,
    disable_qmark: bool = False,
) -> List[Expr]:

    # Atoms
    atoms = [Atom(ch) for ch in alphabet]
    if use_ngrams:
        grams = ngrams_from_good(good_path, ngram_max, alphabet)
        atoms.extend(Atom(g) for g in grams)

    seen_atom_keys = set()
    atom_list = []
    for a in atoms:
        if a.to_key() not in seen_atom_keys:
            seen_atom_keys.add(a.to_key())
            atom_list.append(a)

    by_depth: Dict[int, Set[Expr]] = defaultdict(set)
    by_depth[1] = set(atom_list)

    def beam_score(e: Expr) -> Tuple[int,int]:
        return (expr_length(e), total_ops(e))

    all_exprs: Set[Expr] = set(by_depth[1])

    for depth in range(2, max_depth + 1):
        new_set: Set[Expr] = set()

        for d in range(1, depth):
            for e in by_depth[d]:
                if isinstance(e, Unary):
                    inner = e.inner
                    if e.op in ("*", "+"):
                        pass
                ops_list = ("*", "+") if disable_qmark else ("*", "+", "?")
                for op in ops_list:
                    ue = Unary(op, e)
                    if expr_length(ue) <= max_regex_length:
                        new_set.add(ue)

        for i in range(1, depth):
            j = depth - i
            for x in by_depth[i]:
                for y in by_depth[j]:
                    # Concat
                    ce = Concat([x, y])
                    if expr_length(ce) <= max_regex_length:
                        new_set.add(ce)
                    ue = Union([x, y])
                    if expr_length(ue) <= max_regex_length:
                        new_set.add(ue)

        level_list = sorted(list(new_set), key=beam_score)
        if beam_size > 0 and len(level_list) > beam_size:
            level_list = level_list[:beam_size]

        by_depth[depth] = set(level_list)
        all_exprs.update(by_depth[depth])

        if len(all_exprs) >= max_candidates:
            break

    final = []
    for e in all_exprs:
        body = e.to_regex()
        if expr_length(e) <= max_regex_length and valid_literals_only(body, alphabet):
            final.append(e)

    final_sorted = sorted(final, key=lambda e: (len(e.to_regex()), total_ops(e), e.to_regex()))
    if max_candidates > 0 and len(final_sorted) > max_candidates:
        final_sorted = final_sorted[:max_candidates]
    return final_sorted

def main():
    ap = argparse.ArgumentParser(description="Generate candidate regexes over {a,b} using a bounded grammar.")
    ap.add_argument("--alphabet", default="ab", help="Alphabet letters, default 'ab'. Must be exactly two symbols.")
    ap.add_argument("--good", default="good.txt", help="Path to positives for optional n-gram seeding.")
    ap.add_argument("--use_ngrams", action="store_true", help="Seed atoms with observed n-grams from --good.")
    ap.add_argument("--ngram_max", type=int, default=3, help="Max n-gram length to mine when --use_ngrams is set.")
    ap.add_argument("--bad", default="bad.txt", help="Path to negatives for example-based filtering.")
    ap.add_argument("--use_examples", action="store_true", help="Derive example-based templates from --good and include top matches.")
    ap.add_argument("--example_max", type=int, default=20, help="Max number of example-derived templates to include.")
    ap.add_argument("--max_depth", type=int, default=3, help="Max construction depth (2–4 is typical).")
    ap.add_argument("--beam_size", type=int, default=800, help="Beam size per depth (controls explosion).")
    ap.add_argument("--max_regex_length", type=int, default=32, help="Max textual length of regex body (pruning).")
    ap.add_argument("--max_candidates", type=int, default=5000, help="Hard cap on total candidates.")
    ap.add_argument("--disable_qmark", action="store_true", help="Disable generating '?' (optional) unary operator forms.")
    ap.add_argument("--out_txt", default="candidates.txt", help="Output file with one anchored regex per line.")
    ap.add_argument("--out_jsonl", default="candidates.jsonl", help="Output file with metadata per candidate.")
    args = ap.parse_args()

    alphabet = list(dict.fromkeys(list(args.alphabet)))
    if len(alphabet) != 2:
        raise SystemExit("ERROR: Alphabet must be exactly two distinct symbols (e.g., 'ab').")
    if any(len(ch) != 1 for ch in alphabet):
        raise SystemExit("ERROR: Alphabet symbols must be single characters.")

    exprs = generate_candidates(
        alphabet=alphabet,
        good_path=args.good if os.path.exists(args.good) else None,
        use_ngrams=args.use_ngrams,
        ngram_max=args.ngram_max,
        max_depth=args.max_depth,
        beam_size=args.beam_size,
        max_regex_length=args.max_regex_length,
        max_candidates=args.max_candidates,
        disable_qmark=args.disable_qmark if hasattr(args, 'disable_qmark') else False,
    )

    if args.use_examples:
        good_list = load_example_lines(args.good) if os.path.exists(args.good) else []
        bad_list = load_example_lines(args.bad) if os.path.exists(args.bad) else []
        derived = derive_templates_from_examples(good_list, bad_list, alphabet, max_templates=args.example_max, ngram_max=args.ngram_max)
        scored = []
        for e in derived:
            pos, neg = score_candidate_on_samples(e, good_list, bad_list)
            scored.append((e, pos, neg))
        scored_sorted = sorted(scored, key=lambda t: (-t[1], t[2], len(t[0].to_regex())))
        existing_keys = {x.to_key() for x in exprs}
        added = 0
        new_front = []
        for e, pos, neg in scored_sorted:
            if e.to_key() in existing_keys:
                continue
            new_front.append(e)
            existing_keys.add(e.to_key())
            added += 1
            if added >= args.example_max:
                break
        if new_front:
            exprs = new_front + exprs
            if args.max_candidates > 0 and len(exprs) > args.max_candidates:
                exprs = exprs[: args.max_candidates]
        print(f"Added {len(new_front)} example-derived templates")

        suffix_candidates = best_suffixes_by_signal(good_list, bad_list, max_len=5, min_support=3)
        added_suffix = 0
        for suf, sc, pcount, ncount in suffix_candidates[:3]:
            wildcard = make_wildcard(alphabet)
            suf_expr = Concat([wildcard] + [Atom(ch) for ch in suf])
            if suf_expr.to_key() in {x.to_key() for x in exprs}:
                continue
            exprs = [suf_expr] + exprs
            added_suffix += 1
            if args.max_candidates > 0 and len(exprs) > args.max_candidates:
                exprs = exprs[: args.max_candidates]
        if added_suffix:
            print(f"Added {added_suffix} suffix-derived templates (statistical)")

    with open(args.out_txt, "w") as ftxt, open(args.out_jsonl, "w") as fjs:
        for e in exprs:
            body = e.to_regex()
            anchored = anchor(body)
            ftxt.write(anchored + "\n")
            meta = {
                "regex": anchored,
                "body": body,
                "length": len(body),
                "ops": total_ops(e),
                "kind": e.kind(),
            }
            fjs.write(json.dumps(meta, ensure_ascii=False) + "\n")

    print(f"Generated {len(exprs)} candidates")
    print(f"Wrote: {args.out_txt}")
    print(f"Wrote: {args.out_jsonl}")
    print(f"Settings: depth={args.max_depth}, beam={args.beam_size}, max_len={args.max_regex_length}, ngrams={args.use_ngrams} (max={args.ngram_max})")

if __name__ == "__main__":
    main()
