#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regex -> NFA (Thompson) -> DFA (subset construction) -> Minimized DFA (Hopcroft)
Outputs CSV transition tables and Graphviz DOT diagrams.

Alphabet is strictly two symbols; default 'ab'.
"""

import argparse
import csv
import re
from collections import defaultdict, deque
from typing import List, Tuple, Dict, Set, Optional, FrozenSet

# -----------------------------
# Tokenization & Shunting-yard
# -----------------------------

ALLOWED_LITS = set(["a", "b"])  # strict two-symbol alphabet

# Operator precedences (higher => binds tighter)
PREC = {
    "|": 1,      # union
    "·": 2,      # explicit concat
    "*": 3,      # unary
    "+": 3,
    "?": 3,
}

UNARY = set(["*", "+", "?"])
BINARY = set(["|", "·"])

def sanitize_regex(user_rx: str, alphabet: str) -> str:
    # Strip anchors ^$
    if user_rx.startswith("^"): user_rx = user_rx[1:]
    if user_rx.endswith("$"): user_rx = user_rx[:-1]

    # Allow non-capturing groups (?:...) by removing "?:"
    user_rx = re.sub(r"\(\?:", "(", user_rx)

    # Remove whitespace (treat as literal-free formatting)
    user_rx = "".join(ch for ch in user_rx if not ch.isspace())

    # Validate literals are only from alphabet
    lits = set(ch for ch in user_rx if ch.isalpha())
    if not lits.issubset(set(alphabet)):
        raise ValueError(f"Regex contains literals outside alphabet {{{','.join(alphabet)}}}: {sorted(list(lits - set(alphabet)))}")

    # Basic validation
    return user_rx

def needs_concat(prev_tok: str, curr_tok: str) -> bool:
    # Insert explicit concat between:
    # literal/group/quantifier  followed by  literal/'('
    if prev_tok == "(" or prev_tok == "|":
        return False
    if curr_tok in [")", "|", "*", "+", "?"]:
        return False
    # prev literal or ') or unary' followed by literal or '('
    return True

def tokenize(rx: str) -> List[str]:
    tokens: List[str] = []
    i = 0
    while i < len(rx):
        c = rx[i]
        if c in ("(", ")", "|", "*", "+", "?"):
            tokens.append(c)
            i += 1
        elif c in ALLOWED_LITS:
            tokens.append(c)
            i += 1
        else:
            raise ValueError(f"Unsupported char in regex: {c!r}. Only 'a','b','|','*','+','?','(',')' supported (and '(?:' already sanitized).")
    # Insert explicit concat '·'
    output: List[str] = []
    for j, tok in enumerate(tokens):
        if j > 0 and needs_concat(tokens[j-1], tok):
            output.append("·")
        output.append(tok)
    return output

def to_postfix(tokens: List[str]) -> List[str]:
    out: List[str] = []
    stack: List[str] = []
    for tok in tokens:
        if tok in ALLOWED_LITS:
            out.append(tok)
        elif tok in UNARY:
            # Unary is postfix; apply immediately based on precedence
            while stack and stack[-1] in UNARY and PREC[stack[-1]] >= PREC[tok]:
                out.append(stack.pop())
            stack.append(tok)
        elif tok in BINARY:
            while stack and stack[-1] != "(" and PREC.get(stack[-1],0) >= PREC[tok]:
                out.append(stack.pop())
            stack.append(tok)
        elif tok == "(":
            stack.append(tok)
        elif tok == ")":
            while stack and stack[-1] != "(":
                out.append(stack.pop())
            if not stack:
                raise ValueError("Mismatched parentheses.")
            stack.pop()
        else:
            raise ValueError(f"Unknown token: {tok}")
    while stack:
        t = stack.pop()
        if t in ("(", ")"):
            raise ValueError("Mismatched parentheses.")
        out.append(t)
    return out

# -----------------------------
# Thompson NFA
# -----------------------------

class NFAState:
    __slots__ = ("eid", "eps", "outs")
    def __init__(self, eid: int):
        self.eid = eid
        self.eps: Set["NFAState"] = set()         # epsilon transitions
        self.outs: Dict[str, Set["NFAState"]] = defaultdict(set)  # symbol -> set(states)

class Fragment:
    __slots__ = ("start", "accepts")
    def __init__(self, start: NFAState, accepts: Set[NFAState]):
        self.start = start
        self.accepts = accepts

class NFA:
    def __init__(self):
        self.states: List[NFAState] = []
        self._next_id = 0
        self.start: Optional[NFAState] = None
        self.accepts: Set[NFAState] = set()

    def new_state(self) -> NFAState:
        s = NFAState(self._next_id)
        self._next_id += 1
        self.states.append(s)
        return s

    @staticmethod
    def from_postfix(post: List[str]) -> "NFA":
        nfa = NFA()
        stack: List[Fragment] = []

        def literal(ch: str) -> Fragment:
            s = nfa.new_state()
            t = nfa.new_state()
            s.outs[ch].add(t)
            return Fragment(s, {t})

        for tok in post:
            if tok in ALLOWED_LITS:
                stack.append(literal(tok))
            elif tok == "·":
                # concat: frag2 after frag1 (note: stack order)
                b = stack.pop()
                a = stack.pop()
                # connect all accepts of a to start of b via epsilon
                for acc in a.accepts:
                    acc.eps.add(b.start)
                stack.append(Fragment(a.start, b.accepts))
            elif tok == "|":
                b = stack.pop()
                a = stack.pop()
                s = nfa.new_state()
                t = nfa.new_state()
                s.eps.update([a.start, b.start])
                for acc in a.accepts: acc.eps.add(t)
                for acc in b.accepts: acc.eps.add(t)
                stack.append(Fragment(s, {t}))
            elif tok in ("*", "+", "?"):
                a = stack.pop()
                if tok == "*":
                    s = nfa.new_state()
                    t = nfa.new_state()
                    s.eps.update([a.start, t])
                    for acc in a.accepts:
                        acc.eps.update([a.start, t])
                    stack.append(Fragment(s, {t}))
                elif tok == "+":
                    s = nfa.new_state()
                    t = nfa.new_state()
                    s.eps.add(a.start)
                    for acc in a.accepts:
                        acc.eps.update([a.start, t])
                    stack.append(Fragment(s, {t}))
                elif tok == "?":
                    s = nfa.new_state()
                    t = nfa.new_state()
                    s.eps.update([a.start, t])
                    for acc in a.accepts:
                        acc.eps.add(t)
                    stack.append(Fragment(s, {t}))
            else:
                raise ValueError(f"Unsupported postfix token: {tok}")

        if len(stack) != 1:
            raise ValueError("Invalid postfix; stack not singleton at end.")
        frag = stack.pop()
        nfa.start = frag.start
        nfa.accepts = frag.accepts
        return nfa

# -----------------------------
# NFA -> DFA (subset construction)
# -----------------------------

def eps_closure(states: Set[NFAState]) -> Set[NFAState]:
    stack = list(states)
    closure = set(states)
    while stack:
        s = stack.pop()
        for t in s.eps:
            if t not in closure:
                closure.add(t)
                stack.append(t)
    return closure

def move(states: Set[NFAState], sym: str) -> Set[NFAState]:
    out: Set[NFAState] = set()
    for s in states:
        out.update(s.outs.get(sym, []))
    return out

class DFA:
    def __init__(self, alphabet: List[str]):
        self.alphabet = alphabet
        self.start: int = 0
        self.accepts: Set[int] = set()
        self.trans: Dict[int, Dict[str, int]] = defaultdict(dict)  # state -> sym -> next
        self.state_sets: List[FrozenSet[int]] = []  # mapping to NFA state IDs (for reference)

def nfa_to_dfa(nfa: NFA, alphabet: List[str]) -> DFA:
    # Map NFA states to IDs for hashing
    idmap = {s: s.eid for s in nfa.states}
    start_set = frozenset(idmap[s] for s in eps_closure({nfa.start}))
    dfa = DFA(alphabet=alphabet)
    idx_of: Dict[FrozenSet[int], int] = {start_set: 0}
    dfa.state_sets.append(start_set)
    dfa.start = 0
    if any(s.eid in start_set for s in nfa.accepts):
        dfa.accepts.add(0)

    queue = deque([start_set])
    while queue:
        S = queue.popleft()
        s_idx = idx_of[S]
        for sym in alphabet:
            # Build set of reachable NFA states via sym then epsilon-closure
            nfa_states = {next for sid in S for next in nfa.states if next.eid in []}
            move_set = set()
            for sid in S:
                # find the NFA state object by id
                nstate = next(st for st in nfa.states if st.eid == sid)
                for nxt in nstate.outs.get(sym, []):
                    move_set.add(nxt)
            U = frozenset(st.eid for st in eps_closure(move_set))
            if not U:
                continue
            if U not in idx_of:
                idx = len(dfa.state_sets)
                idx_of[U] = idx
                dfa.state_sets.append(U)
                if any(acc.eid in U for acc in nfa.accepts):
                    dfa.accepts.add(idx)
                queue.append(U)
            dfa.trans[s_idx][sym] = idx_of[U]
    return dfa

# -----------------------------
# Hopcroft Minimization
# -----------------------------

def minimize_dfa(dfa: DFA) -> DFA:
    # Ensure total (optional). We’ll treat missing transitions as dead to a sink.
    alphabet = dfa.alphabet
    # Build full transition function with sink
    sink = None
    full_trans: Dict[int, Dict[str, int]] = defaultdict(dict)
    states = set(dfa.trans.keys()) | {s for m in dfa.trans.values() for s in m.values()}
    states |= set(range(len(dfa.state_sets)))
    max_state = (max(states) if states else -1)

    # Create sink
    sink = max_state + 1
    for s in list(states) + [sink]:
        full_trans[s] = {}
        for a in alphabet:
            nxt = dfa.trans.get(s, {}).get(a, sink)
            full_trans[s][a] = nxt
    # Sink self-loops
    for a in alphabet:
        full_trans[sink][a] = sink
    states.add(sink)

    A = set(dfa.accepts)
    NA = states - A

    # Initial partition
    P: List[Set[int]] = []
    if A: P.append(set(A))
    if NA: P.append(set(NA))
    W: List[Set[int]] = [set(A), set(NA)]

    while W:
        Aset = W.pop()
        for a in alphabet:
            # X = states that go to Aset on 'a'
            X = set(s for s in states if full_trans[s][a] in Aset)
            newP: List[Set[int]] = []
            for Y in P:
                inter = Y & X
                diff = Y - X
                if inter and diff:
                    newP.extend([inter, diff])
                    if Y in W:
                        W.remove(Y)
                        W.extend([inter, diff])
                    else:
                        # add the smaller to W
                        W.append(inter if len(inter) <= len(diff) else diff)
                else:
                    newP.append(Y)
            P = newP

    # Map blocks to new states
    rep_to_new: Dict[int, int] = {}
    for i, block in enumerate(P):
        for s in block:
            rep_to_new[s] = i

    min_dfa = DFA(alphabet=alphabet)
    min_dfa.start = rep_to_new[dfa.start]
    # Build transitions (skip sink state if unreachable from start)
    # But we’ll include all reachable from start in minimized machine
    # First build provisional transitions
    for i, block in enumerate(P):
        min_dfa.trans[i] = {}
    for s in states:
        ns = rep_to_new[s]
        for a in alphabet:
            ns_to = rep_to_new[full_trans[s][a]]
            min_dfa.trans[ns][a] = ns_to
    # Accepting states
    for acc in dfa.accepts:
        min_dfa.accepts.add(rep_to_new[acc])

    # Remove unreachable
    reachable = set()
    q = deque([min_dfa.start])
    while q:
        u = q.popleft()
        if u in reachable: continue
        reachable.add(u)
        for a in alphabet:
            v = min_dfa.trans.get(u, {}).get(a)
            if v is not None:
                q.append(v)

    # Filter
    min_dfa.trans = {s: trans for s, trans in min_dfa.trans.items() if s in reachable}
    min_dfa.accepts = {s for s in min_dfa.accepts if s in reachable}
    # It's helpful (optional) to rebuild state_sets for traceability
    min_dfa.state_sets = [frozenset() for _ in range(len(min_dfa.trans))]
    return min_dfa

# -----------------------------
# Output helpers
# -----------------------------

def write_csv(table_path: str, dfa: DFA):
    states = sorted(dfa.trans.keys())
    with open(table_path, "w", newline="") as f:
        w = csv.writer(f)
        header = ["state"] + dfa.alphabet + ["accepting"]
        w.writerow(header)
        for s in states:
            row = [s] + [dfa.trans[s].get(a, "") for a in dfa.alphabet] + [1 if s in dfa.accepts else 0]
            w.writerow(row)

def to_dot(dot_path: str, dfa: DFA, title: str):
    with open(dot_path, "w") as f:
        f.write("digraph DFA {\n")
        f.write('  rankdir=LR;\n')
        f.write('  node [shape=circle];\n')
        # invisible start arrow
        f.write('  __start [shape=point];\n')
        f.write(f'  __start -> {dfa.start};\n')
        # accepting nodes
        for s in dfa.trans.keys():
            if s in dfa.accepts:
                f.write(f'  {s} [shape=doublecircle];\n')
        # transitions
        for s, trans in dfa.trans.items():
            for a, t in trans.items():
                f.write(f'  {s} -> {t} [label="{a}"];\n')
        f.write(f'  label="{title}"; labelloc="t";\n')
        f.write("}\n")

def summarize(path: str, rx_body: str, dfa: DFA, min_dfa: DFA):
    with open(path, "w") as f:
        f.write("Regex to DFA Report\n")
        f.write("===================\n\n")
        f.write(f"Regex (body): {rx_body}\n")
        f.write(f"Alphabet    : {''.join(sorted(ALLOWED_LITS))}\n\n")
        f.write(f"DFA states         : {len(dfa.trans)}\n")
        f.write(f"DFA accepting      : {len(dfa.accepts)}\n")
        f.write(f"Min DFA states     : {len(min_dfa.trans)}\n")
        f.write(f"Min DFA accepting  : {len(min_dfa.accepts)}\n")
        f.write("\nNotes:\n- DOT files written (dfa.dot, min_dfa.dot). Render with:\n")
        f.write("  dot -Tpng dfa.dot -o dfa.png\n")
        f.write("  dot -Tpng min_dfa.dot -o min_dfa.png\n")

# -----------------------------
# Main
# -----------------------------

def main():
    ap = argparse.ArgumentParser(description="Build DFA & minimized DFA from a regex and export tables and diagrams.")
    ap.add_argument("--regex", help="Regex body or anchored regex. If omitted, reads best_regex.txt.")
    ap.add_argument("--alphabet", default="ab", help="Must be exactly two symbols (default 'ab').")
    ap.add_argument("--best_file", default="best_regex.txt", help="File containing the top regex from scoring.")
    ap.add_argument("--dfa_csv", default="dfa_transition_table.csv")
    ap.add_argument("--min_dfa_csv", default="min_dfa_transition_table.csv")
    ap.add_argument("--dfa_dot", default="dfa.dot")
    ap.add_argument("--min_dfa_dot", default="min_dfa.dot")
    ap.add_argument("--summary", default="dfa_summary.txt")
    args = ap.parse_args()

    alph = list(dict.fromkeys(list(args.alphabet)))
    if len(alph) != 2 or any(len(c) != 1 for c in alph):
        raise SystemExit("❌ --alphabet must be exactly two single characters, e.g., 'ab'.")

    # Load regex
    rx_in = args.regex
    if not rx_in:
        with open(args.best_file, "r") as f:
            rx_in = f.readline().strip()
    if not rx_in:
        raise SystemExit("❌ Provide --regex or ensure best_regex.txt has a regex.")

    # If anchored, keep but sanitize later
    try:
        rx_body = sanitize_regex(rx_in, "".join(alph))
    except ValueError as e:
        raise SystemExit(f"❌ {e}")

    # Tokenize -> Postfix
    tokens = tokenize(rx_body)
    postfix = to_postfix(tokens)

    # Thompson NFA
    nfa = NFA.from_postfix(postfix)

    # NFA -> DFA
    dfa = nfa_to_dfa(nfa, alph)

    # Minimize
    min_d = minimize_dfa(dfa)

    # Outputs
    write_csv(args.dfa_csv, dfa)
    write_csv(args.min_dfa_csv, min_d)
    to_dot(args.dfa_dot, dfa, title="DFA")
    to_dot(args.min_dfa_dot, min_d, title="Minimized DFA")
    summarize(args.summary, rx_body, dfa, min_d)

    print("✅ Built DFA and minimized DFA.")
    print(f"📄 {args.dfa_csv}")
    print(f"📄 {args.min_dfa_csv}")
    print(f"📄 {args.dfa_dot}")
    print(f"📄 {args.min_dfa_dot}")
    print(f"📄 {args.summary}")

if __name__ == "__main__":
    main()
