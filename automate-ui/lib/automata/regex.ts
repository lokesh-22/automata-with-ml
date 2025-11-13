// Minimal regex → NFA (Thompson), NFA → DFA (subset construction), and DOT exporters
// Supports symbols (single chars except metachars), concatenation, union '|' and Kleene '*', and parentheses.

export type Transition = { from: number; to: number; symbol: string | null };
export type NFA = { start: number; accept: number; states: number[]; transitions: Transition[] };

let nextStateId = 0;
function newState(): number {
    return nextStateId++;
}

export function resetIds() {
    nextStateId = 0;
}

function isOperator(c: string) {
    return c === '|' || c === '*' || c === '.';
}

function precedence(op: string) {
    if (op === '*') return 3;
    if (op === '.') return 2;
    if (op === '|') return 1;
    return 0;
}

// Insert explicit concatenation operator '.'
function insertConcats(re: string): string {
    let out = '';
    const len = re.length;
    for (let i = 0; i < len; i++) {
        const c = re[i];
        out += c;
        if (c === '(' || c === '|') continue;
        if (i + 1 < len) {
            const d = re[i + 1];
            if (d === '*' || d === '|' || d === ')') continue;
            out += '.';
        }
    }
    return out;
}

export function regexToPostfix(re: string): string {
    const withConcats = insertConcats(re);
    const out: string[] = [];
    const ops: string[] = [];
    for (const c of withConcats) {
        if (c === '(') {
            ops.push(c);
        } else if (c === ')') {
            while (ops.length && ops[ops.length - 1] !== '(') out.push(ops.pop()!);
            ops.pop();
        } else if (isOperator(c)) {
            while (ops.length && isOperator(ops[ops.length - 1]) && precedence(ops[ops.length - 1]) >= precedence(c)) {
                out.push(ops.pop()!);
            }
            ops.push(c);
        } else {
            out.push(c);
        }
    }
    while (ops.length) out.push(ops.pop()!);
    return out.join('');
}

// Thompson construction using postfix regex
export function postfixToNFA(postfix: string): NFA {
    const stack: NFA[] = [];
    for (const c of postfix) {
        if (c === '*') {
            const n = stack.pop()!;
            const s = newState();
            const f = newState();
            const transitions: Transition[] = [
                { from: s, to: n.start, symbol: null },
                { from: s, to: f, symbol: null },
                { from: n.accept, to: n.start, symbol: null },
                { from: n.accept, to: f, symbol: null },
                ...n.transitions,
            ];
            stack.push({ start: s, accept: f, states: [s, f, ...n.states], transitions });
        } else if (c === '.') {
            const n2 = stack.pop()!;
            const n1 = stack.pop()!;
            // connect n1.accept -> n2.start with epsilon
            const transitions = [...n1.transitions, ...n2.transitions, { from: n1.accept, to: n2.start, symbol: null }];
            const states = [...n1.states, ...n2.states];
            stack.push({ start: n1.start, accept: n2.accept, states, transitions });
        } else if (c === '|') {
            const n2 = stack.pop()!;
            const n1 = stack.pop()!;
            const s = newState();
            const f = newState();
            const transitions: Transition[] = [
                { from: s, to: n1.start, symbol: null },
                { from: s, to: n2.start, symbol: null },
                { from: n1.accept, to: f, symbol: null },
                { from: n2.accept, to: f, symbol: null },
                ...n1.transitions,
                ...n2.transitions,
            ];
            const states = [s, f, ...n1.states, ...n2.states];
            stack.push({ start: s, accept: f, states, transitions });
        } else {
            // symbol
            const s = newState();
            const f = newState();
            const transitions: Transition[] = [{ from: s, to: f, symbol: c }];
            stack.push({ start: s, accept: f, states: [s, f], transitions });
        }
    }
    if (stack.length !== 1) throw new Error('Invalid regex/postfix; stack length != 1');
    const nfa = stack[0];
    // normalize states unique
    nfa.states = Array.from(new Set(nfa.states));
    return nfa;
}

