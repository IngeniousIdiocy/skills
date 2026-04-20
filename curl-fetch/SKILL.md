---
name: curl-fetch
description: Retrieve web page content via Bash curl from the user's local/residential IP whenever Claude Code's WebFetch tool returns 403, 401, 429, 503, Cloudflare challenge, Anubis block, empty body, or "I don't have any web page content to review". Claude Code's WebFetch goes through Anthropic's datacenter IPs, which many bot-protection layers block; curl from the user's machine uses a residential IP that passes cleanly. Also use when the user says "curl it", "try curl", "fetch it directly", "get the raw HTML", or when you need the full content of a specific URL that WebSearch only shows as a snippet. Trigger on known bot-protected hosts even before WebFetch fails: wiki.archlinux.org, r.obin.ch, gpd.hk, gpdstore.net, gpd-minipc.com, device.report, and most vendor/shop/manual sites. Prefer this skill over giving up, escalating to Gemini, or asking the user to fetch the page themselves.
---

# curl-fetch — WebFetch fallback via local curl

## Why this skill exists

Claude Code's built-in `WebFetch` tool runs on Anthropic's infrastructure. Cloudflare, Anubis, and other bot-protection layers routinely block datacenter IPs, so `WebFetch` returns 403, empty bodies, or challenge pages on a lot of vendor/product/wiki/blog sites.

A plain `curl` call from the Bash tool runs **on the user's machine**, from their **residential IP**, with a browser-ish `User-Agent`. That combination passes through almost all bot protection cleanly, typically in under a second. No third-party services, no OAuth, no latency, no auto-approval footguns.

This skill is the minimum viable fix: shell out to curl, get the HTML, extract what you need.

## When to trigger

Use this skill any time **any** of the following happen:

- `WebFetch` returned `Request failed with status code 403` (also 401, 429, 503 with Cloudflare/Anubis branding).
- `WebFetch` returned empty content / "I don't have any web page content to review".
- `WebSearch` returned only snippets and you need the full content of a specific result.
- The user says "curl it", "try curl", "fetch it directly", "just get the raw HTML", "bypass the block".
- The URL host is a known bot-protected site (see list below) — try this first, don't waste a WebFetch call.

**Known bot-protected hosts** (use curl first, skip WebFetch):
- `wiki.archlinux.org` (Anubis)
- `r.obin.ch` (Anubis)
- `gpd.hk`, `gpdstore.net`, `gpd-minipc.com` (Cloudflare)
- `device.report` (Cloudflare)
- Most vendor storefronts, product spec pages, and small-operator blogs

Do **not** use this skill for:

- Pages behind login/paywall — curl won't authenticate for you.
- Simple searches where `WebSearch` is already working — don't overcomplicate.

For JS-rendered SPAs where curl gets an empty shell, see the **JS-rendered fallback** section at the end.

## Canonical flow — always the same three steps

Never pollute main context with raw HTML. Always: **fetch → convert → delegate**.

### Step 1: fetch with curl (save to disk)

```bash
curl -sL --max-time 20 --compressed \
  -A 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/128.0' \
  -o /tmp/page.html \
  -w 'HTTP %{http_code}  size=%{size_download}\n' \
  'URL'
```

Flags:
- `-s -L` — silent, follow redirects.
- `--max-time 20` — bot-protected sites answer fast or hang; don't wait forever.
- `--compressed` — auto-decode gzip/br responses; harmless on uncompressed pages.
- `-A '<browser UA>'` — many filters 403 curl's default UA. Any recent Firefox/Chrome string works.
- `-o /tmp/page.html` — save to disk, always.
- `-w '...'` — print status code + size on stderr-ish; gives you a quick sanity check that the fetch actually worked and didn't land on a challenge page.

If `size` is under ~5KB and HTTP is 200, grep the file for `cf-chl` or `Anubis` — you may have been handed a challenge page instead of the content. Re-check UA.

### Step 2: convert to plain text with pandoc

```bash
pandoc -f html -t plain -o /tmp/page.txt /tmp/page.html
```

`pandoc` is already installed. Plain text is ~3–10x smaller than the source HTML, strips all the nav/script/style noise, and is trivially readable by a subagent. Do this for **every** page, regardless of size — the extra step is ~50ms and keeps downstream extraction consistent.

### Step 3: dispatch an Explore subagent against the text file

