https://github.com/user-attachments/assets/0ed06e44-1210-4b7a-93de-09b4a1292947



[README.md](https://github.com/user-attachments/files/25764877/README.md)
# RAG-Based Mutual Fund FAQ Chatbot

A facts-only FAQ assistant for HDFC mutual funds on INDMoney. This chatbot provides factual information about mutual funds using a Retrieval-Augmented Generation (RAG) pipeline with Groq LLM.

![Chatbot Screenshot](https://via.placeholder.com/800x400?text=Chatbot+Screenshot)

## Features

- **Facts-Only Answers**: Provides only factual information from stored data, no investment advice
- **Source Citation**: Every answer includes source links to INDMoney fund pages
- **8 HDFC Mutual Funds**: Covers Flexi Cap, Small Cap, Mid Cap, Banking & Financial Services, Defence, Nifty Midcap 150, Nifty Private Bank ETF, and Focused funds
- **Daily Data Updates**: Automatic scheduler refreshes data daily at 10:00 AM UTC
- **Data Freshness Indicator**: UI shows when data was last updated

## Architecture

The system is divided into 6 phases:

| Phase | Component | Description |
|-------|-----------|-------------|
| Phase 1 | Data Acquisition | Scrapes fund data from INDMoney using Playwright |
| Phase 2 | Indexing | Creates text chunks and embeddings using sentence-transformers |
| Phase 3 | RAG Engine | Query classification, retrieval, and answer generation with Groq |
| Phase 4 | Backend API | FastAPI server for chat queries and fund metadata |
| Phase 5 | Frontend | React + TypeScript + Vite chat interface |
| Phase 6 | Scheduler | GitHub Actions workflow for daily data updates |

## Deployment

### Frontend (Vercel)
- **URL**: https://rag-based-mutualfund-faqchatbot.vercel.app
- **Framework**: React + TypeScript + Vite
- **Build Command**: `npm run build` (in `phase5/` directory)

### Backend (Render)
- **URL**: https://rag-based-mutualfund-faqchatbot.onrender.com
- **Health Check**: https://rag-based-mutualfund-faqchatbot.onrender.com/health
- **Framework**: FastAPI (Python)
- **Start Command**: `uvicorn render_main:app --host 0.0.0.0 --port $PORT`

### Scheduler (GitHub Actions)
- **Schedule**: Daily at 10:00 AM UTC
- **Workflow**: `.github/workflows/daily-scheduler.yml`
- **Steps**: Scrape → Index → Commit → Push

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Groq API key

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/asankhua/rag-based-mutualfund-faqchatbot.git
   cd rag-based-mutualfund-faqchatbot
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your GROQ_API_KEY
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Run the backend**
   ```bash
   uvicorn render_main:app --reload
   ```

5. **Run the frontend** (in a new terminal)
   ```bash
   cd phase5
   npm install
   npm run dev
   ```

6. **Open** http://localhost:5173

### Running the Scheduler Manually

```bash
python -m phase6.phase6_scheduler --run-once
```

## Environment Variables

| Variable | Description | Required For |
|----------|-------------|--------------|
| `GROQ_API_KEY` | Groq API key for LLM queries | Backend, GitHub Actions |
| `VITE_API_BASE_URL` | Backend API URL | Frontend (Vercel) |

## GitHub Actions Setup

1. Go to Repository Settings → Secrets and variables → Actions
2. Add `GROQ_API_KEY` secret
3. Go to Actions → General → Workflow permissions
4. Select "Read and write permissions"
5. Save changes

## Supported Mutual Funds

1. HDFC Flexi Cap Fund
2. HDFC Small Cap Fund
3. HDFC Nifty Midcap 150 Index Fund
4. HDFC Mid Cap Fund
5. HDFC Banking & Financial Services Fund
6. HDFC Defence Fund
7. HDFC Nifty Private Bank ETF
8. HDFC Focused Fund

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/status` | GET | System status with last updated date |
| `/funds` | GET | List all funds |
| `/funds/{scheme_id}` | GET | Get specific fund details |
| `/chat/query` | POST | Send chat query |

## Project Structure

```
.
├── .github/workflows/     # GitHub Actions workflows
├── api/                   # Vercel serverless API (legacy)
├── data/
│   ├── phase1/           # Scraped fund JSON files
│   ├── phase2/           # Chunks and embeddings
│   └── scheduler_metadata.json  # Last scheduler run timestamp
├── phase1/               # Web scraper
├── phase2/               # Text chunking and embedding
├── phase3/               # RAG engine
├── phase4/               # FastAPI backend
├── phase5/               # React frontend
├── phase6/               # Scheduler and orchestrator
├── render_main.py        # Render deployment entry point
├── requirements.txt      # Python dependencies
└── vercel.json          # Vercel configuration
```

## Constraints

- **No Investment Advice**: The chatbot only provides factual information
- **No Personal Data**: Does not handle portfolio, KYC, or account information
- **Public Sources Only**: Uses only official INDMoney scheme pages
- **Source Citation Required**: Every answer must include at least one source link

## License

MIT License

## Author

Ashish Sankhua
