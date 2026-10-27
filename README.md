# RadiUp.ai

RadiUp.ai helps hackathons, olympiads, science fairs and fests reach student communities and build balanced participant teams. Organisers use Radar and the Organiser Desk; participants register in the mobile web chat and can share teammate invites through WhatsApp.

## What is included

- FastAPI service and static website (`/`, `/submit/`, `/track/`, `/app/`, `/join/`)
- Community discovery, outreach drafts, approval and tracked referral links
- Three-step browser registration using the existing squad balancer
- WhatsApp teammate sharing after registration
- SQLite storage and a Render Blueprint

Telegram remains an optional community outreach channel. Participant registration runs on the website.

## Run locally

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/` for the site or `http://localhost:8000/join/` for the join chat. The development configuration seeds sample communities and an event. Generated tracked links use `SITE_URL`, Render's `RENDER_EXTERNAL_URL`, or `http://localhost:8000`, in that order.

## Deploy on Render

Push this repository to GitHub and create or update the Render service from `render.yaml`. Render supplies `ADMIN_TOKEN` and `SERVICE_API_KEY`. When updating an existing Render service, make sure `SERVICE_API_KEY` is present in its Environment settings (at least 32 characters and different from `ADMIN_TOKEN`) before redeploying. Set `SITE_URL` only if your host does not provide `RENDER_EXTERNAL_URL`. Outreach, event and teammate links open the browser join page on the same origin as the site.

The free Render plan can sleep and does not persist local SQLite files. For real participant data, use a paid service with a persistent disk and set `RADAR_DB_PATH` to the disk path in `render.yaml`.

## Configuration

Copy `.env.example` to `.env`. In production, set strong, unique `ADMIN_TOKEN` and `SERVICE_API_KEY` values. `TRUSTED_HOSTS` should list the hostnames you serve, and `TRUST_PROXY=true` should only be enabled behind a trusted reverse proxy.

## Security model

- Public: health check and rate-limited browser join endpoints.
- Internal service key (`X-Service-Key`): participant management endpoints.
- Organiser token (`Authorization: Bearer ...`): organiser desk and administration.

The browser join endpoints expose only event attribution and the participant information needed to complete registration. Confirmation and withdrawal remain protected.
