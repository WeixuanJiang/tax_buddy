# Tax-return assistant — Web UI

React (Vite) chat interface for the ATO Tax-Return Knowledge Engine. Asks the
FastAPI service and renders grounded answers: markdown (incl. ATO rate tables),
inline `[n]` citations tied to a numbered source ledger, related ATO links, an
income-year tag, and the general-info disclaimer.

## Design

"Civic instrument, not chatbot." Pure-white surfaces, eucalypt-teal identity
(OKLCH), one brass accent. Type: **Public Sans** (UI/body) · **Spectral** serif
(wordmark, hero, answer headings) · **IBM Plex Mono** (income-year tag, citation
numerals). No chat bubbles — each exchange is a "You asked" line plus a document
-style answer notice. States covered: empty (teaches via example questions),
loading (skeleton), answer, clarify, out-of-scope, and error. Responsive to
mobile; respects `prefers-reduced-motion`.

## Run

```bash
# 1. Start the API first (from the ato_data dir):
#    uvicorn knowledge_engine.api.main:app --reload      # http://localhost:8000

# 2. Then the web app:
cd knowledge_engine/web
npm install
npm run dev          # http://localhost:5173
```

The dev server proxies `/api/*` to `http://localhost:8000` (see `vite.config.js`),
so no CORS setup is needed locally. For another backend origin, set
`VITE_API_BASE` (e.g. `VITE_API_BASE=https://api.example.com`).

`npm run build` produces a static bundle in `dist/`.

## Layout

```
web/
  index.html                 fonts + root
  vite.config.js             dev proxy to the API
  src/
    main.jsx  App.jsx        shell + conversation state (uses /chat, multi-turn)
    api.js                   fetch client
    styles.css               OKLCH tokens + full visual system
    lib/citations.jsx        rewrites [n] into clickable source references
    components/
      Masthead · EmptyState · Composer · Exchange
      AnswerNotice · Sources · Thinking
```
