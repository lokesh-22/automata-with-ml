#!/usr/bin/env python3
import argparse
import itertools
import json
import math
import os
import re
from collections import defaultdict
from typing import List, Tuple, Set, Dict, Optional

# -----------------------------
# Config defaults
# -----------------------------
DEFAULT_ALPHABET = ["a", "b"]  # strict two-symbol rule

# -----------------------------
# Small AST with canonicalization
# -----------------------------
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
        # Flatten nested concats and remove empty epsilon parts if we ever add epsilon
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
        # Flatten unions and sort alternatives canonically to avoid duplicates
        flat = []
        for a in alts:
            if isinstance(a, Union):
                flat.extend(a.alts)
            else:
                flat.append(a)
        # Deduplicate by key
        uniq = {a.to_key(): a for a in flat}
        # Sort by key for canonical order
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
        # Parenthesize inner if it’s not a single atom or already grouped
        if isinstance(self.inner, Atom):
            base = self.inner.to_regex()
        else:
            base = f"(?:{self.inner.to_regex()})"
        return f"{base}{self.op}"
    def to_key(self): return ("unary", self.op, self.inner.to_key())

# -----------------------------
# Helpers
# -----------------------------
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
    return f"^(?:{regex_body})$"

def valid_literals_only(regex_body: str, alphabet: List[str]) -> bool:
    # Quick heuristic: ensure we only used a/b literals; our generator ensures it anyway.
    s = regex_body.replace("?", "").replace("*", "").replace("+", "").replace("|", "")
    s = s.replace("(", "").replace(")", "").replace(":", "").replace("^","").replace("$","").replace("\\","")
    return set(ch for ch in s if ch.isalpha()).issubset(set("".join(alphabet)))

def ngrams_from_good(good_path: Optional[str], max_n: int, alphabet: List[str]) -> List[str]:
    grams: Set[str] = set()
    if not good_path or not os.path.exists(good_path):
        return []
    with open(good_path, "r") as f:
        for line in f:
            s = line.strip()
            if any(ch not in alphabet for ch in s):  # enforce alphabet
                continue
            for n in range(2, max_n+1):
                for i in range(0, max(0, len(s)-n+1)):
                    grams.add(s[i:i+n])
    # Keep only n-grams truly in alphabet
    grams = {g for g in grams if all(ch in alphabet for ch in g)}
    # Sort by length desc then lex asc so longer helpful chunks come first
    return sorted(list(grams), key=lambda x: (-len(x), x))

