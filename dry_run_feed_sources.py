import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

notion = Client(auth=os.environ["NOTION_TOKEN"])
feed_sources_id = os.environ["FEED_SOURCES_DATA_SOURCE_ID"]

response = notion.data_sources.query(data_source_id=feed_sources_id)

print(f"Found {len(response['results'])} rows in Feed Sources\n")

for row in response["results"]:
    props = row["properties"]
    name = "".join(t["plain_text"] for t in props["Feed"]["title"]) or "(untitled)"
    active = props["Active"]["checkbox"]
    feed_url = props["Feed URL"]["url"]
    category = props["Category"]["select"]["name"] if props["Category"]["select"] else "(none)"
    print(f"- {name} | active={active} | category={category} | url={feed_url}")
