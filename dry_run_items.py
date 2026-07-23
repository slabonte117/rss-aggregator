import os
from datetime import datetime, timedelta, timezone
from time import mktime
from dotenv import load_dotenv
from notion_client import Client
import feedparser

load_dotenv()

notion = Client(auth=os.environ["NOTION_TOKEN"])
feed_sources_id = os.environ["FEED_SOURCES_DATA_SOURCE_ID"]
cutoff = datetime.now(timezone.utc) - timedelta(days=7)

response = notion.data_sources.query(data_source_id=feed_sources_id)

for row in response["results"]:
    props = row["properties"]
    name = "".join(t["plain_text"] for t in props["Feed"]["title"]) or "(untitled)"
    feed_url = props["Feed URL"]["url"]
    keyword_text = props["Keyword Filter"]["rich_text"]
    keywords = [kw.strip().lower() for kw in "".join(t["plain_text"] for t in keyword_text).split(",") if kw.strip()] if keyword_text else []

    parsed = feedparser.parse(feed_url)
    kept, skipped_old, skipped_keyword = 0, 0, 0

    print(f"\n=== {name} (keywords: {keywords or 'none'}) ===")
    for entry in parsed.entries:
        published_parsed = entry.get("published_parsed")
        if published_parsed:
            published_dt = datetime.fromtimestamp(mktime(published_parsed), tz=timezone.utc)
            if published_dt < cutoff:
                skipped_old += 1
                continue

        title = entry.get("title", "(no title)")
        if keywords and not any(kw in title.lower() for kw in keywords):
            skipped_keyword += 1
            continue

        kept += 1
        print(f"  - {title}")

    print(f"  kept={kept} skipped_old={skipped_old} skipped_keyword={skipped_keyword}")