# -----------------------------
# Generation core
# -----------------------------
def generate_candidates(
    alphabet: List[str],
    good_path: Optional[str],
    use_ngrams: bool,
    ngram_max: int,
    max_depth: int,
    beam_size: int,
    max_regex_length: int,
    max_candidates: int,
) -> List[Expr]:

    # Atoms
    atoms = [Atom(ch) for ch in alphabet]
    if use_ngrams:
        grams = ngrams_from_good(good_path, ngram_max, alphabet)
        atoms.extend(Atom(g) for g in grams)

    # Dedup atoms
    seen_atom_keys = set()
    atom_list = []
    for a in atoms:
        if a.to_key() not in seen_atom_keys:
            seen_atom_keys.add(a.to_key())
            atom_list.append(a)

    # Beam per depth
    by_depth: Dict[int, Set[Expr]] = defaultdict(set)
    by_depth[1] = set(atom_list)

    # Score for beam: smaller textual length + fewer ops
    def beam_score(e: Expr) -> Tuple[int,int]:
        return (expr_length(e), total_ops(e))

    all_exprs: Set[Expr] = set(by_depth[1])

    for depth in range(2, max_depth + 1):
        new_set: Set[Expr] = set()

        # Unary expansions from earlier levels (up to depth-1)
        for d in range(1, depth):
            for e in by_depth[d]:
                # Skip redundant stacked unaries like (X*)* or (X+)+ etc.
                if isinstance(e, Unary):
                    inner = e.inner
                    # Avoid doubling the same op and star/plus on '?'-ed content can be allowed but grows search; keep simple
                    if e.op in ("*", "+"):
                        # do not apply same op again
                        pass
                for op in ("*", "+", "?"):
                    ue = Unary(op, e)
                    if expr_length(ue) <= max_regex_length:
                        new_set.add(ue)

        # Binary concat/union: combine splits of depth (i, j) with i+j=depth
        for i in range(1, depth):
            j = depth - i
            for x in by_depth[i]:
                for y in by_depth[j]:
                    # Concat
                    ce = Concat([x, y])
                    if expr_length(ce) <= max_regex_length:
                        new_set.add(ce)
                    # Union (canonicalizes order)
                    ue = Union([x, y])
                    if expr_length(ue) <= max_regex_length:
                        new_set.add(ue)

        # Apply beam
        level_list = sorted(list(new_set), key=beam_score)
        if beam_size > 0 and len(level_list) > beam_size:
            level_list = level_list[:beam_size]

        by_depth[depth] = set(level_list)
        all_exprs.update(by_depth[depth])

        if len(all_exprs) >= max_candidates:
            break

    # Final prune by max length again and alphabet check (paranoid)
    final = []
    for e in all_exprs:
        body = e.to_regex()
        if expr_length(e) <= max_regex_length and valid_literals_only(body, alphabet):
            final.append(e)

    # Sort final by (length, ops, text)
    final_sorted = sorted(final, key=lambda e: (len(e.to_regex()), total_ops(e), e.to_regex()))
    if max_candidates > 0 and len(final_sorted) > max_candidates:
        final_sorted = final_sorted[:max_candidates]
    return final_sorted

# -----------------------------
# CLI
# -----------------------------
def main():
    ap = argparse.ArgumentParser(description="Generate candidate regexes over {a,b} using a bounded grammar.")
    ap.add_argument("--alphabet", default="ab", help="Alphabet letters, default 'ab'. Must be exactly two symbols.")
    ap.add_argument("--good", default="good.txt", help="Path to positives for optional n-gram seeding.")
    ap.add_argument("--use_ngrams", action="store_true", help="Seed atoms with observed n-grams from --good.")
    ap.add_argument("--ngram_max", type=int, default=3, help="Max n-gram length to mine when --use_ngrams is set.")
    ap.add_argument("--max_depth", type=int, default=3, help="Max construction depth (2–4 is typical).")
    ap.add_argument("--beam_size", type=int, default=800, help="Beam size per depth (controls explosion).")
    ap.add_argument("--max_regex_length", type=int, default=32, help="Max textual length of regex body (pruning).")
    ap.add_argument("--max_candidates", type=int, default=5000, help="Hard cap on total candidates.")
    ap.add_argument("--out_txt", default="candidates.txt", help="Output file with one anchored regex per line.")
    ap.add_argument("--out_jsonl", default="candidates.jsonl", help="Output file with metadata per candidate.")
    args = ap.parse_args()

    # Enforce exactly two-symbol alphabet
    alphabet = list(dict.fromkeys(list(args.alphabet)))
    if len(alphabet) != 2:
        raise SystemExit("❌ Alphabet must be exactly two distinct symbols (e.g., 'ab').")
    if any(len(ch) != 1 for ch in alphabet):
        raise SystemExit("❌ Alphabet symbols must be single characters.")

    exprs = generate_candidates(
        alphabet=alphabet,
        good_path=args.good if os.path.exists(args.good) else None,
        use_ngrams=args.use_ngrams,
        ngram_max=args.ngram_max,
        max_depth=args.max_depth,
        beam_size=args.beam_size,
        max_regex_length=args.max_regex_length,
        max_candidates=args.max_candidates,
    )

    # Write outputs
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

    print(f"✅ Generated {len(exprs)} candidates")
    print(f"📄 {args.out_txt}")
    print(f"📄 {args.out_jsonl}")
    print(f"Settings: depth={args.max_depth}, beam={args.beam_size}, max_len={args.max_regex_length}, ngrams={args.use_ngrams} (max={args.ngram_max})")

if __name__ == "__main__":
    main()

