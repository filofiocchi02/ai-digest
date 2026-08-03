#!/usr/bin/env python3
"""
Daily LLM / Agentic AI digest.
Fetches candidate items for three categories (Research, News, Learning Pills),
asks a free LLM (Groq) to pick and summarize the best ones, and renders a
single HTML page with one section per category plus "Expand in Claude" links.

Env vars required (set as GitHub Actions secrets):
  GROQ_API_KEY        - free key from https://console.groq.com
Optional (for Telegram push notification / custom domain):
   TELEGRAM_BOT_TOKEN
   TELEGRAM_CHAT_ID
   PAGES_URL           - e.g. https://filofiocchi02.github.io/ai-digest/
"""

import os
import json
import html
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


def render_html(sections, date_str, archive_link=True, archive_back_link=False):
    css = """
    body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:760px;
         margin:40px auto;padding:0 16px;color:#1a1a1a;line-height:1.5}
    h1{font-size:1.6em;margin-bottom:0}
    .date{color:#888;margin-bottom:4px}
    .archive-link{font-size:0.85em;margin-bottom:28px}
    .archive-link a{color:#666}
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
    if archive_back_link:
        parts.append("<div class='archive-link'><a href='./'>← Back to archive</a></div>")
    parts.append(f"<h1>🧠 Daily LLM / Agentic AI Digest</h1><div class='date'>{date_str}</div>")
    if archive_link:
        parts.append("<div class='archive-link'><a href='archive/'>📂 Browse past digests</a></div>")

    for section_title, items in sections.items():
        parts.append(f"<h2>{section_title}</h2>")
        if not items:
            parts.append("<p><i>No items today.</i></p>")
            continue
        for it in items:
            title = html.escape(it["title"])
            summary = html.escape(it.get("summary", ""))
            source = html.escape(it.get("source", ""))
            url = html.escape(it["url"])
            link = claude_deeplink(it["title"], it["url"])
            parts.append(
                "<div class='item'>"
                f"<div class='title'><a href='{url}' target='_blank'>{title}</a></div>"
                f"<div class='summary'>{summary}</div>"
                f"<div class='meta'>{source} · "
                f"<a class='expand' href='{link}'>Expand in Claude ↗</a></div>"
                "</div>"
            )
    parts.append("</body></html>")
    return "\n".join(parts)


def render_archive_index(archive_dir):
    """Scan docs/archive/*.html and build an index.html listing them all,
    newest first, so the archive is browsable instead of requiring a
    guessed URL."""
    dated_files = sorted(
        (f for f in os.listdir(archive_dir)
         if f.endswith(".html") and f != "index.html"),
        reverse=True,  # newest date first (filenames are YYYY-MM-DD.html)
    )

    css = """
    body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;
         margin:40px auto;padding:0 16px;color:#1a1a1a;line-height:1.6}
    h1{font-size:1.4em}
    a.back{font-size:0.85em;color:#666}
    ul{list-style:none;padding:0}
    li{padding:8px 0;border-bottom:1px solid #eee}
    li a{text-decoration:none;color:#1a1a1a;font-weight:500}
    li a:hover{text-decoration:underline}
    """
    parts = [
        "<html><head><meta charset='utf-8'><title>Digest Archive</title>"
        f"<style>{css}</style></head><body>",
        "<a class='back' href='../'>← Back to today's digest</a>",
        "<h1>📂 Digest Archive</h1>",
    ]

    if not dated_files:
        parts.append("<p><i>No past digests yet — check back tomorrow.</i></p>")
    else:
        parts.append("<ul>")
        for fname in dated_files:
            date_label = fname.replace(".html", "")
            parts.append(f"<li><a href='{fname}'>{date_label}</a></li>")
        parts.append("</ul>")

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

    # Also keep a dated archive copy, plus a browsable index of all of them
    archive_dir = os.path.join(OUTPUT_DIR, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    with open(os.path.join(archive_dir, f"{date_str}.html"), "w") as f:
        f.write(render_html(sections, date_str, archive_link=False, archive_back_link=True))

    with open(os.path.join(archive_dir, "index.html"), "w") as f:
        f.write(render_archive_index(archive_dir))

    print(f"Wrote digest with "
          f"{sum(len(v) for v in sections.values())} items to {out_path}")

    notify_telegram(date_str, sections)


TELEGRAM_ITEMS_PER_SECTION = 3  # how many headlines to show per category in the ping


def get_pages_url():
    pages_url = os.environ.get("PAGES_URL", "").strip()
    if pages_url:
        return pages_url

    # Automatically derive GitHub Pages URL from standard Actions environment variable
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()  # e.g. owner/repo
    if "/" in gh_repo:
        owner, repo = gh_repo.split("/", 1)
        return f"https://{owner}.github.io/{repo}/"

    return ""


def notify_telegram(date_str, sections):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        return  # optional feature, skip silently if not configured

    pages_url = get_pages_url()

    lines = [f"🧠 <b>LLM Digest — {html.escape(date_str)}</b>\n"]

    for section_title, items in sections.items():
        if not items:
            continue
        lines.append(f"<b>{html.escape(section_title)}</b>")
        for it in items[:TELEGRAM_ITEMS_PER_SECTION]:
            title = html.escape(it.get("title", "").strip())
            lines.append(f"• {title}")
        remaining = len(items) - TELEGRAM_ITEMS_PER_SECTION
        if remaining > 0:
            lines.append(f"  <i>…+{remaining} more</i>")
        lines.append("")  # blank line between sections

    if pages_url:
        lines.append(f'Full digest → <a href="{html.escape(pages_url)}">{html.escape(pages_url)}</a>')

    text = "\n".join(lines).strip()

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"Warning: Failed to send Telegram notification: {e}")


if __name__ == "__main__":
    main()