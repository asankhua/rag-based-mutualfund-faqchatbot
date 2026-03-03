## RAG-Based Mutual Fund FAQ Chatbot – Architecture

This document describes the phase-wise architecture for a RAG-based FAQ assistant for specific HDFC mutual fund schemes on INDMoney. The assistant is **read-only**, answers only from stored data/embeddings, always cites sources, and never gives advice or handles personal/account information.

---

## Scope & High-Level Requirements

- **Supported funds (Phase 1)** – fixed allowlist of INDMoney scheme pages:
  - `https://www.indmoney.com/mutual-funds/hdfc-flexi-cap-fund-direct-plan-growth-option-3184`
  - `https://www.indmoney.com/mutual-funds/hdfc-small-cap-fund-direct-growth-option-3580`
  - `https://www.indmoney.com/mutual-funds/hdfc-nifty-midcap-150-index-fund-direct-growth-1043788`
  - `https://www.indmoney.com/mutual-funds/hdfc-mid-cap-fund-direct-plan-growth-option-3097`
  - `https://www.indmoney.com/mutual-funds/hdfc-banking-financial-services-fund-direct-growth-1006661`
  - `https://www.indmoney.com/mutual-funds/hdfc-defence-fund-direct-growth-1043873`
  - `https://www.indmoney.com/mutual-funds/hdfc-nifty-private-bank-etf-1042349`
  - `https://www.indmoney.com/mutual-funds/hdfc-focused-fund-direct-plan-growth-option-2795`

- **Data needed (per scheme, primarily from “Overview”)**:
  - NAV
  - % per year / returns since inception (and standard periods like 1Y/3Y/5Y where available)
  - Expense ratio
  - Benchmark
  - AUM
  - Inception date
  - Minimum lumpsum and SIP amounts
  - Exit load
  - Lock-in
  - Turnover
  - Risk (risk category / riskometer)

- **Behavioral constraints**:
  - Answers **must only use information from the stored data/embeddings** (no “LLM world knowledge”).
  - **Every answer must include at least one source link**, usually the specific INDMoney fund URL used.
  - The chatbot **must not provide investment advice or opinions** (no “should I buy/sell/hold?”, “is this good for me?”, “best fund”).
  - Any request for **personal or account-specific information** (portfolio, KYC status, PAN, phone/email, login, tax filing details, etc.) is **out of scope** and must be refused politely.
  - Opinionated/portfolio questions must be refused with a **polite, facts-only message** and a **relevant educational link**.
  - **Public sources only**: use only official, public webpages (e.g., INDMoney scheme pages, AMC/SEBI factsheets). Do **not** use screenshots from internal tools, app back-ends, or third-party blogs as sources.
  - **No PII**: do not accept, store, or log sensitive identifiers (PAN, Aadhaar, account numbers, OTPs, emails, phone numbers) anywhere in the pipeline.
  - **No performance computation/comparison**: do not compute or compare returns yourself; if users ask for performance comparisons, route them to official factsheets or the underlying INDMoney pages as sources instead.
  - In future (Phase 3), **Groq** will be used as the LLM for the RAG answering layer.

---

## Phase 1 – Data Acquisition & Normalization (Scraping Layer)

**Suggested folder layout for implementation**

- `phase1/` – Phase 1 Python code (scrapers, helpers, CLI entrypoints).
  - `phase1/phase1_scraper.py` – main script to scrape all allowlisted URLs.
  - Additional modules as the scraper grows (parsers, validators, etc.).
- `data/phase1/` – JSON output files, one per scheme.

### Goals

- Fetch and normalize structured data for the defined set of HDFC mutual funds from INDMoney.
- Produce a **canonical, machine-readable representation** per fund that downstream phases can rely on.

### Responsibilities

- Crawl/scrape only the **allowlisted URLs**.
- Extract the target fields from the fund **Overview** (and related sections if needed).
- Normalize and validate data.
- Store canonical snapshots in a persistent store.

### Components