```
Agent({
  subagent_type: "Explore",
  model: "haiku",          // or "sonnet" if haiku misses structure
  description: "<short task description>",
  prompt: "Read /tmp/page.txt. Extract <specific detail>. Quote
           verbatim where possible. If the file does not mention
           <detail>, say so explicitly. Report under 200 words."
})
```

Key points:
- **Always pass `model: "haiku"` for simple extraction** (finding a quote, a spec number, a config block). Haiku 4.5 handles this fine and costs a fraction of Opus. Upgrade to `sonnet` only if haiku gives a weak answer. Never let Explore default to the parent model (Opus 4.7 for this session) on grunt-work extraction.
- Keep the prompt narrow and bounded (`under 200 words`, `quote verbatim`, `if not found, say so`) — same discipline you'd use with any subagent.
- The subagent's context window absorbs the text; yours stays clean.
- Run multiple fetches in parallel when you have multiple URLs — one `Bash` call per fetch, one `Agent` call per extraction, all in a single message.

### Why this pattern is the default, not an option

Reading raw HTML into main context is almost never correct:
- Even "small" pages (50KB) eat a surprising amount of context once tokenized.
- HTML is ~80% structural noise; only the text carries information you need.
- The subagent costs one extra tool round-trip but buys you a clean, summarized result that's safe to keep in context long-term.
- Using `haiku` on the subagent makes this cheaper than a grep-and-reread loop in main context.

Only reach for inline `grep` or direct `Read` if you need a single byte-exact string match and you're certain the file is tiny (< 5KB of actual page text).

## Known gotchas

- **Redirects landing on a challenge page**: if the fetch size is ~5–10KB and `grep -E 'cf-chl|Anubis|Just a moment' /tmp/page.html` matches, you got blocked despite the UA. Try a different UA, or escalate to the JS-rendered fallback.
- **Binary / non-HTML responses**: if `file /tmp/page.html` says PDF/image/etc., skip pandoc and use the appropriate skill (`document-skills:pdf`, etc.).
- **Rate limiting**: keep fetches under ~10/min to the same host. `--max-time 20` prevents runaway hangs.

## JS-rendered fallback — when curl returns an empty shell

If `/tmp/page.html` is short (often < 2KB) and contains text like "Please enable JavaScript" or just a mostly-empty `<body>`, the content requires JS execution. curl can't help. In rough order of cost:

1. **Try WebFetch once** — Anthropic's fetcher can render some JS. Ironic fallback direction, but sometimes works.
2. **Gemini CLI** — `gemini -p 'fetch <URL>, extract <detail>'` routes through Gemini API's `urlContext`, which is a cloud-side Chromium-style fetcher that *does* render JS. When the primary path succeeds (i.e. **not** the local-fallback path), it returns rendered content. This is Gemini's only remaining value vs. plain curl.
   ```bash
   export PATH="$HOME/.local/lib/npm-global/bin:$PATH"
   gemini -p 'Fetch <URL>. Extract <detail>. Quote verbatim. If the page does not mention it, say so.' --yolo 2>&1 | tail -40
   ```
   Caveats: ~30s latency, requires Google OAuth (already set up), `--yolo` auto-approves all Gemini tool calls — don't extend this flow to non-fetch tasks without rethinking.
3. **Playwright via `document-skills:webapp-testing`** — real browser, full JS execution. Heaviest option; use only when (1) and (2) both fail, typically on complex SPAs.

If none of these work, stop and tell the user the URL needs a real browser session (cookies, login, or aggressive bot-blocking) that this skill can't solve.

## One-line recipe (copy this)

When you need `<detail>` from `<URL>`:

```bash
curl -sL --max-time 20 --compressed -A 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/128.0' -o /tmp/page.html -w 'HTTP %{http_code}  size=%{size_download}\n' '<URL>' && pandoc -f html -t plain -o /tmp/page.txt /tmp/page.html && wc -l /tmp/page.txt
```

Then `Agent({ subagent_type: "Explore", model: "haiku", prompt: "Read /tmp/page.txt. Extract <detail>. ..." })`. Cite the URL when you report back.

## Performance notes

Empirical test on an Anubis-blocked Arch Wiki URL:
- `WebFetch`: 403 / no content.
- `curl` from this machine: ~1s, HTTP 200, full content.
- `gemini -p 'fetch ...'`: ~30s, succeeds via its local-fallback path (which is itself a curl from this machine — so for static HTML, Gemini is just curl-with-extra-steps).

So: curl + pandoc + Explore-on-haiku is the default for static pages. Gemini only earns its keep on JS-rendered pages where its cloud-side primary path (not its local fallback) succeeds.
