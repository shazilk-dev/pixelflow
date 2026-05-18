# Deployment Guide — Distributed Image Processing Pipeline

## The Core Challenge

This project has one architectural constraint that shapes every deployment decision:

```
API container ──┐
worker_1       ─┤── shared_data volume (/app/data/)
worker_2       ─┤   (uploads/ + outputs/ live here)
worker_3       ─┘
```

API and workers share a Docker volume. Every file uploaded via the API must be readable
by any worker, and every processed output must be readable by the API for the results page.
**Platforms that isolate containers from each other (most PaaS) break this.**

---

## Platform Decision Matrix

| Platform | Frontend | Backend | Shared Volume | Cost | Verdict |
|----------|----------|---------|---------------|------|---------|
| Vercel | ✅ Perfect (made for Next.js) | ❌ Serverless only | ❌ | Free | Frontend only |
| Railway | ✅ | ✅ Docker containers | ⚠️ One volume per service | $5 free/mo | Good, needs workaround |
| Render | ✅ | ✅ Docker containers | ❌ Paid plans only | Free spins down | Not ideal |
| Fly.io | ✅ | ✅ Docker native | ⚠️ Single-machine only | Free tier | Works with care |
| Oracle Cloud VM | N/A | ✅ Docker Compose as-is | ✅ Full support | **Free forever** | Best free backend |
| ngrok (local) | N/A | ✅ No changes | ✅ | Free | Best for demo day |

---

## Option A — Recommended: Vercel (frontend) + Railway (backend)

**Best for:** Quick deployment you can share a link to. Costs ~$0–2/month.

### Why Railway for the backend?
Railway runs real persistent Docker containers (not serverless). Redis is a one-click plugin.
It has internal networking between services and persistent volumes. The only limitation: each
volume can only attach to one service — so you need the workaround in Step 4.

---

### Step 1 — Deploy Redis on Railway

