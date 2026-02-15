# MU Result Parser API - Vercel Deployment

FastAPI service for parsing Mumbai University result PDFs, deployed on Vercel.

## API Endpoints

- `GET /` - API info
- `GET /health` - Health check
- `POST /parse` - Parse PDF file (multipart/form-data)

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
cd api
uvicorn index:app --reload
```

## Deploy to Vercel

1. Install Vercel CLI:
```bash
npm install -g vercel
```

2. Deploy:
```bash
cd parser-api
vercel
```

3. For production:
```bash
vercel --prod
```

## Environment Variables

No environment variables needed for basic deployment.

## Update CORS Origins

Edit `api/index.py` and update the `allow_origins` in CORS middleware to your production domain:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.vercel.app"],  # Update this
    ...
)
```

## File Structure

```
parser-api/
├── api/
│   ├── index.py       # Vercel entry point (FastAPI app)
│   └── parser.py      # MU Result Parser
├── requirements.txt   # Python dependencies
├── vercel.json       # Vercel configuration
└── README.md         # This file
```

## Usage

Once deployed, update your Next.js `.env` file:

```bash
PARSER_API_URL=https://your-api.vercel.app
```

And update `app/api/parse/route.ts` to use the environment variable.
