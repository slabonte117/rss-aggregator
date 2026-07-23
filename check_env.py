import os
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get("NOTION_TOKEN", "")
feed_id = os.environ.get("FEED_SOURCES_DATA_SOURCE_ID", "")
inbox_id = os.environ.get("CONTENT_INBOX_DATA_SOURCE_ID", "")

print("NOTION_TOKEN loaded:", bool(token))
print("FEED_SOURCES_DATA_SOURCE_ID:", feed_id or "MISSING")
print("CONTENT_INBOX_DATA_SOURCE_ID:", inbox_id or "MISSING")
