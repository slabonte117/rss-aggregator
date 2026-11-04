"""Prune old News Feed rows.

Rule (Sean, 2026-11-03): rows created more than PRUNE_AFTER_DAYS (30) ago are moved
to the Notion trash unless their Keep checkbox is checked. Everything else in the
database is left alone.

Safety:
- The query filters on age and Keep, and every row is re-checked in code before it
  is touched. If the Keep property is missing from a row, the whole prune stops
  (fail closed) instead of guessing.
- A per-run cap and a time budget keep the prune from delaying the next ingest.
  The very first runs work through the backlog a slice at a time.
- PRUNE_DRY_RUN=1 (or --dry-run) counts and lists candidates and changes nothing.

Run standalone:  python prune.py --dry-run
Called at the end of run_ingest.py after ingest has finished.
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def env_flag(name, default="0"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


class PruneAbort(Exception):
    """Raised when something looks wrong and the prune must stop."""


def parse_created(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def should_prune(row, cutoff):
    """True only if the row is older than cutoff and Keep is explicitly unchecked."""
    props = row.get("properties", {})
    if "Keep" not in props or props["Keep"].get("type") != "checkbox":
        raise PruneAbort("Keep checkbox property not found on a row; stopping.")
    if props["Keep"].get("checkbox"):
        return False
    created = row.get("created_time")
    if not created:
        return False
    return parse_created(created) < cutoff


def build_filter(cutoff):
    return {
        "and": [
            {"timestamp": "created_time", "created_time": {"before": cutoff.isoformat()}},
            {"property": "Keep", "checkbox": {"equals": False}},
        ]
    }


def row_title(row):
    title = row.get("properties", {}).get("Title", {}).get("title", [])
    return "".join(t.get("plain_text", "") for t in title) or "(untitled)"


def archive_with_retry(notion, page_id, retries=5):
    for attempt in range(1, retries + 1):
        try:
            notion.pages.update(page_id=page_id, archived=True)
            return
        except Exception as e:  # notion_client.APIResponseError and network errors
            code = getattr(e, "code", "")
            if attempt == retries or code not in ("rate_limited", "internal_server_error", "service_unavailable"):
                raise
            time.sleep(2 * attempt)


def run_prune(notion, data_source_id, now=None, sleep=time.sleep):
    if not env_flag("PRUNE_ENABLED", "1"):
        print("Prune: disabled (PRUNE_ENABLED=0)")
        return {"pruned": 0, "candidates": 0}

    days = env_int("PRUNE_AFTER_DAYS", 30)
    max_per_run = env_int("PRUNE_MAX_PER_RUN", 1500)
    budget = env_int("PRUNE_TIME_BUDGET_SECONDS", 600)
    dry_run = env_flag("PRUNE_DRY_RUN", "0")

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    started = time.monotonic()
    filt = build_filter(cutoff)

    print(f"Prune: rows created before {cutoff.date()} with Keep unchecked "
          f"({'DRY RUN' if dry_run else f'cap {max_per_run}, budget {budget}s'})")

    pruned = 0
    candidates = 0
    samples = []
    cursor = None

    while True:
        kwargs = {"data_source_id": data_source_id, "filter": filt, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = notion.data_sources.query(**kwargs)
        rows = response.get("results", [])

        pruned_before_page = pruned
        for row in rows:
            if not should_prune(row, cutoff):
                continue
            candidates += 1
            if dry_run:
                if len(samples) < 5:
                    samples.append((row.get("created_time", "")[:10], row_title(row)))
                continue
            if pruned >= max_per_run or time.monotonic() - started > budget:
                break
            archive_with_retry(notion, row["id"])
            pruned += 1
            sleep(0.35)  # stay under Notion's ~3 requests per second average

        stop = (not dry_run) and (pruned >= max_per_run or time.monotonic() - started > budget)
        # A live page that archived nothing would repeat forever; stop instead.
        stalled = (not dry_run) and pruned == pruned_before_page
        if stop or stalled or not response.get("has_more"):
            break
        # In a live run the archived rows drop out of the query, so restart from the
        # top; in a dry run nothing changes, so page through with the cursor.
        cursor = response.get("next_cursor") if dry_run else None

    if dry_run:
        print(f"Prune (dry run): {candidates} rows would be moved to the trash")
        for created, title in samples:
            print(f"  e.g. {created}  {title[:80]}")
    else:
        print(f"Prune: moved {pruned} rows to the trash")
        if pruned >= max_per_run or time.monotonic() - started > budget:
            print("Prune: stopped at the per-run limit; the rest goes next run")
    return {"pruned": pruned, "candidates": candidates}


if __name__ == "__main__":
    from dotenv import load_dotenv
    from notion_client import Client

    load_dotenv()
    if "--dry-run" in sys.argv:
        os.environ["PRUNE_DRY_RUN"] = "1"
    client = Client(auth=os.environ["NOTION_TOKEN"])
    run_prune(client, os.environ["CONTENT_INBOX_DATA_SOURCE_ID"])