1. **Scraper Service**
   - **Input**: List of allowed scheme URLs (configured statically or in DB).
   - **Implementation options**:
     - Python (`requests` + `BeautifulSoup`) if the pages are mostly static.
     - Python + Playwright/Selenium if content is rendered client-side.
   - **Responsibilities**:
     - Fetch each page in the allowlist.
     - Use stable selectors (CSS/XPath) to extract:
       - Scheme name
       - NAV
       - Returns (1Y/3Y/5Y/since inception, as available)
       - Expense ratio
       - Benchmark
       - AUM
       - Inception date
       - Minimum lumpsum
       - Minimum SIP
       - Exit load
       - Lock-in
       - Turnover
       - Risk
     - Normalize numeric fields where possible (e.g., parse NAV and AUM into numeric + currency).
     - Attach metadata:
       - `source_url` (the INDMoney URL)
       - `scraped_at` timestamp

2. **Canonical Data Model**
   - Example JSON document per scheme:

```json
{
  "scheme_id": "hdfc-focused-fund-direct-plan-growth-option-2795",
  "name": "HDFC Focused Fund Direct Plan Growth Option",
  "source_url": "https://www.indmoney.com/mutual-funds/hdfc-focused-fund-direct-plan-growth-option-2795",
  "overview": {
    "nav": "₹XXX (as on DD MMM YYYY)",
    "returns_since_inception": "X% p.a.",
    "returns_1y": "X%",
    "returns_3y": "Y%",
    "returns_5y": "Z%",
    "expense_ratio": "A%",
    "benchmark": "NIFTY XYZ",
    "aum": "₹AAA crore",
    "inception_date": "DD MMM YYYY",
    "min_lumpsum": "₹X",
    "min_sip": "₹Y",
    "exit_load": "Exit load details text",
    "lock_in": "None / 3 years etc",
    "turnover": "Turnover text/value",
    "risk": "Very High"
  },
  "last_scraped_at": "2026-03-02T10:00:00Z"
}
```

3. **Storage**
   - **Option A (recommended)**: PostgreSQL
     - `schemes` table (scheme_id, name, url, inception_date, etc.).
     - `scheme_overview` table (scheme_id FK, nav, returns, aum, expense_ratio, etc.).
   - **Option B**: Document store (MongoDB / Firestore) with one document per scheme.

### Validation & Governance

- Enforce **URL allowlist** – scraper refuses to fetch any non-listed URL.
- Run sanity checks:
  - Non-empty NAV, AUM, basic metrics.
  - Date formats parseable.
  - Log and alert on missing or malformed key fields.
- Persist both:
  - **Raw text values** (exactly as shown on the website).
  - **Normalized numeric forms** (for potential analytics).

---

## Phase 2 – Knowledge Modeling, Chunking & Embeddings (RAG Index Layer)

### Goals

- Transform canonical data into **semantic text chunks** suitable for retrieval.
- Compute embeddings and store them in a **vector database**.
- Ensure that **all chatbot answers come from these chunks**.

### Responsibilities

- Generate human-readable, fact-focused text from structured records.
- Chunk the text into topically coherent segments.
- Tag chunks with metadata (scheme id, topic, source URL, timestamps).
- Compute embeddings and store them with metadata.

### Knowledge Modeling

For each scheme, derive internal “fact documents,” for example:

- **Scheme summary**
  - A concise textual summary covering name, category, benchmark, AUM, inception date, and risk.
- **Key metrics – overview**
  - NAV, returns, expense ratio, AUM, benchmark, min SIP/lumpsum, exit load, lock-in, turnover, risk.
- **Optional glossary entries**
  - Generic explanations of terms: NAV, expense ratio, exit load, lock-in, etc., from neutral, regulatory or AMC glossaries.
  - These are **not recommendations** and are the same across schemes.

Each document includes:

- Scheme name + scheme_id (except generic glossary docs).
+- `source_url` (INDSMoney scheme URL or educational site for glossary).
- Data freshness info (e.g., “NAV as on DD MMM YYYY”).
- Category tags: `["overview"]`, `["returns"]`, `["fees"]`, `["risk"]`, `["min-investment"]`, etc.

### Chunking Strategy

- Chunk size: ~200–500 tokens per chunk.
- Separate chunks per topic, e.g.:
  - `HDFC Focused Fund – Overview`
  - `HDFC Focused Fund – Returns & Performance`
  - `HDFC Focused Fund – Fees & Expenses`
  - `HDFC Focused Fund – Minimum Investment & Exit Load`
  - `HDFC Focused Fund – Risk Profile`
