import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()
notion = Client(auth=os.environ["NOTION_TOKEN"])
content_inbox_id = os.environ["CONTENT_INBOX_DATA_SOURCE_ID"]

seen = {}
duplicates = []
cursor = None

while True:
    kwargs = {"data_source_id": content_inbox_id}
    if cursor:
        kwargs["start_cursor"] = cursor
    response = notion.data_sources.query(**kwargs)
    for row in response["results"]:
        url_prop = row["properties"].get("URL", {}).get("url")
        if not url_prop:
            continue
        if url_prop in seen:
            duplicates.append(row["id"])
        else:
            seen[url_prop] = row["id"]
    if response.get("has_more"):
        cursor = response.get("next_cursor")
    else:
        break

print(f"Total unique URLs: {len(seen)}")
print(f"Duplicate pages to archive: {len(duplicates)}")

for page_id in duplicates:
    notion.pages.update(page_id=page_id, archived=True)

print(f"Archived {len(duplicates)} duplicate pages.")
