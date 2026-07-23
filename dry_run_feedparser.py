import os
from dotenv import load_dotenv
from notion_client import Client
import feedparser

load_dotenv()

notion = Client(auth=os.environ["NOTION_TOKEN"])
feed_sources_id = os.environ["FEED_SOURCES_DATA_SOURCE_ID"]

response = notion.data_sources.query(data_source_id=feed_sources_id)

for row in response["results"]:
    props = row["properties"]
    name = "".join(t["plain_text"] for t in props["Feed"]["title"]) or "(untitled)"
    feed_url = props["Feed URL"]["url"]
    parsed = feedparser.parse(feed_url)
    status = getattr(parsed, "status", "n/a")
    if parsed.bozo:
        print(f"- {name}: FAILED status={status} error={parsed.bozo_exception}")
    else:
        print(f"- {name}: OK status={status} entries={len(parsed.entries)}")
