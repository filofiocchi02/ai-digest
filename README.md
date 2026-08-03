# Daily LLM / Agentic AI Digest — free, self-hosted

Pulls fresh **Research** (arXiv), **News** (Hacker News + a few lab blogs), and
**Learning Pills** (curated technical blogs), asks a free LLM to pick and
summarize the best of each into one page per category, publishes it as a
static page, and (optionally) pings you on Telegram. Runs on a daily cron via
GitHub Actions — no server, no paid tier.

## 1. Create the repo

1. Create a **public** GitHub repo (public repos get unlimited free Actions
   minutes; private repos get 2,000 free min/month, which is still plenty for
   one run a day).
2. Push these files (`digest.py`, `requirements.txt`, `.github/workflows/digest.yml`, this README).

## 2. Get a free Groq API key (for summarization)

1. Go to https://console.groq.com → sign up (free) → "API Keys" → create one.
2. In your repo: **Settings → Secrets and variables → Actions → New repository secret**
   → name `GROQ_API_KEY`, paste the key.

Groq's free tier easily covers 3 calls/day. If you'd rather use Google's
Gemini free tier instead, swap the `summarize_category()` HTTP call for
Gemini's `generateContent` endpoint — same idea, different URL/payload.

## 3. (Optional) Set up Telegram push notifications

1. Message **@BotFather** on Telegram → `/newbot` → follow prompts → you get a
   bot token.
2. Message your new bot once (anything), then visit
   `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser to find your
   `chat.id`.
3. Add two more repo secrets: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

Skip this step if you're happy just bookmarking the GitHub Pages URL.

## 4. Turn on GitHub Pages

1. **Settings → Pages** → Source: "Deploy from a branch" → Branch: `main`,
   folder: `/docs`. Save.
2. GitHub gives you a URL like `https://<you>.github.io/<repo>/`. Optionally
   add it as a repo **variable** (not secret) named `PAGES_URL` so it gets
   included in the Telegram message.

## 5. Schedule

The workflow (`.github/workflows/digest.yml`) already runs daily at
06:30 UTC via `cron: "30 6 * * *"`. Edit that line for a different time —
cron is always in UTC, so offset for your local time. You can also trigger a
run manually any time from the **Actions** tab (`workflow_dispatch`).

## 6. "Expand in Claude" links

Each item includes an `Expand in Claude ↗` link built from a
`claude://claude.ai/new?q=...` deep link. If you have **Claude Desktop or the
Claude mobile app installed**, clicking it opens a new chat with a
pre-filled prompt to expand on that item — no copy/paste needed.

Note: the old `claude.ai/new?q=...` **web browser** shortcut was removed by
Anthropic in Oct 2025, so on a browser with no app installed the link won't
autofill anything. For that case, each item's title/URL is right there for
you to paste manually, or you can extend `render_html()` to add a "copy
prompt" button (`navigator.clipboard.writeText(...)`) as a one-click
fallback.

## Tuning

- `KEYWORDS` — filters arXiv/HN by relevance.
- `NEWS_FEEDS` / `LEARNING_FEEDS` — add/remove RSS sources freely (any blog
  with an RSS/Atom feed works).
- `ITEMS_PER_CATEGORY` — how many items make the final cut per section
  (8 keeps each section to roughly one page).
- `GROQ_MODEL` — swap for any other Groq-hosted free model if you like.

## Costs

Everything here is free at this scale: GitHub Actions (public repo, 1
run/day), GitHub Pages, Groq's free API tier, Telegram bots, and all the RSS
feeds/APIs. If you outgrow Groq's free rate limits, Google AI Studio's Gemini
Flash free tier is a solid alternative with similarly generous limits.