- Always embed **source URL(s)** directly into chunk metadata.

Example chunk (pre-embedding text):

> HDFC Focused Fund – Overview  
> Source: https://www.indmoney.com/mutual-funds/hdfc-focused-fund-direct-plan-growth-option-2795  
> As on 01 Jan 2026, the NAV of HDFC Focused Fund Direct Plan Growth Option is ₹XXX. The fund’s expense ratio is Y%. The scheme’s benchmark is ZZZ. The Assets Under Management (AUM) are ₹AAA crore. The fund was launched on DD MMM YYYY. The minimum lumpsum investment is ₹X and the minimum SIP investment is ₹Y. The exit load is ..., lock-in is ..., the portfolio turnover is ..., and the SEBI risk label is “Very High”.

### Embeddings Infrastructure

- **Embedding model**: Choose a high-quality text embedding model (OpenAI, Cohere, or other) in early phases; later align with Groq-compatible stack if needed.
- **Vector store**:
  - Recommended: PostgreSQL + `pgvector`.
  - Alternative: Pinecone, Qdrant, Weaviate, etc.

Suggested `embeddings` table schema (PostgreSQL with pgvector):

- `id` (UUID, PK)
- `scheme_id` (string)
- `text` (chunk content)
- `metadata` (JSONB) – includes:
  - `source_url`
  - `scheme_name`
  - `tags` (list)
  - `scraped_at`
  - `chunk_type` (overview/returns/fees/etc.)
- `embedding` (vector)

### Policy Enforcement at This Layer

- Only include **public, non-personal facts** in the chunks.
- Exclude any text that could be interpreted as:
  - A recommendation (e.g., “suitable for aggressive investors”).
  - A personal or behavioral suggestion (“you should consider”).

---

## Phase 3 – RAG Answering Engine with Groq (LLM Layer)

### Goals

- Use Groq as the LLM to generate natural-language answers.
- Enforce that **all answers are grounded in retrieved chunks**.
- Implement strict guardrails for:
  - No advice / portfolio recommendations.
  - No personal/account information.
  - Mandatory source links.

### Query Flow

1. **User query received** by backend (`/chat/query`).
2. **Classification / Intent detection**:
   - Categories:
     - **Fund-fact** (e.g., “What is the NAV of HDFC Focused Fund?”).
     - **Concept/explanation** (e.g., “What is exit load?”).
     - **Opinionated/portfolio/advisory** (e.g., “Should I buy this fund?”, “Which fund is best?”).
     - **Personal/account-specific** (e.g., “What is my SIP amount?”, “Check my KYC status”).
     - **Out-of-domain** (irrelevant topics).
   - Implementation:
     - Start with rule-based keyword detection and regex for personal data patterns.
     - Optionally add a light classification model later.
3. **Branching**:
   - If **opinionated/portfolio/advisory**:
     - Skip retrieval or restrict to generic educational chunks.
     - Return a **polite refusal**:
       - Explain that the assistant is facts-only and cannot give buy/sell/hold or “best fund” opinions.
       - Provide neutral educational links (e.g., SEBI investor education) and/or general INDMoney pages.
   - If **personal/account-specific**:
     - Refuse and direct the user to official INDMoney or AMC support channels.
     - Do **not** attempt to guess or use any personal data.
   - If **fund-fact or concept/explanation**:
     - Proceed with **vector retrieval**.
4. **Vector Retrieval**:
   - Identify mentioned schemes by matching user text against known scheme names/aliases.
   - Construct a semantic search query using the user question.
   - Retrieve top-k relevant chunks (e.g., `k = 5`) filtered by target schemes and topic if known.
   - If no relevant chunks are retrieved or similarity is below a threshold:
     - Answer with “I don’t have that information in my current dataset” and do **not** guess.
5. **Groq Prompt Construction**:
   - **System message**:
     - Define role as a **facts-only mutual fund FAQ assistant**.
     - Explicitly forbid:
       - Investment advice or recommendations.
       - Portfolio construction guidance.
       - Buy/sell/hold opinions.
       - Any use of knowledge outside the provided context.
       - Handling personal/account-specific questions.
     - Require:
       - Use only the provided context chunks to answer.
       - If information is missing, say so clearly.
       - Include a **“Sources” section** listing one or more URLs from chunk metadata.
       - Use a polite refusal pattern for opinionated or personal questions.
   - **Context message**:
     - Concatenate retrieved chunks (with scheme names and source URLs).
   - **User message**:
     - Original user query.
