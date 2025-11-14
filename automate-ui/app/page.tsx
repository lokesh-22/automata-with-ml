import Link from 'next/link';

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-gray-50 py-16 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto">
        <main className="mt-8">
          <div className="bg-white shadow sm:rounded-lg p-8">
            <h1 className="text-3xl font-extrabold text-gray-900">Automata with ML</h1>
            <p className="mt-2 text-sm text-gray-600">Visualize NFAs and DFAs generated from candidate regexes and score them using the backend.</p>

            <div className="mt-8 grid gap-8 grid-cols-1 md:grid-cols-2">
              <Link href="/scorer" className="block p-6 bg-white rounded-lg shadow hover:shadow-md border">
                <h2 className="text-lg font-semibold text-gray-900">Score Examples</h2>
                <p className="mt-2 text-sm text-gray-600">Provide positive and negative examples to generate and score regex candidates. Submit and view the top results.</p>
                <div className="mt-4 text-sm font-medium text-indigo-600">Go to Scorer →</div>
              </Link>

              <Link href="/regex" className="block p-6 bg-white rounded-lg shadow hover:shadow-md border">
                <h2 className="text-lg font-semibold text-gray-900">Inspect Automata</h2>
                <p className="mt-2 text-sm text-gray-600">View NFAs and DFAs for scored candidates. Toggle between NFA and DFA and examine metrics.</p>
                <div className="mt-4 text-sm font-medium text-indigo-600">Open Visualizer →</div>
              </Link>
            </div>

            <section className="mt-8 bg-gray-50 rounded-lg p-6 border">
              <h3 className="text-lg font-semibold text-gray-900">How it works</h3>
              <ol className="mt-3 space-y-2 text-sm text-gray-600 list-decimal list-inside">
                <li>Enter positive (good) and negative (bad) examples on the <strong>Scorer</strong> page and submit.</li>
                <li>The backend generates candidate regexes, scores them, and returns the top candidates.</li>
                <li>Open the <strong>Visualizer</strong> to inspect the top candidates, view metrics, and visualize NFAs/DFAs.</li>
              </ol>
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}
