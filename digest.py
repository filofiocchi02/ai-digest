#!/usr/bin/env python3
"""
Daily LLM / Agentic AI digest.
Fetches candidate items for three categories (Research, News, Learning Pills),
asks a free LLM (Groq) to pick and summarize the best ones, and renders a
single HTML page with one section per category plus "Expand in Claude" links.

Env vars required (set as GitHub Actions secrets):
  GROQ_API_KEY        - free key from https://console.groq.com
Optional (for Telegram push notification):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""

import os
import json
import textwrap
import datetime
import urllib.parse
import requests
import feedparser

# ---------------------------------------------------------------------------
# 1. CONFIG — tune this to taste
# ---------------------------------------------------------------------------

KEYWORDS = [
    "llm", "large language model", "agent", "agentic", "rag",
    "retrieval augmented", "fine-tun", "reasoning model", "alignment",
    "prompt", "transformer", "inference", "context window", "tool use",
    "chain of thought", "mcp", "model context protocol",
]

ARXIV_CATEGORIES = ["cs.CL", "cs.AI", "cs.LG"]
ARXIV_MAX = 40

HN_QUERY = "LLM OR agent OR RAG OR \"language model\""

NEWS_FEEDS = [
    "https://www.anthropic.com/news/rss.xml",
    "https://openai.com/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://blog.google/technology/ai/rss/",
]

LEARNING_FEEDS = [
    "https://simonwillison.net/atom/everything/",
    "https://magazine.sebastianraschka.com/feed",
    "https://www.latent.space/feed",
    "https://www.deeplearning.ai/the-batch/feed/",
    "https://eugeneyan.com/rss/",
]

GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
ITEMS_PER_CATEGORY = 8

OUTPUT_DIR = "docs"  # GitHub Pages serves from /docs on main branch


# ---------------------------------------------------------------------------
# 2. FETCHERS — return list of {title, url, snippet, source}
# ---------------------------------------------------------------------------

def fetch_arxiv():
    items = []
    cat_query = "+OR+".join(f"cat:{c}" for c in ARXIV_CATEGORIES)
    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query=({cat_query})&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={ARXIV_MAX}"
    )
    feed = feedparser.parse(url)
    for e in feed.entries:
        text = (e.title + " " + e.get("summary", "")).lower()
        if any(k in text for k in KEYWORDS):
            items.append({
                "title": e.title.replace("\n", " ").strip(),
                "url": e.link,
                "snippet": e.get("summary", "")[:400].replace("\n", " "),
                "source": "arXiv",
            })
    return items


def fetch_hn():
    items = []
    resp = requests.get(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"query": HN_QUERY, "tags": "story", "hitsPerPage": 30},
        timeout=20,
    )
    resp.raise_for_status()
    for hit in resp.json().get("hits", []):
        if not hit.get("title"):
            continue
        items.append({
            "title": hit["title"],
            "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
            "snippet": f"{hit.get('points', 0)} points, {hit.get('num_comments', 0)} comments on HN",
            "source": "Hacker News",
        })
    return items


def fetch_rss(feeds, label_default=None):
    items = []
    for f in feeds:
        try:
            parsed = feedparser.parse(f)
        except Exception:
            continue
        source_name = parsed.feed.get("title", label_default or f)
        for e in parsed.entries[:8]:
            items.append({
                "title": e.get("title", "").strip(),
                "url": e.get("link", ""),
                "snippet": (e.get("summary", "") or "")[:400].replace("\n", " "),
                "source": source_name,
            })
    return items


# ---------------------------------------------------------------------------
# 3. SUMMARIZE + RANK via Groq (free tier)
# ---------------------------------------------------------------------------

def summarize_category(category_name, candidates):
    if not candidates:
        return []

    api_key = os.environ["GROQ_API_KEY"]
    # Trim candidate list to keep the prompt small
    trimmed = candidates[:35]
    listing = "\n".join(
        f"{i}. [{c['source']}] {c['title']} — {c['snippet'][:200]} ({c['url']})"
        for i, c in enumerate(trimmed)
    )

    prompt = textwrap.dedent(f"""
        You are curating a daily digest for category "{category_name}" about
        LLMs and agentic AI. From the numbered list below, pick the
        {ITEMS_PER_CATEGORY} most interesting, substantive, non-duplicate items.
        Skip pure marketing/spam. Merge near-duplicates.

        Return ONLY valid JSON, a list of objects with keys:
        "title" (clean, <=90 chars), "summary" (1-2 plain sentences, no fluff),
        "url" (copy exactly from the source list), "source".

        List:
        {listing}
    """).strip()

    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]

    # Model may wrap JSON in prose/fences — extract the [...] block
    start = content.find("[")
    end = content.rfind("]")
    try:
        return json.loads(content[start:end + 1])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 4. RENDER HTML
# ---------------------------------------------------------------------------

def claude_deeplink(title, url):
    prompt = (
        f"Expand on this for me: \"{title}\" ({url}). "
        "Give me the key context, why it matters for LLM/agentic AI, "
        "and what to read next."
    )
    return "claude://claude.ai/new?q=" + urllib.parse.quote(prompt)


def render_html(sections, date_str):
    css = """
    body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;
         margin:40px auto;padding:0 16px;color:#1a1a1a;line-height:1.5}
    h1{font-size:1.6em;margin-bottom:0}
    .date{color:#888;margin-bottom:28px}
    h2{border-bottom:2px solid #eee;padding-bottom:6px;margin-top:36px}
    .item{margin-bottom:16px}
    .item .title a{font-weight:600;text-decoration:none;color:#1a1a1a}
    .item .title a:hover{text-decoration:underline}
    .item .summary{color:#444;font-size:0.95em;margin:2px 0}
    .item .meta{font-size:0.8em;color:#999}
    .item .expand{font-size:0.8em}
    """
    parts = [f"<html><head><meta charset='utf-8'><title>LLM Digest {date_str}</title>"
              f"<style>{css}</style></head><body>"]
    parts.append(f"<h1>🧠 Daily LLM / Agentic AI Digest</h1><div class='date'>{date_str}</div>")

    for section_title, items in sections.items():
        parts.append(f"<h2>{section_title}</h2>")
        if not items:
            parts.append("<p><i>No items today.</i></p>")
            continue
        for it in items:
            link = claude_deeplink(it["title"], it["url"])
            parts.append(
                "<div class='item'>"
                f"<div class='title'><a href='{it['url']}' target='_blank'>{it['title']}</a></div>"
                f"<div class='summary'>{it.get('summary', '')}</div>"
                f"<div class='meta'>{it.get('source', '')} · "
                f"<a class='expand' href='{link}'>Expand in Claude ↗</a></div>"
                "</div>"
            )
    parts.append("</body></html>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 5. MAIN
# ---------------------------------------------------------------------------

def main():
    date_str = datetime.date.today().isoformat()

    research_raw = fetch_arxiv()
    news_raw = fetch_hn() + fetch_rss(NEWS_FEEDS)
    pills_raw = fetch_rss(LEARNING_FEEDS)

    sections = {
        "📚 Research": summarize_category("Research", research_raw),
        "📰 News": summarize_category("News", news_raw),
        "💊 Learning Pills": summarize_category("Learning Pills", pills_raw),
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    html = render_html(sections, date_str)
    out_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(out_path, "w") as f:
        f.write(html)

    # Also keep a dated archive copy (optional, nice to have)
    archive_dir = os.path.join(OUTPUT_DIR, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    with open(os.path.join(archive_dir, f"{date_str}.html"), "w") as f:
        f.write(html)

    print(f"Wrote digest with "
          f"{sum(len(v) for v in sections.values())} items to {out_path}")

    notify_telegram(date_str, sections)


def notify_telegram(date_str, sections):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    pages_url = os.environ.get("PAGES_URL")  # e.g. https://you.github.io/llm-digest/
    if not (token and chat_id):
        return  # optional feature, skip silently if not configured

    counts = " · ".join(f"{k}: {len(v)}" for k, v in sections.items())
    text = f"🧠 LLM Digest — {date_str}\n{counts}"
    if pages_url:
        text += f"\n{pages_url}"

    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=20,
    )


if __name__ == "__main__":
    main()
