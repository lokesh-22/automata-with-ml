"use client";
import React, { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function ScorerPage() {
    const router = useRouter();
    const [goodText, setGoodText] = useState('');
    const [badText, setBadText] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setLoading(true);
        try {
            const good = goodText
                .split('\n')
                .map((s) => s.trim())
                .filter(Boolean);
            const bad = badText
                .split('\n')
                .map((s) => s.trim())
                .filter(Boolean);

            const resp = await fetch('http://localhost:5000/score', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ good, bad, top_k: 5 }),
            });
            if (!resp.ok) {
                const txt = await resp.text();
                throw new Error(`Server error: ${resp.status} ${txt}`);
            }
            const data = await resp.json();
            console.log('Scorer response', data);
            // store top candidates in localStorage for /regex page to pick up
            localStorage.setItem('top_candidates', JSON.stringify(data.top || []));
            // navigate to /regex
            router.push('/regex');
        } catch (err: any) {
            setError(String(err.message || err));
        } finally {
            setLoading(false);
        }
    }

        return (
            <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
                <div className="max-w-3xl mx-auto">
                    <div className="bg-white shadow sm:rounded-lg p-6">
                        <h1 className="text-2xl font-semibold text-gray-900">Score candidates</h1>
                        <p className="mt-1 text-sm text-black">Enter positive (good) and negative (bad) examples, one per line. The backend scorer will return the top candidates.</p>

                        <form onSubmit={onSubmit} className="mt-6 grid gap-6">
                            <div>
                                <label htmlFor="good" className="block text-sm font-medium text-gray-900">Good examples</label>
                                <p className="text-xs text-gray-900">One positive example per line</p>
                                <textarea
                                    id="good"
                                    rows={6}
                                    value={goodText}
                                    onChange={(e) => setGoodText(e.target.value)}
                                    className="mt-2 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                                    placeholder="e.g. aab\nababb"
                                />
                            </div>

                            <div>
                                <label htmlFor="bad" className="block text-sm font-medium text-gray-900">Bad examples</label>
                                <p className="text-xs text-gray-900">One negative example per line</p>
                                <textarea
                                    id="bad"
                                    rows={6}
                                    value={badText}
                                    onChange={(e) => setBadText(e.target.value)}
                                    className="mt-2 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                                    placeholder="e.g. bb\naba"
                                />
                            </div>

                            <div className="flex items-center gap-3">
                                <button
                                    type="submit"
                                    disabled={loading}
                                    className="inline-flex items-center rounded-md bg-indigo-600 px-4 py-2 text-white text-sm font-medium hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                                >
                                    {loading ? 'Scoring...' : 'Submit & View'}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => { setGoodText(''); setBadText(''); }}
                                    className="inline-flex items-center rounded-md bg-white border px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-50"
                                >
                                    Clear
                                </button>

                                <div className="ml-auto text-sm text-gray-900">Server: <span className="font-mono">http://localhost:5000/score</span></div>
                            </div>

                            {error && <div className="text-sm text-red-600">{error}</div>}
                        </form>
                    </div>
                </div>
            </div>
        );
}
