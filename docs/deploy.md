# Deploying gift-exchange

The app runs on the Droplet (see **Hosting** in CLAUDE.md) as two Docker Compose services:

- `app` — the NiceGUI app, built from `Dockerfile`. The SQLite DB and its migration
  snapshots live in the `appdata` volume (`/app/data` in the container).
- `caddy` — HTTPS in front of the app (`Caddyfile`). It gets and renews the Let's Encrypt
  certificate itself; certificates live in the `caddy_data` volume.

Only ports 22, 80 and 443 are open (DigitalOcean Cloud Firewall `santa-web`; ufw isn't
used because Docker bypasses it). The app's port 8080 is reachable only by Caddy.

## Server setup (done once, already done for the current Droplet)

- Droplet: Docker on Ubuntu, 1 GB, SGP1. SSH host alias `root.droplet1` in the laptop's `~/.ssh/config`.
- 2 GB swap (`/swapfile`, `vm.swappiness=10`) so image builds don't run out of memory.
- Docker log cap in `/etc/docker/daemon.json`: 3 × 10 MB per container.
- Cloudflare: `A santa → <Droplet IP>`, **DNS only** (Caddy needs the real IP for HTTPS).

## First deploy

```sh
ssh root.droplet1
git clone https://github.com/<owner>/gift-exchange.git ~/gift-exchange
```

From the laptop, copy the production settings (never committed) to the Droplet as `.env`:

```sh
scp .env.production root.droplet1:~/gift-exchange/.env
```

On the Droplet:

```sh
cd ~/gift-exchange
chmod 600 .env
docker compose up -d --build
docker compose logs -f        # wait for "Applied migrations" and Caddy's "certificate obtained"
```

Then open https://santa.mangobello.dev and log in with the `ADMIN_EMAILS` address.

`docker-compose.yml` fixes `HOST`, `PORT` and `DB_PATH` for the container, so `.env` only
needs the secrets and `DEV=0`, `BASE_URL`, `ADMIN_EMAILS`, `EMAIL_FROM`.

## Updating

```sh
ssh root.droplet1
cd ~/gift-exchange && git pull && docker compose up -d --build
```

Migrations run automatically at startup, after a snapshot (see `docs/migrations.md`). Only
the app restarts; logged-in people stay logged in (the session is a signed cookie).

## Everyday commands (on the Droplet, in `~/gift-exchange`)

| What | Command |
|---|---|
| Status | `docker compose ps` |
| Logs (follow) | `docker compose logs -f app` (or `caddy`) |
| Emails sent | `docker compose logs app \| grep "Sent email"` |
| Restart the app | `docker compose restart app` |
| Migration status | `docker compose exec app python -m gift_exchange.migrate status` |
| Stop everything | `docker compose down` (volumes, i.e. the DB and certificates, are kept) |

Never run `docker compose down -v`: `-v` deletes the volumes, including the database.

## Backups (manual, until R2 backups exist)

Take one before the matching day and after the event. On the Droplet:

```sh
docker compose exec app python -c "import sqlite3; sqlite3.connect('data/gift.db').backup(sqlite3.connect('data/backup.db'))"
docker compose cp app:/app/data/backup.db ./backup.db
```

Then on the laptop: `scp root.droplet1:~/gift-exchange/backup.db data/gift-$(date +%F).db`.
SQLite's backup API gives a consistent copy even while the app is running.

### Restore

```sh
docker compose stop app
docker compose cp ./backup.db app:/app/data/gift.db
docker compose start app
```

## Off-season: shut down and bring back

The app is only needed around the event, and the Droplet is billed hourly.

**Shut down:** take a backup (above) and keep it, plus `.env.production`, on the laptop.
Then destroy the Droplet in DigitalOcean (the `santa-web` firewall stays).

**Bring back:** create a Droplet as in **Server setup**, attach the `santa-web` firewall,
point the Cloudflare `santa` record at the new IP, do **First deploy**, then **Restore** the
backup. Keeping the same `SECRET_KEY` keeps old login sessions valid; a new one just logs
everyone out.

## Local test of the production setup

Runs the same Compose stack on the laptop with Caddy's self-signed certificate for
`localhost`, on ports 8180/8443 so nothing clashes:

```sh
SITE_ADDRESS=localhost HTTP_PORT=8180 HTTPS_PORT=8443 docker compose -p santa-test up -d --build
# open https://localhost:8443 (accept the certificate warning)
SITE_ADDRESS=localhost HTTP_PORT=8180 HTTPS_PORT=8443 docker compose -p santa-test down -v
```

It reads `.env`. For production-like behaviour use an env file with `DEV=0` and
`BASE_URL=https://localhost:8443`, but don't request login links unless you mean to
send real email.
