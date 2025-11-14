#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate a DFA:
1) Structure: determinism, totality, reachability.
2) Data fit: accuracy/F1 vs good.txt & bad.txt.
3) Equivalence: against a regex or another DFA (symmetric difference emptiness).
4) Minimality hint: compare against minimized DFA state count (optional).

Input CSV must match 'dfa_from_regex.py' format:
  state,a,b,accepting
"""

import argparse
import csv
import sys
from collections import deque, defaultdict
from typing import Dict, Set, List, Tuple, Optional
import re

ALPHABET_DEFAULT = ["a","b"]

# ---------------------------
# CSV I/O
# ---------------------------
def load_dfa_csv(path: str, alphabet: List[str]) -> Tuple[int, Set[int], Dict[int, Dict[str,int]]]:
    trans: Dict[int, Dict[str,int]] = {}
    accepts: Set[int] = set()
    start = None
    with open(path, "r") as f:
        r = csv.reader(f)
        header = next(r)
        # Expect: ["state"] + alphabet + ["accepting"]
        if header[0] != "state" or header[-1] != "accepting":
            raise SystemExit("❌ Bad header. Expected: state,<alphabet...>,accepting")
        cols = header[1:-1]
        if cols != alphabet:
            raise SystemExit(f"❌ Alphabet mismatch. CSV has {cols}, expected {alphabet}")
        for i, row in enumerate(r):
            if not row: continue
            s = int(row[0])
            if start is None:
                start = s
            trans[s] = {}
            for j, a in enumerate(alphabet, start=1):
                nxt = row[j]
                if nxt == "":
                    continue
                trans[s][a] = int(nxt)
            acc = int(row[-1])
            if acc == 1:
                accepts.add(s)
    if start is None:
        raise SystemExit("❌ Empty DFA CSV.")
    return start, accepts, trans

def load_lines(path: str) -> List[str]:
    with open(path, "r") as f:
        return [ln.rstrip("\n") for ln in f if ln.strip() != ""]

# ---------------------------
# Structural checks
# ---------------------------
def check_deterministic_total(start: int, trans: Dict[int,Dict[str,int]], alphabet: List[str]) -> Tuple[bool, List[str]]:
    ok = True
    issues = []
    states = set(trans.keys())
    for s, m in trans.items():
        for a in alphabet:
            if a not in m:
                ok = False
                issues.append(f"Missing transition: δ({s},{a})")
    targets = {t for m in trans.values() for t in m.values()}
    unknown_targets = [t for t in targets if t not in states]
    if unknown_targets:
        ok = False
        issues.append(f"Transitions to unknown states: {sorted(set(unknown_targets))}")
    reachable = set()
    q = deque([start])
    while q:
        u = q.popleft()
        if u in reachable: continue
        reachable.add(u)
        for a in alphabet:
            v = trans.get(u,{}).get(a)
            if v is not None:
                q.append(v)
    unreachable = [s for s in states if s not in reachable]
    if unreachable:
        issues.append(f"Unreachable states: {sorted(unreachable)}")
    return ok, issues

# ---------------------------
# Simulation
# ---------------------------
def dfa_accepts(start:int, accepts:Set[int], trans:Dict[int,Dict[str,int]], alphabet:List[str], s:str) -> bool:
    q = start
    for ch in s:
        if ch not in alphabet:
            return False
        if ch not in trans.get(q, {}):
            return False
        q = trans[q][ch]
    return q in accepts

def evaluate_on_data(start, accepts, trans, alphabet, pos: List[str], neg: List[str]) -> Dict[str,float]:
    y_true = []
    y_pred = []
    for s in pos:
        y_true.append(1)
        y_pred.append(1 if dfa_accepts(start, accepts, trans, alphabet, s) else 0)
    for s in neg:
        y_true.append(0)
        y_pred.append(1 if dfa_accepts(start, accepts, trans, alphabet, s) else 0)
    TP = sum(1 for t,p in zip(y_true,y_pred) if t==1 and p==1)
    FP = sum(1 for t,p in zip(y_true,y_pred) if t==0 and p==1)
    FN = sum(1 for t,p in zip(y_true,y_pred) if t==1 and p==0)
    TN = sum(1 for t,p in zip(y_true,y_pred) if t==0 and p==0)
    prec = TP/(TP+FP) if (TP+FP)>0 else 0.0
    rec  = TP/(TP+FN) if (TP+FN)>0 else 0.0
    f1   = 2*prec*rec/(prec+rec) if (prec+rec)>0 else 0.0
    acc  = (TP+TN)/max(1,(TP+FP+FN+TN))
    return {"TP":TP,"FP":FP,"FN":FN,"TN":TN,"precision":prec,"recall":rec,"f1":f1,"accuracy":acc}

# ---------------------------
# Regex → DFA (minimal subset of your previous code)
# ---------------------------
PREC = {"|":1,"·":2,"*":3,"+":3,"?":3}
UNARY = set(["*","+","?"])
ALLOWED = set(["a","b"])

def sanitize_regex(rx: str, alphabet: List[str]) -> str:
    if rx.startswith("^"): rx = rx[1:]
    if rx.endswith("$"): rx = rx[:-1]
    rx = re.sub(r"\(\?:", "(", rx)  # treat non-capturing as capturing
    rx = "".join(ch for ch in rx if not ch.isspace())
    lits = set(ch for ch in rx if ch.isalpha())
    if not lits.issubset(set(alphabet)):
        raise ValueError(f"Regex contains literals outside alphabet {alphabet}: {sorted(list(lits - set(alphabet)))}")
    return rx

def needs_concat(prev_tok: str, curr_tok: str) -> bool:
    if prev_tok in ("(", "|"): return False
    if curr_tok in (")","|","*","+","?"): return False
    return True

def tokenize(rx:str) -> List[str]:
    toks = []
    i = 0
    while i < len(rx):
        c = rx[i]
        if c in ("(",")","|","*","+","?"):
            toks.append(c); i+=1
        elif c in ALLOWED:
            toks.append(c); i+=1
        else:
            raise ValueError(f"Unsupported char: {c!r}")
    out=[]
    for j,t in enumerate(toks):
        if j>0 and needs_concat(toks[j-1], t):
            out.append("·")
        out.append(t)
    return out

def to_postfix(tokens: List[str]) -> List[str]:
    out, stack = [], []
    for tok in tokens:
        if tok in ALLOWED:
            out.append(tok)
        elif tok in UNARY:
            while stack and stack[-1] in UNARY and PREC[stack[-1]]>=PREC[tok]:
                out.append(stack.pop())
            stack.append(tok)
        elif tok in ("|","·"):
            while stack and stack[-1]!="(" and PREC.get(stack[-1],0)>=PREC[tok]:
                out.append(stack.pop())
            stack.append(tok)
        elif tok=="(":
            stack.append(tok)
        elif tok==")":
            while stack and stack[-1]!="(":
                out.append(stack.pop())
            if not stack: raise ValueError("Mismatched )")
            stack.pop()
    while stack:
        t=stack.pop()
        if t in ("(",")"): raise ValueError("Mismatched (")
        out.append(t)
    return out

class NFAState:
    __slots__=("eid","eps","outs")
    def __init__(self,eid:int):
        self.eid=eid; self.eps=set(); self.outs=defaultdict(set)
class Fragment:
    __slots__=("start","accepts")
    def __init__(self,start,accepts): self.start=start; self.accepts=accepts
class NFA:
    def __init__(self): self.states=[]; self._id=0; self.start=None; self.accepts=set()
    def ns(self): s=NFAState(self._id); self._id+=1; self.states.append(s); return s
    @staticmethod
    def from_postfix(post: List[str]) -> "NFA":
        n=NFA(); st=[]
        def lit(ch): s=n.ns(); t=n.ns(); s.outs[ch].add(t); return Fragment(s,{t})
        for tok in post:
            if tok in ALLOWED: st.append(lit(tok))
            elif tok=="·":
                b=st.pop(); a=st.pop()
                for q in a.accepts: q.eps.add(b.start)
                st.append(Fragment(a.start,b.accepts))
            elif tok=="|":
                b=st.pop(); a=st.pop(); s=n.ns(); t=n.ns()
                s.eps.update([a.start,b.start])
                for q in a.accepts: q.eps.add(t)
                for q in b.accepts: q.eps.add(t)
                st.append(Fragment(s,{t}))
            elif tok in ("*","+","?"):
                a=st.pop(); s=n.ns(); t=n.ns()
                if tok=="*":
                    s.eps.update([a.start,t])
                    for q in a.accepts: q.eps.update([a.start,t])
                elif tok=="+":
                    s.eps.add(a.start)
                    for q in a.accepts: q.eps.update([a.start,t])
                else: # ?
                    s.eps.update([a.start,t])
                    for q in a.accepts: q.eps.add(t)
                st.append(Fragment(s,{t}))
        if len(st)!=1: raise ValueError("Invalid postfix")
        f=st.pop(); n.start=f.start; n.accepts=f.accepts; return n

def eps_closure(states:Set[NFAState])->Set[NFAState]:
    cl=set(states); dq=list(states)
    while dq:
        s=dq.pop()
        for t in s.eps:
            if t not in cl: cl.add(t); dq.append(t)
    return cl

def nfa_to_dfa(nfa:NFA, alphabet:List[str]):
    idmap={s:s.eid for s in nfa.states}
    start_set=frozenset(q.eid for q in eps_closure({nfa.start}))
    idx_of={start_set:0}; sets=[start_set]; start=0
    accepts=set()
    if any(a.eid in start_set for a in nfa.accepts): accepts.add(0)
    trans=defaultdict(dict)
    q=deque([start_set])
    while q:
        S=q.popleft(); i=idx_of[S]
        for a in alphabet:
            move=set()
            for sid in S:
                st = next(x for x in nfa.states if x.eid==sid)
                for nxt in st.outs.get(a, []):
                    move.add(nxt)
            U=frozenset(x.eid for x in eps_closure(move))
            if not U: continue
            if U not in idx_of:
                idx_of[U]=len(sets); sets.append(U); q.append(U)
                if any(acc.eid in U for acc in nfa.accepts): accepts.add(idx_of[U])
            trans[i][a]=idx_of[U]
    return start, accepts, trans

def complete_with_sink(start:int, accepts:Set[int], trans:Dict[int,Dict[str,int]], alphabet:List[str]):
    states=set(trans.keys()) | {t for m in trans.values() for t in m.values()}
    sink = max(states) + 1 if states else 1
    for s in list(states)+[sink]:
        trans.setdefault(s, {})
        for a in alphabet:
            trans[s].setdefault(a, sink)
    for a in alphabet:
        trans[sink][a]=sink
    return start, accepts, trans, sink

def equivalent(dfa1, dfa2, alphabet: List[str]) -> bool:
    s1,a1,t1 = dfa1
    s2,a2,t2 = dfa2
    s1,a1,t1,_ = complete_with_sink(s1,set(a1),{k:dict(v) for k,v in t1.items()},alphabet)
    s2,a2,t2,_ = complete_with_sink(s2,set(a2),{k:dict(v) for k,v in t2.items()},alphabet)
    seen=set()
    dq=deque([(s1,s2)])
    while dq:
        p=dq.popleft()
        if p in seen: continue
        seen.add(p)
        u,v=p
        in1 = 1 if u in a1 else 0
        in2 = 1 if v in a2 else 0
        if in1 ^ in2:
            return False
        for a in alphabet:
            dq.append((t1[u][a], t2[v][a]))
    return True

def main():
    ap = argparse.ArgumentParser(description="Validate a DFA: structure, data fit, and equivalence checks.")
    ap.add_argument("--dfa_csv", default="min_dfa_transition_table.csv", help="DFA to validate (use minimized CSV by default).")
    ap.add_argument("--alphabet", default="ab", help="Exactly two symbols, default 'ab'.")
    ap.add_argument("--good", default="good.txt", help="Positives file.")
    ap.add_argument("--bad", default="bad.txt", help="Negatives file.")
    ap.add_argument("--regex", help="Optional regex to check equivalence against.")
    ap.add_argument("--other_dfa_csv", help="Optional second DFA CSV to check equivalence against.")
    args = ap.parse_args()

    alphabet=list(args.alphabet)
    if len(alphabet)!=2: raise SystemExit("❌ Alphabet must be exactly two symbols.")

    start, accepts, trans = load_dfa_csv(args.dfa_csv, alphabet)

    ok, issues = check_deterministic_total(start, trans, alphabet)
    print("== Structural checks ==")
    print(f"Deterministic & total transitions: {'OK' if ok else 'PROBLEMS'}")
    for msg in issues:
        print(" -", msg)

    pos = load_lines(args.good) if args.good else []
    neg = load_lines(args.bad) if args.bad else []
    if pos or neg:
        m = evaluate_on_data(start, accepts, trans, alphabet, pos, neg)
        print("\n== Data fit ==")
        print(f"TP={m['TP']} FP={m['FP']} FN={m['FN']} TN={m['TN']}")
        print(f"Precision={m['precision']:.4f} Recall={m['recall']:.4f} F1={m['f1']:.4f} Acc={m['accuracy']:.4f}")
    else:
        print("\n== Data fit ==\n(no data provided)")

    if args.regex:
        rx_body = sanitize_regex(args.regex, alphabet)
        tokens = tokenize(rx_body)
        postfix = to_postfix(tokens)
        nfa = NFA.from_postfix(postfix)
        s2,a2,t2 = nfa_to_dfa(nfa, alphabet)
        eq = equivalent((start, accepts, trans), (s2,a2,t2), alphabet)
        print("\n== Equivalence to regex ==")
        print(f"Equivalent to '{args.regex}'? {'YES' if eq else 'NO'}")

    if args.other_dfa_csv:
        s2,a2,t2 = load_dfa_csv(args.other_dfa_csv, alphabet)
        eq = equivalent((start, accepts, trans), (s2,a2,t2), alphabet)
        print("\n== Equivalence to other DFA ==")
        print(f"Equivalent to {args.other_dfa_csv}? {'YES' if eq else 'NO'}")

if __name__ == "__main__":
    main()