// NFA -> DFA subset construction
export type DFA = {
    start: number;
    acceptStates: number[];
    states: number[]; // ids
    transitions: { from: number; to: number; symbol: string }[];
};

function epsilonClosure(nfa: NFA, stateSet: Set<number>): Set<number> {
    const stack = Array.from(stateSet);
    const res = new Set<number>(stateSet);
    while (stack.length) {
        const s = stack.pop()!;
        for (const t of nfa.transitions) {
            if (t.from === s && t.symbol === null && !res.has(t.to)) {
                res.add(t.to);
                stack.push(t.to);
            }
        }
    }
    return res;
}

function move(nfa: NFA, stateSet: Set<number>, symbol: string): Set<number> {
    const res = new Set<number>();
    for (const s of stateSet) {
        for (const t of nfa.transitions) {
            if (t.from === s && t.symbol === symbol) res.add(t.to);
        }
    }
    return res;
}

export function nfaToDfa(nfa: NFA): DFA {
    // collect alphabet
    const alphabet = new Set<string>();
    for (const t of nfa.transitions) if (t.symbol !== null) alphabet.add(t.symbol);

    const startClosure = epsilonClosure(nfa, new Set([nfa.start]));
    const dfaStatesMap = new Map<string, number>();
    const dfaStatesList: Set<number>[] = [];
    function keyOf(set: Set<number>) {
        return Array.from(set).sort((a, b) => a - b).join(',');
    }
    const q0key = keyOf(startClosure);
    dfaStatesMap.set(q0key, 0);
    dfaStatesList.push(startClosure);
    const transitions: { from: number; to: number; symbol: string }[] = [];
    let idx = 0;
    while (idx < dfaStatesList.length) {
        const currentSet = dfaStatesList[idx];
        const currentKey = keyOf(currentSet);
        const fromId = dfaStatesMap.get(currentKey)!;
        for (const sym of alphabet) {
            const moved = move(nfa, currentSet, sym);
            if (moved.size === 0) continue;
            const closure = epsilonClosure(nfa, moved);
            const k = keyOf(closure);
            if (!dfaStatesMap.has(k)) {
                dfaStatesMap.set(k, dfaStatesList.length);
                dfaStatesList.push(closure);
            }
            const toId = dfaStatesMap.get(k)!;
            transitions.push({ from: fromId, to: toId, symbol: sym });
        }
        idx++;
    }

    const acceptStates: number[] = [];
    for (const [k, id] of dfaStatesMap.entries()) {
        const parts = k === '' ? [] : k.split(',').map((x) => Number(x));
        if (parts.includes(nfa.accept)) acceptStates.push(id);
    }

    return {
        start: 0,
        acceptStates,
        states: Array.from({ length: dfaStatesList.length }, (_, i) => i),
        transitions,
    };
}

export function nfaToDot(nfa: NFA): string {
    const lines: string[] = [];
    lines.push('digraph NFA {');
    lines.push('  rankdir=LR;');
    lines.push('  node [shape = circle];');
    lines.push(`  start [shape=point];`);
    lines.push(`  start -> ${nfa.start};`);
    for (const s of nfa.states) {
        if (s === nfa.accept) lines.push(`  ${s} [shape=doublecircle];`);
    }
    for (const t of nfa.transitions) {
        const label = t.symbol === null ? 'ε' : t.symbol;
        lines.push(`  ${t.from} -> ${t.to} [label="${label}"];`);
    }
    lines.push('}');
    return lines.join('\n');
}

export function dfaToDot(dfa: DFA): string {
    const lines: string[] = [];
    lines.push('digraph DFA {');
    lines.push('  rankdir=LR;');
    lines.push('  node [shape = circle];');
    lines.push('  start [shape=point];');
    lines.push(`  start -> ${dfa.start};`);
    for (const s of dfa.states) {
        if (dfa.acceptStates.includes(s)) lines.push(`  ${s} [shape=doublecircle];`);
    }
    for (const t of dfa.transitions) {
        const label = t.symbol;
        lines.push(`  ${t.from} -> ${t.to} [label="${label}"];`);
    }
    lines.push('}');
    return lines.join('\n');
}
