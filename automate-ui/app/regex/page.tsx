"use client";
import React, { useEffect, useMemo, useState } from 'react';
import RegexVisualizer from '../../components/RegexVisualizer';
import {
    regexToPostfix,
    resetIds,
    postfixToNFA,
    nfaToDot,
    nfaToDfa,
    dfaToDot,
} from '../../lib/automata/regex';

export default function Page() {
    // sample regexes — in practice these come from backend
    const samples = ['a|b', 'ab*', '(a|b)*abb'];

    const [selectedIndex, setSelectedIndex] = useState(0);
    const [activeView, setActiveView] = useState<'nfa' | 'dfa'>('nfa');

    // Recompute artifacts when selection changes
    const artifact = useMemo(() => {
        const re = samples[selectedIndex];
        resetIds();
        const postfix = regexToPostfix(re);
        const nfa = postfixToNFA(postfix);
        const dfa = nfaToDfa(nfa);
        const nfaDot = nfaToDot(nfa);
        const dfaDot = dfaToDot(dfa);
        return { re, postfix, nfaDot, dfaDot };
    }, [selectedIndex]);

    useEffect(() => {
        // keep active view if possible; otherwise default to nfa
        setActiveView((v) => (v === 'nfa' || v === 'dfa' ? v : 'nfa'));
    }, [selectedIndex]);

    return (
        <div style={{ padding: 20 }}>
            <h1>Regex → NFA/DFA Visualizer</h1>

            <div style={{ marginBottom: 12, display: 'flex', gap: 12, alignItems: 'center' }}>
                <label htmlFor="regex-select">Choose regex:</label>
                <select
                    id="regex-select"
                    value={selectedIndex}
                    onChange={(e) => setSelectedIndex(Number(e.target.value))}
                >
                    {samples.map((s, i) => (
                        <option key={i} value={i}>
                            {s}
                        </option>
                    ))}
                </select>

                <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                    {/* Tab-like buttons */}
                    <button
                        onClick={() => setActiveView('nfa')}
                        aria-pressed={activeView === 'nfa'}
                        style={{
                            padding: '6px 12px',
                            background: activeView === 'nfa' ? '#111827' : '#e5e7eb',
                            color: activeView === 'nfa' ? '#fff' : '#111827',
                            border: 'none',
                            borderRadius: 6,
                        }}
                    >
                        NFA
                    </button>
                    <button
                        onClick={() => setActiveView('dfa')}
                        aria-pressed={activeView === 'dfa'}
                        style={{
                            padding: '6px 12px',
                            background: activeView === 'dfa' ? '#111827' : '#e5e7eb',
                            color: activeView === 'dfa' ? '#fff' : '#111827',
                            border: 'none',
                            borderRadius: 6,
                        }}
                    >
                        DFA
                    </button>
                </div>
            </div>

            <div style={{ marginBottom: 12 }}>
                <strong>Selected:</strong> {artifact.re} &nbsp; <em>postfix:</em> {artifact.postfix}
            </div>

            <div style={{ border: '1px solid #e5e7eb', padding: 12, borderRadius: 8 }}>
                {/* Buttons to switch view (duplicate functionality per request) */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                    <button onClick={() => setActiveView('nfa')} style={{ padding: '6px 10px' }}>
                        Show NFA
                    </button>
                    <button onClick={() => setActiveView('dfa')} style={{ padding: '6px 10px' }}>
                        Show DFA
                    </button>
                </div>

                {/* Only one visualization shown at a time */}
                <div style={{ display: 'flex', gap: 20 }}>
                    <div style={{ flex: 1 }}>
                        {activeView === 'nfa' ? (
                            <div>
                                <h3>NFA</h3>
                                <RegexVisualizer dot={artifact.nfaDot} />
                            </div>
                        ) : (
                            <div style={{ color: '#6b7280' }}>NFA hidden</div>
                        )}
                    </div>

                    <div style={{ flex: 1 }}>
                        {activeView === 'dfa' ? (
                            <div>
                                <h3>DFA</h3>
                                <RegexVisualizer dot={artifact.dfaDot} />
                            </div>
                        ) : (
                            <div style={{ color: '#6b7280' }}>DFA hidden</div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
