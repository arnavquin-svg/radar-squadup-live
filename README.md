# RadiUp.ai

> Radar brings people in. SquadUp makes each person bring more.

RadiUp.ai runs on two engines: **Radar** (finding and reaching the right student groups) and **SquadUp** (sign-ups, teams and reminders in Telegram).

Built for the **X AI Tech Ideathon, Problem Statement 2: AI for Event Reach and Registration.**

First-time organisers of hackathons, olympiads, science fairs and fests don't have followers or ad budgets, so their reach stops at their own circle. RadiUp.ai gets the first hundred sign-ups through the people who already have the audience: club and group admins.

### Who uses what

| Who | What they use | Where |
|---|---|---|
| **Event host** (runs the hackathon or fest) | Submits the event, then follows progress on a private link | `/submit/` and `/track/` on the website |
| **Your team** (runs the reach) | Accepts requests, runs Radar, approves messages, watches squads | Organiser desk at `/app/`, behind an access key |
| **Group admins** (club heads) | Receive your approved message and decide whether to forward it | Their own WhatsApp / Telegram / Instagram |
| **Participants** (students) | Register, get a team, invite friends, confirm attendance | The Telegram bot |

- **Radar** ranks the student clubs and communities most likely to care about an event and drafts a message to each admin in English, Hindi or Marathi, using only facts from the event details. Nothing is sent automatically: your team approves each message, which unlocks its tracked link, and sends it.
- **SquadUp** is a Telegram bot. Tapping a tracked link registers someone in three taps, seats them in a balanced team of four (Developer, Designer, Domain expert, Presenter), gives them an invite link that reserves their team's open seats for friends, and sends 7/2/1-day reminders with one-tap confirm or "I can't make it".

```
radar-squadup/
├── app/
│   ├── main.py          routes (public / bot / organiser), app factory, error handling
│   ├── config.py        validated settings from environment variables
│   ├── security.py      access keys, rate limiting, body-size limit, security headers
│   ├── schemas.py       strict request validation
│   ├── radar.py         event profiling, community ranking, message drafting
│   ├── squad.py         team balancing and team cards
│   ├── db.py            SQLite schema, versioning and connections
│   └── seed.py          sample community directory and demo event
├── bot/
│   ├── telegram_bot.py  SquadUp bot (inline buttons, reminders, flood control)
│   └── i18n.py          English and Hindi strings
├── web/
│   ├── index.html       landing page for event hosts
│   ├── submit/          "Submit your event" form
│   ├── track/           private progress page for hosts
│   ├── app/             organiser desk (your team)
│   └── assets/          styles and scripts (no inline scripts or styles anywhere)
├── tests/               API, validation and security tests
├── render.yaml          one-click hosting on Render
├── Dockerfile, docker-compose.yml, .env.example
└── requirements.txt, requirements-dev.txt
```

---

## Put it online (no terminal needed)