6. **Groq Response**:
   - LLM generates a structured answer.
   - Backend post-processes:
     - Extracts or reconstructs **source URLs** from chunk metadata.
     - Deduplicates URLs.
     - Ensures the final API response includes `sources: [url1, url2, ...]`.

### Refusal & Educational Link Behavior

- For **opinionated/portfolio** questions:
  - Example response pattern:
    - “I’m a facts-only assistant and cannot provide opinions, personalized recommendations, or buy/sell advice.”
    - “I can share objective details like NAV, past returns, expense ratio, and risk level. Deciding if a fund is right for you depends on your goals and risk profile.”
    - “For personalized guidance, please consult a SEBI-registered financial advisor or use official INDMoney tools.”
  - **Sources**:
    - Relevant scheme page(s).
    - At least one **educational link** (e.g., SEBI investor education website or an INDMoney education article).

### Enforcement of “Embeddings Only”

- The backend **never calls Groq without providing context**.
- If retrieval fails:
  - The system instructs Groq to respond along the lines of:
    - “I don’t have this information in the data I have access to,” without hallucinating.
- No direct web access from Groq; only server-side retrieval is allowed.

---

## Phase 4 – Backend & API Layer (Chat Application Backend)

### Goals

- Provide a clean, secure API for the frontend and tools.
- Encapsulate scraping, indexing, and answering functionality.
- Centralize policy enforcement (no advice, no PII, sources, etc.).

### Suggested Tech Stack

- **Language/Framework**: Python + FastAPI (or Node.js + NestJS/Express).
- **Database**: PostgreSQL with `pgvector` extension.
- **Message Bus / Jobs (optional)**: Celery / RQ / APScheduler for background jobs.
- **LLM Client**: Groq SDK or HTTP client.

### Key Services & Endpoints

1. **Ingestion/Indexing (internal/admin only)**
   - `POST /admin/ingest`
     - Triggers Phase 1 scraping and Phase 2 embedding generation for all or specified schemes.
   - `POST /admin/ingest/{scheme_id}`
     - Re-ingest a single scheme.

2. **Chat/RAG API**
   - `POST /chat/query`
     - Request:
       - `message`: user input.
       - Optional: `session_id`, `user_id` (not used for personalization; for logging only).
     - Response:
       - `answer`: assistant text.
       - `sources`: list of URLs used.
       - `metadata` (optional): scheme_ids touched, scraped_at, etc.

3. **Meta Data APIs**
   - `GET /funds`
     - Returns list of all supported schemes and high-level attributes (name, category, URL).
   - `GET /funds/{scheme_id}`
     - Returns canonical Phase 1 data for that scheme (for debugging/inspection).

### Backend Guardrails

- **Intent classifier middleware**:
  - Inspects each request before RAG:
    - If it detects personal/account-related or advisory intent, short-circuits to a refusal response.
- **Source enforcement**:
  - All chunk-level metadata includes `source_url`.
  - RAG service aggregates and deduplicates source URLs and injects them into API responses.
- **Logging & auditing**:
  - Log user queries, classification result, retrieval stats (k, similarity scores, selected schemes).
  - Logs must **not** store sensitive user data (but should capture patterns like “advice-request detected”).

---

## Phase 5 – Frontend (Chat UI)

### Goals

- Provide a user-friendly chat interface.
- Clearly communicate limitations (no advice, no personal info).
- Highlight sources and scheme details.

### Suggested Tech Stack

- **React** + TypeScript.
- UI toolkit: MUI / Chakra UI / Tailwind CSS-based design system.

### Core UI Elements

- **Chat window**:
  - Message bubbles for user and bot.
  - Typing indicator when the bot is generating an answer.
- **Sources section** under each bot reply:
  - List of clickable links:
    - Primary: the specific INDMoney fund URL(s).
    - Secondary: any educational link(s) when relevant.
