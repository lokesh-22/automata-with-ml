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
    sanitizeRegex,
} from '../../lib/automata/regex';

export default function Page() {
    // sample regexes — replaced by backend results when available
    const defaultSamples = ['a|b', 'ab*', '(a|b)*abb'];
    const [samples, setSamples] = useState<string[]>(defaultSamples);
    const [topCandidates, setTopCandidates] = useState<any[] | null>(null);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [activeView, setActiveView] = useState<'nfa' | 'dfa'>('nfa');
    const [testInput, setTestInput] = useState<string>('');
    const [testResults, setTestResults] = useState<Array<{ s: string, ok?: boolean, error?: string }>>([]);

    // Load top candidates from localStorage (written by scorer page) on mount
    useEffect(() => {
        try {
            const raw = localStorage.getItem('top_candidates');
            if (raw) {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed) && parsed.length > 0) {
                    // sanitize regexes from backend before using them in automata
                    const sanitized = parsed.map((p: any) => {
                        const r = p.regex ?? String(p.regex ?? '');
                        return { ...p, _sanitized: sanitizeRegex(String(r)) };
                    });
                    setTopCandidates(sanitized);
                    setSamples(sanitized.map((p: any) => p._sanitized || String(p.regex)));
                    setSelectedIndex(0);
                    return;
                }
            }
        } catch (e) {
            // ignore
        }
        setSamples(defaultSamples);
    }, []);

    // Recompute artifacts when selection changes
    const artifact = useMemo(() => {
        const re = samples[selectedIndex] ?? '';
        resetIds();
        const postfix = regexToPostfix(re);
        const nfa = postfixToNFA(postfix);
        const dfa = nfaToDfa(nfa);
        const nfaDot = nfaToDot(nfa);
        const dfaDot = dfaToDot(dfa);
        return { re, postfix, nfaDot, dfaDot };
    }, [samples, selectedIndex]);

    return (
        <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
            <div className="max-w-5xl mx-auto">
                <div className="bg-white shadow sm:rounded-lg p-6">
                    <div className="flex items-center gap-4">
                        <h1 className="text-2xl font-semibold text-gray-900">Regex → Automata Visualizer</h1>
                        <p className="text-sm text-gray-500">Select a candidate to inspect NFA and DFA</p>
                    </div>

                    <div className="mt-6 flex flex-col md:flex-row md:items-center md:gap-6 gap-4">
                        <div className="flex-1">
                            <label htmlFor="regex-select" className="block text-sm font-medium text-gray-700">Choose regex</label>
                            <select
                                id="regex-select"
                                value={selectedIndex}
                                onChange={(e) => setSelectedIndex(Number(e.target.value))}
                                className="mt-1 block w-full rounded-md border-gray-300 bg-white py-2 pl-3 pr-10 text-base focus:border-indigo-500 focus:outline-none focus:ring-indigo-500 sm:text-sm"
                            >
                                {samples.map((s, i) => (
                                    <option key={i} value={i}>{s}</option>
                                ))}
                            </select>
                        </div>

                        <div className="flex gap-2">
                            <button
                                onClick={() => setActiveView('nfa')}
                                aria-pressed={activeView === 'nfa'}
                                className={`px-3 py-2 rounded-md text-sm font-medium ${activeView === 'nfa' ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-700'}`}
                            >NFA</button>
                            <button
                                onClick={() => setActiveView('dfa')}
                                aria-pressed={activeView === 'dfa'}
                                className={`px-3 py-2 rounded-md text-sm font-medium ${activeView === 'dfa' ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-700'}`}
                            >DFA</button>
                        </div>
                    </div>

                    <div className="mt-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700">Test strings (one per line)</label>
                                <textarea
                                    value={testInput}
                                    onChange={(e) => setTestInput(e.target.value)}
                                    rows={6}
                                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm text-gray-900"
                                    placeholder={"e.g.\nabb\naabb\naba"}
                                />
                                <div className="flex items-center gap-2 mt-2">
                                    <button
                                        onClick={() => {
                                            // run tests against currently selected regex
                                            const reStr = (samples[selectedIndex] || '').toString();
                                            const sanitized = sanitizeRegex(reStr || '');
                                            const lines = testInput.split(/\r?\n/).map(s => s.trim()).filter(s => s.length > 0);
                                            const out: Array<{ s: string, ok?: boolean, error?: string }> = [];
                                            try {
                                                // Create JS RegExp; ensure anchored behavior
                                                const anchored = sanitized.startsWith('^') ? sanitized : '^' + sanitized;
                                                const anchoredFinal = anchored.endsWith('$') ? anchored : anchored + '$';
                                                const rx = new RegExp(anchoredFinal);
                                                for (const s of lines) {
                                                    try {
                                                        const ok = rx.test(s);
                                                        out.push({ s, ok });
                                                    } catch (err: any) {
                                                        out.push({ s, error: String(err) });
                                                    }
                                                }
                                            } catch (err: any) {
                                                // failed to compile regex in JS
                                                for (const s of lines) out.push({ s, error: 'Invalid regex (JS): ' + String(err) });
                                            }
                                            setTestResults(out);
                                        }}
                                        className="inline-flex items-center px-3 py-2 rounded-md bg-indigo-600 text-white text-sm font-medium"
                                    >Run tests</button>
                                    <button
                                        onClick={() => { setTestInput(''); setTestResults([]); }}
                                        className="inline-flex items-center px-3 py-2 rounded-md bg-gray-100 text-gray-700 text-sm font-medium"
                                    >Clear</button>
                                </div>
                                <p className="mt-2 text-xs text-gray-500">Note: client-side JS RegExp is used for testing; syntax differences with Python are possible.</p>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700">Results</label>
                                <div className="mt-1 bg-white rounded border p-2 max-h-56 overflow-auto">
                                    {testResults.length === 0 ? (
                                        <div className="text-sm text-gray-400 p-4">No test runs yet.</div>
                                    ) : (
                                        <ul className="divide-y">
                                            {testResults.map((r, i) => (
                                                <li key={i} className="flex items-center justify-between py-2">
                                                    <div className="text-sm font-mono text-gray-800">{r.s}</div>
                                                    <div>
                                                        {r.error ? (
                                                            <span className="text-xs text-red-600">{r.error}</span>
                                                        ) : r.ok ? (
                                                            <span className="text-xs font-semibold text-green-700">MATCH</span>
                                                        ) : (
                                                            <span className="text-xs text-gray-500">no match</span>
                                                        )}
                                                    </div>
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                    <div className="text-sm text-gray-600">Selected: <span className="font-medium">{artifact.re}</span> &nbsp; <span className="text-xs italic text-gray-400">postfix: {artifact.postfix}</span></div>
                </div>

                {topCandidates && topCandidates[selectedIndex] && (
                    <div className="mt-4 p-4 bg-gray-50 rounded-md border">
                        <h3 className="text-sm font-semibold text-gray-700">Metrics</h3>
                        <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                            {Object.entries(topCandidates[selectedIndex]).map(([k, v]) => (
                                <div key={k} className="p-2 bg-white rounded border">
                                    <div className="text-xs text-gray-500">{k}</div>
                                    <div className="text-sm font-medium">{String(v)}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                <div className="mt-6">
                    <div className="bg-white rounded-md border p-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-lg font-medium text-gray-800">{activeView === 'nfa' ? 'NFA' : 'DFA'}</h3>
                            <div className="text-sm text-gray-500">Showing: <span className="font-mono">{activeView.toUpperCase()}</span></div>
                        </div>
                        <div className="mt-4 overflow-auto border rounded p-4 bg-gray-50" style={{ minHeight: 420 }}>
                            {activeView === 'nfa' ? (
                                <RegexVisualizer dot={artifact.nfaDot} />
                            ) : (
                                <RegexVisualizer dot={artifact.dfaDot} />
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