1. **Make a GitHub repository.** On github.com click **New**, name it, leave every box unticked, and create it. On the empty repository page, click **uploading an existing file** and drag in everything inside this project folder (not the `.venv` folder, `radar.db` or `.env` if you have them). Click **Commit changes**.
2. **Create the site on Render.** Sign in at [render.com](https://render.com) with GitHub, click **New → Blueprint**, pick your repository and click **Apply**. Render reads `render.yaml`, installs everything, and gives you an address like `https://radar-squadup.onrender.com`.
3. **Get your team's access key.** In Render, open the **radar-squadup** service → **Environment**, and copy the value of `ADMIN_TOKEN`.
4. **Use it.** Event hosts go to `https://<your-address>/submit/`. Your team signs in at `https://<your-address>/app/` with the access key.
5. **Updates.** Upload changed files to GitHub the same way; Render redeploys on its own.

The default plan is **free**: good for demos, but the site sleeps after 15 idle minutes (the first visit after that takes about a minute) and its data resets when it sleeps or redeploys. For real use, follow the comments at the top of `render.yaml` to switch to a paid instance with a persistent disk.

**The Telegram bot** needs an always-on process, which Render's free plan doesn't offer. For a demo, run it on your laptop pointing at the hosted site: set `RADAR_API_URL` to your Render address and `BOT_API_KEY` to the value shown in Render, then `python -m bot.telegram_bot`. For real use, add a Render background worker (paid) with the start command `python -m bot.telegram_bot` and the same environment variables.

---

## Run it locally

Requires **Python 3.10+**.

```bash
git clone <your-repo-url> radar-squadup && cd radar-squadup
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                   # Windows: copy .env.example .env
```

Generate two secrets and put them in `.env` as `ADMIN_TOKEN` and `BOT_API_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Start the API and website:

```bash
uvicorn app.main:app --reload --env-file .env
```

- Website: <http://localhost:8000/>
- Organiser desk: <http://localhost:8000/app/>. Sign in with your `ADMIN_TOKEN`.
- API docs (development only): <http://localhost:8000/docs>

In development the server loads a sample directory of 32 made-up community groups and a demo event. If you skip setting `ADMIN_TOKEN`, a temporary one is generated and printed in the terminal on each start.

### Try the flow without Telegram

0. **Requests**: open `/submit/` in another tab and send a test event. It appears under **Requests** in the desk; **Accept** creates the event and runs Radar. The host's private link (shown after submitting) now shows progress.
1. **Radar** → *Run Radar*. Ranked groups appear on the map and in the list.
2. **Outreach** → open a message, switch its language if you like, edit it, then *Approve message*. The tracked link unlocks; *Copy message* gives you the text to send to the admin yourself.
3. **Squads** → *Add 12 sample sign-ups* (development only). Synthetic participants arrive through your approved links and are seated by the balancer; they're flagged `is_synthetic` in the database.
4. **Overview** shows the funnel, sources, skill mix and latest sign-ups, refreshing every few seconds.

### Connect the Telegram bot

1. In Telegram, message **@BotFather** → `/newbot`. Copy the token into `.env` as `TELEGRAM_BOT_TOKEN`, and the bot's username as `TELEGRAM_BOT_USERNAME`.
2. Restart the API so links use your bot's username.
3. In a second terminal, check everything is connected with `python -m bot.check`, then start the bot with `python -m bot.telegram_bot` (both read `.env` themselves).
4. Open an approved link from the desk on your phone and register.

Bot commands: `/start`, `/team`, `/invite`, `/confirm`, `/lang`, `/help`, and `/demo_reminder` (sends the 1-day reminder in 10 seconds, for demos).

### Tests

```bash
pytest -q
```

---

## Deploy to production

```bash
cp .env.example .env
# set APP_ENV=production, ADMIN_TOKEN, BOT_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME,
# TRUSTED_HOSTS=your.domain, TRUST_PROXY=true (behind a proxy)
docker compose up -d --build
```

- The API listens on `127.0.0.1:8000`. Put a TLS-terminating reverse proxy in front of it (Caddy, Nginx, or your platform's load balancer). Example Caddyfile: `radar.example.org { reverse_proxy 127.0.0.1:8000 }`.
- When behind a proxy, also set `FORWARDED_ALLOW_IPS` to the proxy's address so client IPs (used for rate limiting) and HTTPS detection (used for HSTS) are correct.
- Data lives in the `radar-data` volume (`/data/radar.db`). Back it up with `sqlite3 /data/radar.db ".backup /data/backup.db"` or by copying the volume while the API is stopped.
- Containers run as a non-root user with a read-only filesystem and `no-new-privileges`.
- On platforms without Docker Compose (Render, Railway, Fly.io), deploy the same image twice: once with the default command (the API) and once with `python -m bot.telegram_bot` (the bot), sharing the same environment variables.

In production the server **refuses to start** unless `ADMIN_TOKEN` and `BOT_API_KEY` are set, at least 32 characters long, and different, and `TELEGRAM_BOT_USERNAME` is valid. Sample data, the sign-up simulator and the API docs are off unless you explicitly turn them on.

---

## Security model

| Area | What's in place |
|---|---|
| Access control | Three tiers. Public: `/api/health` only. Bot (`X-Service-Key: BOT_API_KEY`): registration, confirmations and reminders. Organiser (`Authorization: Bearer ADMIN_TOKEN`): everything else. Keys are compared in constant time. The bot's key cannot reach organiser routes. |
| Brute force | After 10 failed sign-ins from one address in 15 minutes (configurable), that address is blocked for the rest of the window, even with the right key. |
| Rate limiting | 120 requests per minute per IP on `/api` (configurable). The bot gets a larger shared budget because it relays many users. For multi-instance deployments, also limit at the proxy. |
| Input validation | Every request body rejects unknown fields. Text is NFC-normalised, and control characters, zero-width characters and bidirectional overrides are stripped. Single-line fields refuse `<` and `>` and must contain a letter where a name is expected. Lengths, number ranges, dates (today up to 3 years ahead), languages, roles, platforms, topics and link payloads are all checked. Path and query parameters are typed and bounded. Errors never echo the submitted input. |
| Business rules | A message can't be approved if the tracked link was removed from it. Approved messages are locked until moved back to review. Bot buttons only act on the pressing user's own registration. |
| SQL | Every query uses bound parameters. The only dynamic SQL fragment is chosen from a fixed internal map. |
| XSS / clickjacking | Strict Content-Security-Policy (`script-src 'self'`, no inline scripts or styles, `frame-ancestors 'none'`), with all rendered data escaped in the desk. Also `X-Frame-Options: DENY`, `nosniff`, a strict referrer policy, a locked-down permissions policy, and HSTS over HTTPS. API responses are `no-store`. |
| Payload limits | Request bodies over 64 KB are rejected, whether or not `Content-Length` is honest. |
| Sessions | The desk keeps the access key in `sessionStorage` (cleared when the tab closes), and signs out on any 401. |
| Errors | Unexpected errors return a generic message with a request ID; details go to the server log only. |
| Event requests | The public form is limited to 5 submissions per network per hour (and a global cap), silently drops bots that fill a hidden field, rejects duplicates, and requires consent to be contacted. Hosts get a private tracking token that is stored only as a SHA-256 hash, kept in the URL fragment (never sent to servers or in Referer headers), and only ever reveals progress counts, not contact details. |
| Privacy | Team cards that circulate in group chats only carry first names and roles. Host contact details are visible only in the organiser desk. All sample data in this repository is made up. |

---

## How it works

### Radar ranking

Radar profiles the event from its form: topics (tags plus keywords in the name and description), skill level, city and draft languages. Each community is scored with the blueprint's formula:

```
Score = 22 × (topics shared with the event) + 25 (if in the same city) + size factor
size factor = min(15, 5 × log10(members))      # 100 members → 10, 1,000+ → 15
```

A group needs a shared topic or the same city to qualify. The top 12 are kept, each with a one-line reason.

### Honest drafts

Drafts use only what the organiser typed: name, city, date, venue, the description's first sentence and team size, plus "first-timers welcome" only if the event is beginner-friendly. No invented numbers, deadlines or testimonials.

### Attribution

| Link payload | Meaning |
|---|---|
| `o_<code>` | an approved community message (counted as a click and a source) |
| `r_<code>` | an invite from a participant |
| `e_<id>` | a direct link to an event |

### Team balancing

1. Someone who came through a teammate's invite joins that team if it has a free seat.
2. Otherwise every open team is scored: +100 if it lacks their role, −40 per member who already has it, +10 per member (near-full teams fill first).
3. The best team wins if its score is positive; otherwise a new team opens.

### Growth loop

After registering, people can name their college or club. New names join the directory (shown as *Found through SquadUp*), so the next Radar run reaches networks the organiser didn't know about.

### Reminders

The bot schedules reminders 7, 2 and 1 day before the event at `REMINDER_HOUR` in `EVENT_TIMEZONE`, and rebuilds them from the API on restart.

---

## API reference

| Method | Path | Access |
|---|---|---|
| GET | `/api/health` | public |
| POST | `/api/requests` | public (5 per hour per network, honeypot, duplicate check) |
| POST | `/api/requests/status` | public with the private token |
| GET | `/api/requests` | organiser |
| POST | `/api/requests/{id}/accept` · `/decline` | organiser |
| GET | `/api/config` | organiser |
| GET / POST | `/api/events` | organiser |
| GET / DELETE | `/api/events/{id}` | organiser |
| GET | `/api/events/{id}/radar` | organiser |
| POST | `/api/events/{id}/radar/run` | organiser |
| GET / POST | `/api/communities` | organiser |
| GET | `/api/events/{id}/outreach?status=` | organiser |
| PATCH | `/api/outreach/{id}` | organiser |
| POST | `/api/outreach/{id}/approve` · `/reject` · `/reset` | organiser |
| GET | `/api/events/{id}/teams` · `/stats` | organiser |
| POST | `/api/events/{id}/simulate` | organiser (when enabled) |
| GET | `/api/ref/resolve?payload=` | bot |
| POST | `/api/ref/click?payload=` | bot |
| POST | `/api/register` | bot or organiser |
| GET | `/api/participants/lookup?telegram_id=` | bot |
| GET / PATCH | `/api/participants/{id}` | bot |
| POST | `/api/participants/{id}/confirm` · `/withdraw` | bot |
| GET | `/api/teams/{id}/card` | bot |
| GET | `/api/reminders` | bot |

## Configuration

All settings come from environment variables; see `.env.example` for the full list with comments.
# Browser-based SquadUp registration

Tracked outreach, event, and teammate referral links open the mobile web join flow at `/join/?start=...`. Participants choose a role, enter their name, and select their experience level; registration is handled by the existing SquadUp team balancer. After joining, they can invite teammates through WhatsApp.

The link base is selected in this order: `SITE_URL`, Render's `RENDER_EXTERNAL_URL`, then `http://localhost:8000` for local development. Set `SITE_URL` to the public HTTPS origin when deploying on a host that does not provide `RENDER_EXTERNAL_URL`. The Telegram bot remains available independently; the browser registration path does not require a Telegram account or bot token.

The public browser endpoints (`/api/join/resolve`, `/api/join/click`, and `/api/join/register`) use the app's existing per-IP API rate limit. Participant confirmation and withdrawal remain service-key protected.