- **Scheme quick filters** (optional but useful):
  - Buttons or dropdown listing the 8 HDFC schemes to help users specify exactly which fund they are asking about.
- **Disclaimers**:
  - Static banner at top or bottom:
    - “This chatbot is a facts-only FAQ assistant for certain HDFC mutual fund schemes on INDMoney. It does not provide investment advice or handle personal/account-specific queries.”
  - Footnote in chat area reinforcing that past performance is not indicative of future returns.

### UX Behaviors

- If a question is detected as advisory/personal:
  - The bot returns a **clear refusal message** with an educational link.
  - The UI visually distinguishes such messages (e.g., with an info icon or different background).
- For factual questions:
  - The answer includes:
    - A brief summary sentence.
    - (Optionally) a compact table of key metrics (e.g., NAV, expense ratio, AUM, risk).
    - A “Sources” section with the underlying URLs.

---

## Phase 6 – Scheduler & Auto-Refresh Pipeline

### Goals

- Keep fund data up to date automatically.
- Orchestrate periodic re-scraping, re-chunking, and re-embedding.

### Scheduler Design

- **Options**:
  - Cron jobs (server-level).
  - A scheduler library (e.g., APScheduler in Python).
  - Cloud-native schedulers (Cloud Scheduler, EventBridge, etc.).

### Job Types

1. **Scrape Job**
   - Runs on a schedule:
     - NAV / returns: **daily** on trading days.
     - Structural fields (lock-in, benchmark, AUM, etc.): **daily or weekly**.
   - Steps:
     - Iterate over allowlisted URLs.
     - Run Phase 1 scraping.
     - Compare with previous snapshot per scheme:
       - If changes detected in key fields, mark scheme as “dirty/updated”.

2. **Rebuild Chunks & Embeddings Job**
   - For schemes marked as updated:
     - Regenerate Phase 2 text chunks.
     - Recompute embeddings.
     - Upsert into the vector store.
     - Optionally soft-delete or version old chunks.

3. **Health Check / Smoke Test Job**
   - After each refresh cycle:
     - Run a small set of canned queries (e.g., “What is the NAV of HDFC Flexi Cap Fund?”).
     - Validate that answers:
       - Are non-empty.
       - Include source links.
       - Show the correct “as on” dates when available.

### Trigger Chain

- **Scheduler → Scraper (Phase 1) → Chunker + Embeddings (Phase 2)**.
- Backend reads always from the **latest dataset** (e.g., by timestamp/version).

### Monitoring & Alerts

- Metrics:
  - Last successful scrape time per URL.
  - Number of chunks per scheme.
  - Embedding generation failures.
  - Average chat response latency.
- Alerts:
  - Scrape failures.
  - Sudden reduction in chunks or missing data for any scheme (indicates layout changes or parsing errors).

---

## Non-Functional Considerations

- **Security & Privacy**
  - No storage or processing of sensitive PII.
  - HTTPS for all API calls.
  - Admin endpoints for ingestion must be authenticated.
- **Scalability**
  - Stateless chat API; can be horizontally scaled.
  - Vector DB sized for current and future number of schemes.
- **Extensibility**
  - Easy to add new mutual funds:
    - Add URL to allowlist.
    - Add scheme metadata mapping.
    - Let the next scheduler run handle ingestion and indexing.
- **Observability**
  - Central logging for:
    - Ingestion runs.
    - Retrieval performance.
    - LLM call success/failure and latency.

---

## Summary

This architecture breaks the chatbot into clear, reviewable phases:

- **Phase 1**: Scrape and normalize fund data from a fixed set of INDMoney URLs.
- **Phase 2**: Model knowledge into topic-specific text chunks and embeddings with rich metadata and source URLs.
- **Phase 3**: Use Groq in a strict RAG pipeline with classification and guardrails: embeddings-only answers, mandatory sources, no advice, no personal queries.
- **Phase 4**: Backend API that orchestrates ingestion, retrieval, and answer generation, enforcing policies.
- **Phase 5**: Frontend chat UI that clearly communicates limitations and always shows sources.
- **Phase 6**: Scheduler that keeps data and embeddings up to date and monitors the pipeline.

This design ensures the chatbot remains **facts-only, up-to-date, source-cited, and compliant with non-advisory and non-personal-information constraints**.

