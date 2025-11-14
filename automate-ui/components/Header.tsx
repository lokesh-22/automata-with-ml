import Link from 'next/link';

export default function Header() {
  return (
    <header className="bg-white border-b">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <div>
            <Link href="/" className="text-lg font-bold text-gray-900">Automata with ML</Link>
          </div>
          <nav className="flex items-center space-x-4">
            <Link href="/scorer" className="text-sm font-medium text-gray-700 hover:text-indigo-600">Scorer</Link>
            <Link href="/regex" className="text-sm font-medium text-gray-700 hover:text-indigo-600">Visualizer</Link>
          </nav>
        </div>
      </div>
    </header>
  );
}
