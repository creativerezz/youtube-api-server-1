# Railway Deployment Guide

## Quick Deploy

### Option 1: Via Railway Dashboard (Recommended)

1. Go to [Railway Dashboard](https://railway.app)
2. Select your FastAPI service
3. Go to **Variables** tab
4. Click **Import from File** and upload `.env.railway`
5. Railway will auto-deploy when you push to GitHub

### Option 2: Via Railway CLI

```bash
cd apps/fastapi

# Link to your project (first time only)
railway link

# Set environment variables
./set_railway_vars.sh

# Deploy
railway up
```

### Option 3: Manual Variable Setup

If the script doesn't work, set variables manually in Railway Dashboard or via CLI:

```bash
railway variables set HOST="0.0.0.0"
railway variables set YOUTUBE_API_KEY="your-key"
# ... etc
```

## Environment Variables

All FastAPI-specific variables are in `.env.railway`. 

**Note:** Variables like `NEXT_PUBLIC_*`, `GITHUB_CLIENT_ID`, `GOOGLE_CLIENT_ID`, etc. are for the Next.js frontend and should be set in the **web app's Railway service**, not the FastAPI service.

## Verify Deployment

```bash
# Check logs
railway logs

# Check status
railway status

# View deployed URL
railway domain
```

## Troubleshooting

- **Port issues**: Railway automatically sets `PORT`, don't override it
- **Build fails**: Check `railway.json` and ensure Python dependencies are in `requirements.txt`
- **Variables not loading**: Make sure variables are set in the correct service (FastAPI, not web)
