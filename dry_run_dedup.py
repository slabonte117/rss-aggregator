import os
import sqlite3
from datetime import datetime, timedelta, timezone
from time import mktime
from dotenv import load_dotenv
from notion_client import Client
import feedparser

load_dotenv()

notion = Client(auth=os.environ["NOTION_TOKEN"])
feed_sources_id = os.environ["FEED_SOURCES_DATA_SOURCE_ID"]
content_inbox_id = os.environ["CONTENT_INBOX_DATA_SOURCE_ID"]
cutoff = datetime.now(timezone.utc) - timedelta(days=7)

conn = sqlite3.connect("dedup.db")
conn.execute("""
    CREATE TABLE IF NOT EXISTS feed_cursor (
        feed_url TEXT PRIMARY KEY,
        last_seen_link TEXT,
        last_seen_published TEXT,
        updated_at TEXT
    )
""")
conn.commit()

existing_urls = set()
inbox_response = notion.data_sources.query(data_source_id=content_inbox_id)
for row in inbox_response["results"]:
    url_prop = row["properties"].get("URL", {}).get("url")
    if url_prop:
        existing_urls.add(url_prop)
print(f"Content Inbox currently has {len(existing_urls)} existing URLs\n")

feed_response = notion.data_sources.query(data_source_id=feed_sources_id)
total_would_insert = 0

for row in feed_response["results"]:
    props = row["properties"]
    name = "".join(t["plain_text"] for t in props["Feed"]["title"]) or "(untitled)"
    feed_url = props["Feed URL"]["url"]
    keyword_text = props["Keyword Filter"]["rich_text"]
    keywords = [kw.strip().lower() for kw in "".join(t["plain_text"] for t in keyword_text).split(",") if kw.strip()] if keyword_text else []

    parsed = feedparser.parse(feed_url)
    would_insert = []

    for entry in parsed.entries:
        published_parsed = entry.get("published_parsed")
        if published_parsed:
            published_dt = datetime.fromtimestamp(mktime(published_parsed), tz=timezone.utc)
            if published_dt < cutoff:
                continue

        title = entry.get("title", "(no title)")
        link = entry.get("link", "")

        if keywords and not any(kw in title.lower() for kw in keywords):
            continue
        if link in existing_urls:
            continue

        would_insert.append((title, link))

    print(f"=== {name}: would insert {len(would_insert)} ===")
    for title, link in would_insert:
        print(f"  - {title}")

    total_would_insert += len(would_insert)

conn.close()
print(f"\nTOTAL: would insert {total_would_insert} items into Content Inbox (dry run — nothing written)")
