API: scorer wrapper
====================

This document describes the minimal HTTP API provided by `backend/api/server.js`. The Node server runs the existing Python scorer (`backend/score_candidates.py`) and returns the top candidates as JSON.

Prerequisites
-------------
- Node.js (to run the server)
- Python available on PATH as `python` (the server invokes `python score_candidates.py` in the `backend/` folder)
- The repository backend files present: `backend/score_candidates.py`, `backend/candidates.txt`, `backend/good.txt`, `backend/bad.txt`.

Start the server
----------------
From the repo root:

```bash
cd backend/api
node server.js
# or: npm start
```

The server listens on port 5000 by default (override with PORT environment variable).

Endpoints
---------

GET /
~~~~~
Health endpoint. Returns a small JSON object listing available endpoints.

Request
- Method: GET
- Path: /
- Body: none

Response
- 200 OK
- Content-Type: application/json
- Body example:

  {
    "ok": true,
    "endpoints": ["/top"]
  }

GET /top
~~~~~~~~
Run the Python scorer and return the top candidates (top-3). The server executes the scorer synchronously and then reads `backend/top_candidates.csv` produced by the scorer and returns the rows as JSON.

Request
- Method: GET
- Path: /top
- Query: none (server is currently hard-coded to request top_k=3)
- Body: none

Behavior
- The server runs (synchronously) the command:

  python score_candidates.py --good good.txt --bad bad.txt --candidates candidates.txt --top_k 3 --out_jsonl scored_candidates.jsonl --out_csv top_candidates.csv --out_best best_regex.txt

- When the scorer finishes, the server reads `top_candidates.csv` and returns the first three rows parsed into JSON objects.

Response
- 200 OK
- Content-Type: application/json
- Body schema:

  {
    "top": [
      { "rank": "1", "regex": "^(?:a|b)*abb$", "f1_val": "1.0000", "acc_val": "1.0000", "f1_tr": "1.0000", "acc_tr": "1.0000", "score": "0.778000", "len": "11", "ops": "5", "star": "1", "plus": "0", "qmark": "0", "union": "2", "groups": "2", "tp_val": "100", "fp_val": "0", "fn_val": "0", "tn_val": "100" },
      { /* second row */ },
      { /* third row */ }
    ]
  }

Notes on returned values
- The CSV header is produced by `score_candidates.py` and contains these columns (the server maps the CSV columns directly to string values):
  - rank, regex, f1_val, acc_val, f1_tr, acc_tr, score, len, ops, star, plus, qmark, union, groups, tp_val, fp_val, fn_val, tn_val
- All values are returned as strings exactly as found in the CSV. If you prefer typed numeric values, the server can be updated to coerce numeric columns to numbers before returning JSON.

Error responses
---------------
- 500 Internal Server Error — returned when the scorer process fails to run or returns a non-zero exit status. The response body contains `stdout` and `stderr` returned by the Python process to aid debugging.
- 404 Not Found — for unknown paths.

CORS
----
The server sets Access-Control-Allow-Origin: * so the frontend can call it from a different origin during development.

Security and performance notes
------------------------------
- The server runs the full scorer synchronously on each `/top` request. For interactive or production use you should:
  - Run scoring asynchronously and cache results (so /top returns quickly and scoring runs in the background), or
  - Expose a persistent Python service (FastAPI) and call it from Node, or
  - Limit calls to /top and protect the endpoint behind an authentication layer.
- The server assumes `python` on PATH. If your system uses `python3`, either ensure `python` is available or edit `server.js` to call `python3` (or make the executable configurable via an env var).

Possible improvements (next steps)
---------------------------------
- Add a POST /score endpoint that accepts custom `good`, `bad`, and `candidates` payloads (careful: this requires input validation and sandboxing).
- Return typed numeric fields in JSON (coerce floats/ints).
- Add caching or async job queue to avoid running the scorer repeatedly.
- Replace the Node wrapper with a small FastAPI service for better performance and easier Python integration.

New: POST /score
-----------------
The server now exposes a POST `/score` endpoint that accepts a JSON body with `good` and `bad` arrays and optional generation/scoring options. The endpoint will:

- Write `good.txt` and `bad.txt` into the `backend/` folder from the provided arrays.
- Run `generate_candidates.py` (in `backend/`) to produce `candidates.txt` / `candidates.jsonl`.
- Run `score_candidates.py` to score those candidates and produce `top_candidates.csv`.
- Return the top-k rows (default k=3) as JSON with numeric coercion for common metric fields.

Request
- Method: POST
- Path: /score
- Content-Type: application/json
- Body schema (JSON):

  {
    "good": ["pos1", "pos2"],
    "bad": ["neg1", "neg2"],
    // optional generator/scorer options
    "max_depth": 3,
    "beam_size": 800,
    "max_regex_length": 32,
    "max_candidates": 5000,
    "use_examples": true,           // default true
    "example_max": 20,
    "use_ngrams": false,
    "ngram_max": 4,
    "disable_qmark": false,
    "top_k": 3
  }

Response
- 200 OK
- Content-Type: application/json
- Body:

  {
    "top": [ { /* typed candidate object (numbers for numeric fields) */ }, ... ]
  }

Error responses are similar to GET /top (non-zero python exits will return 500 with stdout/stderr for debugging).

Contact
-------
If you want me to wire this endpoint into the Next.js frontend, add typed responses, or convert to an async/cached flow, tell me which option and I'll implement it next.
