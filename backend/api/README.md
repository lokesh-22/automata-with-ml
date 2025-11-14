Backend API
=================

This is a minimal Node.js API that wraps the Python scorer and returns the top candidates.

Endpoints
- GET / -> health and endpoints
- GET /top -> runs the scorer and returns top candidates from `top_candidates.csv`

Run
----
- From repository root, start the server:

```bash
cd backend/api
node server.js
# or: npm start
```

It will run Python's `score_candidates.py` in the backend folder and return JSON for the top-k candidates.
