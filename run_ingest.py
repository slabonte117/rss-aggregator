import os
import re
import html
from datetime import datetime, timedelta, timezone
from time import mktime
from urllib.parse import urlparse
from dotenv import load_dotenv
from notion_client import Client
import feedparser
import trafilatura
from trafilatura.settings import use_config

load_dotenv()

notion = Client(auth=os.environ["NOTION_TOKEN"])
feed_sources_id = os.environ["FEED_SOURCES_DATA_SOURCE_ID"]
content_inbox_id = os.environ["CONTENT_INBOX_DATA_SOURCE_ID"]
cutoff = datetime.now(timezone.utc) - timedelta(days=7)
TRAFILATURA_CONFIG = use_config(filename="trafilatura_settings.cfg")

SOURCE_MAP = {
    "BBC News": "BBC News",
    "NPR": "NPR",
    "The Guardian": "The Guardian",
    "The New York Times": "The New York Times",
    "Ars Technica": "Ars Technica",
    "MIT Technology Review": "MIT Technology Review",
}

PAYWALLED_DOMAINS = {
    "nytimes.com",
    "theguardian.com",
    "bbc.com",
    "bbc.co.uk",
}

def resolve_source(feed_name):
    for key, val in SOURCE_MAP.items():
        if feed_name.startswith(key):
            return val
    return feed_name

def clean_snippet(text):
    no_tags = re.sub("<[^<]+?>", "", text or "")
    return html.unescape(no_tags).strip()

def is_paywalled(link):
    domain = urlparse(link).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return any(domain == d or domain.endswith("." + d) for d in PAYWALLED_DOMAINS)

def get_full_text(entry, link):
    content_field = entry.get("content")
    if content_field:
        feed_text = clean_snippet(content_field[0].get("value", ""))
        if len(feed_text) > 600:
            return feed_text
    if is_paywalled(link):
        return None
    try:
        downloaded = trafilatura.fetch_url(link, config=TRAFILATURA_CONFIG)
        if downloaded:
            extracted = trafilatura.extract(downloaded, config=TRAFILATURA_CONFIG)
            if extracted and len(extracted) > 200:
                return extracted
    except Exception:
        pass
    return None

def text_to_blocks(text, max_blocks=95):
    blocks = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        for i in range(0, len(para), 2000):
            if len(blocks) >= max_blocks:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": "[Content truncated]"}}]},
                })
                return blocks
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": para[i:i + 2000]}}]},
            })
    return blocks

existing_urls = set()
cursor = None
while True:
    kwargs = {"data_source_id": content_inbox_id}
    if cursor:
        kwargs["start_cursor"] = cursor
    response = notion.data_sources.query(**kwargs)
    for row in response["results"]:
        url_prop = row["properties"].get("URL", {}).get("url")
        if url_prop:
            existing_urls.add(url_prop)
    if response.get("has_more"):
        cursor = response.get("next_cursor")
    else:
        break
print(f"Content Inbox currently has {len(existing_urls)} existing URLs")

feed_response = notion.data_sources.query(data_source_id=feed_sources_id)

total_created, total_errors = 0, 0

for row in feed_response["results"]:
    props = row["properties"]
    name = "".join(t["plain_text"] for t in props["Feed"]["title"]) or "(untitled)"
    feed_url = props["Feed URL"]["url"]
    category = props["Category"]["select"]["name"] if props["Category"]["select"] else None
    keyword_text = props["Keyword Filter"]["rich_text"]
    keywords = [kw.strip().lower() for kw in "".join(t["plain_text"] for t in keyword_text).split(",") if kw.strip()] if keyword_text else []
    source_name = resolve_source(name)

    parsed = feedparser.parse(feed_url)
    created, errors = 0, 0

    for entry in parsed.entries:
        published_dt = None
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

        snippet = clean_snippet(entry.get("summary", ""))[:500]
        full_text = get_full_text(entry, link)
        children = text_to_blocks(full_text) if full_text else None

        properties = {
            "Title": {"title": [{"text": {"content": title[:2000]}}]},
            "URL": {"url": link},
            "Snippet": {"rich_text": [{"text": {"content": snippet}}]},
            "Status": {"select": {"name": "New"}},
            "Source": {"select": {"name": source_name}},
        }
        if category:
            properties["Category"] = {"select": {"name": category}}
        if published_dt:
            properties["Published"] = {"date": {"start": published_dt.isoformat()}}

        try:
            create_kwargs = {
                "parent": {"type": "data_source_id", "data_source_id": content_inbox_id},
                "properties": properties,
            }
            if children:
                create_kwargs["children"] = children
            notion.pages.create(**create_kwargs)
            created += 1
            existing_urls.add(link)
        except Exception as e:
            errors += 1
            print(f"  ERROR creating '{title}': {e}")

    print(f"{name}: created={created} errors={errors}")
    total_created += created
    total_errors += errors

    status_text = "OK" if errors == 0 else f"{errors} error(s)"
    try:
        notion.pages.update(
            page_id=row["id"],
            properties={
                "Last Checked": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
                "Last Status": {"rich_text": [{"text": {"content": status_text}}]},
            },
        )
    except Exception as e:
        print(f"  WARNING: could not write feed health for {name}: {e}")

print(f"\nTOTAL: created={total_created} errors={total_errors}")
