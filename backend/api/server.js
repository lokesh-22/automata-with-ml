const http = require('http');
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 5000;
const BACKEND_DIR = path.resolve(__dirname, '..'); // backend/

function runScorer() {
    // Run the Python scorer in the backend directory and ask for top_k=3
    const args = [
        'score_candidates.py',
        '--good', 'good.txt',
        '--bad', 'bad.txt',
        '--candidates', 'candidates.txt',
        '--top_k', '3',
        '--out_jsonl', 'scored_candidates.jsonl',
        '--out_csv', 'top_candidates.csv',
        '--out_best', 'best_regex.txt'
    ];
    const res = spawnSync('python', args, { cwd: BACKEND_DIR, encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 });
    return res;
}

function parseTopCsv(csvPath) {
    if (!fs.existsSync(csvPath)) return [];
    const txt = fs.readFileSync(csvPath, 'utf8').trim();
    if (!txt) return [];
    const lines = txt.split(/\r?\n/);
    const header = lines[0].split(',').map(h => h.replace(/^\uFEFF/, '').trim());
    const rows = [];
    for (let i = 1; i < Math.min(lines.length, 1 + 3); i++) {
        const cols = lines[i].split(',');
        const obj = {};
        for (let j = 0; j < Math.min(header.length, cols.length); j++) {
            obj[header[j]] = cols[j];
        }
        rows.push(obj);
    }
    return rows;
}

const server = http.createServer((req, res) => {
    // Basic CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

    if (req.method === 'GET' && req.url.startsWith('/top')) {
        // Run scorer synchronously (short-lived) and return parsed top CSV
        const child = runScorer();
        if (child.error) {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: String(child.error) }));
            return;
        }
        if (child.status !== 0) {
            // include stdout/stderr for debugging
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'scorer failed', stdout: child.stdout, stderr: child.stderr }));
            return;
        }

        const csvPath = path.join(BACKEND_DIR, 'top_candidates.csv');
        const rows = parseTopCsv(csvPath);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ top: rows }));
        return;
    }

    if (req.method === 'GET' && req.url === '/') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true, endpoints: ['/top'] }));
        return;
    }

        // POST /score
        if (req.method === 'POST' && req.url === '/score') {
            // collect body
            let body = '';
            req.on('data', chunk => {
                body += chunk;
                // limit body size to ~1MB
                if (body.length > 1e6) {
                    res.writeHead(413, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Request entity too large' }));
                    req.connection.destroy();
                }
            });
            req.on('end', () => {
                let payload;
                try {
                    payload = JSON.parse(body || '{}');
                } catch (err) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Invalid JSON body' }));
                    return;
                }

                const good = Array.isArray(payload.good) ? payload.good : [];
                const bad = Array.isArray(payload.bad) ? payload.bad : [];
                if (good.length === 0 || bad.length === 0) {
                    res.writeHead(400, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Provide non-empty arrays `good` and `bad` in the request body' }));
                    return;
                }

                // write files to backend dir
                try {
                    fs.writeFileSync(path.join(BACKEND_DIR, 'good.txt'), good.join('\n') + '\n', 'utf8');
                    fs.writeFileSync(path.join(BACKEND_DIR, 'bad.txt'), bad.join('\n') + '\n', 'utf8');
                } catch (err) {
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'Failed to write input files', detail: String(err) }));
                    return;
                }

                // prepare generator args
                const genArgs = [
                    'generate_candidates.py',
                    '--good', 'good.txt',
                    '--out_txt', 'candidates.txt',
                    '--out_jsonl', 'candidates.jsonl',
                    '--max_depth', String(payload.max_depth || 3),
                    '--beam_size', String(payload.beam_size || 800),
                    '--max_regex_length', String(payload.max_regex_length || 32),
                    '--max_candidates', String(payload.max_candidates || 5000),
                    // Always run with these options
                    '--use_examples',
                    '--example_max', '10',
                    '--disable_qmark'
                ];

                // run generator
                const gen = spawnSync('python', genArgs, { cwd: BACKEND_DIR, encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 });
                if (gen.error) {
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: String(gen.error) }));
                    return;
                }
                if (gen.status !== 0) {
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'generator failed', stdout: gen.stdout, stderr: gen.stderr }));
                    return;
                }

                // run scorer
                const scoreArgs = [
                    'score_candidates.py',
                    '--good', 'good.txt',
                    '--bad', 'bad.txt',
                    '--candidates', 'candidates.txt',
                    '--top_k', String(payload.top_k || 3),
                    '--out_jsonl', 'scored_candidates.jsonl',
                    '--out_csv', 'top_candidates.csv',
                    '--out_best', 'best_regex.txt'
                ];
                const sc = spawnSync('python', scoreArgs, { cwd: BACKEND_DIR, encoding: 'utf8', maxBuffer: 50 * 1024 * 1024 });
                if (sc.error) {
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: String(sc.error) }));
                    return;
                }
                if (sc.status !== 0) {
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'scorer failed', stdout: sc.stdout, stderr: sc.stderr }));
                    return;
                }

                // parse CSV into typed JSON
                const csvPath = path.join(BACKEND_DIR, 'top_candidates.csv');
                if (!fs.existsSync(csvPath)) {
                    res.writeHead(500, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({ error: 'top_candidates.csv not found after scoring' }));
                    return;
                }
                const csvText = fs.readFileSync(csvPath, 'utf8').trim();
                const lines = csvText.split(/\r?\n/);
                const header = lines[0].split(',').map(h => h.replace(/^\uFEFF/, '').trim());
                const rows = [];
                for (let i = 1; i < Math.min(lines.length, 1 + (payload.top_k || 3)); i++) {
                    const cols = lines[i].split(',');
                    const obj = {};
                    for (let j = 0; j < Math.min(header.length, cols.length); j++) {
                        const key = header[j];
                        let val = cols[j];
                        // coerce some numeric fields
                        if (['rank','len','ops','star','plus','qmark','union','groups','tp_val','fp_val','fn_val','tn_val'].includes(key)) {
                            val = parseInt(val, 10);
                        } else if (['f1_val','acc_val','f1_tr','acc_tr','score'].includes(key)) {
                            val = parseFloat(val);
                        }
                        obj[key] = val;
                    }
                    rows.push(obj);
                }

                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ top: rows }));
            });
            return;
        }

    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'not found' }));
});

server.listen(PORT, () => {
    console.log(`API server listening on http://localhost:${PORT}`);
});