1. Go to [railway.app](https://railway.app) → New Project → **Add Redis**
2. Note the internal Redis URL: `redis://default:PASSWORD@redis.railway.internal:6379`
   (Railway shows this under the Redis service → Variables tab)

---

### Step 2 — Deploy the API on Railway

1. New Service → **Deploy from GitHub repo** → select this repo
2. Set **Root Directory** to `backend`
3. Railway auto-detects the Dockerfile in `./backend/`
4. Set environment variables:
   ```
   REDIS_URL=<internal Redis URL from Step 1>
   UPLOAD_DIR=/app/data/uploads
   OUTPUT_DIR=/app/data/outputs
   ```
5. Under **Volumes** → Add volume → mount at `/app/data`
6. Note the public URL Railway assigns (e.g. `https://api-xyz.up.railway.app`)

---

### Step 3 — Deploy Workers on Railway

Each worker is a **separate service** sharing the same backend Docker image.

For **worker_1**, **worker_2**, **worker_3** — repeat three times:

1. New Service → Deploy from GitHub → same repo, Root Directory `backend`
2. Override the **Start Command**:
   ```
   celery -A celery_app worker --loglevel=info --concurrency=1 -n worker_1@%h
   ```
   (change `worker_1` to `worker_2` / `worker_3` for each)
3. Environment variables:
   ```
   REDIS_URL=<internal Redis URL>
   UPLOAD_DIR=/app/data/uploads
   OUTPUT_DIR=/app/data/outputs
   WORKER_ID=worker_1
   ```
4. **Volume** — mount the **same volume name** from Step 2 at `/app/data`

> **Note:** Railway allows mounting the same volume to multiple services.
> This preserves the shared filesystem the project requires.

---

### Step 4 — Deploy Frontend on Vercel

1. Go to [vercel.com](https://vercel.com) → New Project → Import GitHub repo
2. Set **Root Directory** to `frontend`
3. Framework: Next.js (auto-detected)
4. Environment variables:
   ```
   NEXT_PUBLIC_API_URL=https://api-xyz.up.railway.app
   API_INTERNAL_URL=https://api-xyz.up.railway.app
   ```
   > On Vercel, server components run on Vercel's infrastructure (not inside Docker),
   > so both variables point to the same public Railway URL.
5. Deploy → Vercel gives you a `https://your-app.vercel.app` URL

---

### Step 5 — Fix CORS on the API

The API needs to allow requests from your Vercel domain. Add to `backend/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3400",
        "https://your-app.vercel.app",   # replace with your Vercel URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Redeploy the API service on Railway after this change.

---

## Option B — Best Free: Oracle Cloud Free Tier (Always-Free VM)

**Best for:** Zero cost, full architecture preserved, runs Docker Compose as-is.

Oracle Cloud has a genuinely free-forever ARM VM: 4 OCPUs, 24 GB RAM, 200 GB disk.
Run the exact same `docker compose up --build` on it as you do locally.

### Step 1 — Create the VM

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com) (credit card required for verification, not charged)
2. Create Instance → **Ampere A1** (ARM) → 4 OCPUs, 24 GB RAM → **Always Free**
3. Download the SSH key pair Oracle generates
4. Open ports in the Security List: **8000** (API) and **3400** (frontend)

### Step 2 — Install Docker on the VM

```bash
ssh -i your-key.pem ubuntu@<VM_PUBLIC_IP>

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
newgrp docker

# Install Docker Compose plugin
sudo apt-get install -y docker-compose-plugin
```

### Step 3 — Deploy the Project

```bash
git clone https://github.com/YOUR_USERNAME/parallel-distributed.git
cd parallel-distributed

# Copy and fill in the .env file
cp .env.example .env

# Change the frontend port mapping in docker-compose.yml: "3400:3000" → "80:3000"
# (So users visit http://IP directly, no port number)
sed -i 's/3400:3000/80:3000/' docker-compose.yml

# Build and start
docker compose up --build -d
```

### Step 4 — Set API URL

```bash
# In docker-compose.yml, update the frontend environment:
# NEXT_PUBLIC_API_URL=http://<VM_PUBLIC_IP>:8000
# API_INTERNAL_URL=http://api:8000   ← stays as-is (internal Docker network)
```

Your app is live at `http://<VM_PUBLIC_IP>` — no Vercel needed.

> **Tip:** Point a free domain from [Freenom](https://freenom.com) or
> [duckdns.org](https://duckdns.org) at your VM IP and add an Nginx reverse proxy
> for HTTPS (Let's Encrypt).

---

## Option C — Demo Day Only: ngrok (Quickest)

**Best for:** Presenting to your professor or panel right now with zero setup.

```bash
# Install ngrok (https://ngrok.com — free account required)
# Then, with docker compose already running locally:

# Expose the API
ngrok http 8000

# In a second terminal, expose the frontend
ngrok http 3400
```

ngrok gives you two public HTTPS URLs (e.g. `https://abc123.ngrok.io`).

Update the frontend's `NEXT_PUBLIC_API_URL` to the API ngrok URL:
```bash
# Stop frontend container, update env, restart
docker compose stop frontend
# Edit docker-compose.yml: NEXT_PUBLIC_API_URL=https://abc123.ngrok.io
docker compose up -d frontend
```

Share the frontend ngrok URL. Works instantly, costs nothing, no code changes.
Free ngrok URLs reset every 8 hours — fine for a demo session.

---

## Environment Variable Reference

### Backend (API + all workers)

| Variable | Local | Railway | Oracle Cloud VM |
|----------|-------|---------|-----------------|
| `REDIS_URL` | `redis://redis:6379/0` | Railway internal URL | `redis://redis:6379/0` |
| `UPLOAD_DIR` | `/app/data/uploads` | `/app/data/uploads` | `/app/data/uploads` |
| `OUTPUT_DIR` | `/app/data/outputs` | `/app/data/outputs` | `/app/data/outputs` |
| `WORKER_ID` | set per service | set per service | set per service |

### Frontend

| Variable | Local | Vercel + Railway | Oracle Cloud VM |
|----------|-------|-----------------|-----------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | `https://api-xyz.up.railway.app` | `http://<VM_IP>:8000` |
| `API_INTERNAL_URL` | `http://api:8000` | `https://api-xyz.up.railway.app` | `http://api:8000` |

> `API_INTERNAL_URL` and `NEXT_PUBLIC_API_URL` are **identical on Vercel** because
> Vercel server components run on Vercel's own servers, not inside your Docker network.
> On a VM, `API_INTERNAL_URL` stays as the Docker-internal `http://api:8000`.

---

## What Won't Work (and Why)

| Approach | Problem |
|----------|---------|
| Vercel for backend | Serverless — no persistent processes, Celery workers can't run |
| Render free tier | Services spin down after 15 min of inactivity, shared disk is paid-only |
| Heroku | Ephemeral filesystem — uploaded files disappear between dynos |
| Pure Fly.io multi-app | Fly volumes can't be shared across apps without NFS setup |
| Supabase / PlanetScale | SQL databases — this project is Redis-only by design |

---

## Post-Deployment Checklist

- [ ] `GET /api/workers/status` returns 3 workers (worker_1, worker_2, worker_3)
- [ ] Upload page accepts images and redirects to dashboard
- [ ] Dashboard shows worker cards updating in real time (SSE working)
- [ ] Kill Worker button sends signal and task reassigns
- [ ] Results page loads without error (server-side fetch using correct `API_INTERNAL_URL`)
- [ ] Speedup chart visible on results page
- [ ] Before/After gallery shows processed images

---

## Recommendation Summary

| Goal | Best Option |
|------|-------------|
| Quickest working demo | **ngrok** (10 minutes) |
| Free, architecture preserved | **Oracle Cloud Free Tier VM** |
| Shareable URL, small cost | **Railway + Vercel** |
| Frontend only (link to local API) | **Vercel** |
