# RSS & Newsletter Aggregator Worker

Self-hosted personal news pipeline that fetches curated RSS/Atom feeds and delivers deduplicated articles straight into a Notion reading inbox — no manual curation, no Notion AI credits, no third-party SaaS.

## What it does
- Reads an active list of feed URLs from a Notion Feed Sources database.
- Fetches and parses each feed (RSS/Atom) via feedparser.
- Dedupes against every article already ingested, via a live paginated query against the Content Inbox (no fragile local cache).
- Writes new articles into a Notion Content Inbox database with title, source, category, published date, and snippet.
- Runs automatically 3x/day (07:00, 13:00, 19:00) via a systemd timer, fully containerized in Docker.

## Why
Built to replace passive social-media scrolling with an intentional, curated reading queue, and as a hands-on project for Docker, systemd, git/GitHub, and Notion API automation.

## Architecture
    systemd timer (3x/day)
      -> docker compose run --rm rss-aggregator
           -> run_ingest.py
                1. Load active feeds from Notion "Feed Sources"
                2. Fetch + parse each feed (feedparser)
                3. Query existing Content Inbox URLs (dedup)
                4. Insert new articles into Content Inbox
                5. Prune: move rows older than 30 days (Keep unchecked) to the Notion trash

## Tech stack
- Python 3.13 (feedparser, notion-client, python-dotenv)
- Docker + Docker Compose (deployed runtime)
- systemd service + timer (scheduling)
- Notion API (control plane: feed list + inbox storage)

## Setup
    git clone git@github.com:slabonte117/rss-aggregator.git
    cd rss-aggregator
    cp .env.template .env
    docker compose build
    docker compose run --rm rss-aggregator

## Pruning
After each ingest, rows created more than 30 days ago are moved to the Notion trash unless the row's **Keep** checkbox is checked. Each run is capped (1500 rows, 10 minutes) so the first runs work through the backlog in slices without delaying the next ingest. Preview first with `docker compose run --rm rss-aggregator python prune.py --dry-run`. Settings are in `.env.template`.

## Scheduling (systemd)
    sudo cp deploy/rss-aggregator.service deploy/rss-aggregator.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now rss-aggregator.timer

## Project layout
| File | Purpose |
|---|---|
| run_ingest.py | Main ingest pipeline |
| prune.py | 30-day prune of the News Feed (Keep checkbox protects rows); `python prune.py --dry-run` previews |
| tests/ | Unit tests for the prune (`python -m unittest discover -s tests -t .`) |
| Dockerfile / docker-compose.yml | Containerized runtime |
| deploy/rss-aggregator.service / .timer | systemd scheduling |
| .env.template | Required environment variables |
| check_env.py | Verifies .env is loadable |
| cleanup_duplicates.py | One-off dedup cleanup utility |
| dry_run_*.py | Local dry-run/debug scripts (no writes) |

## Status
Actively running in production on a home Debian/Docker host, ingesting curated feeds 3x daily into a personal Notion workspace.
