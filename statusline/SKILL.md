---
name: statusline
description: Install a compact, color-graded Claude Code statusline that shows model, effort level, context-window usage (current/max with green/orange/red threshold coloring), and 5-hour rate-limit usage (percentage + time until reset). Use this skill whenever the user asks to set up, install, restore, customize, or troubleshoot a Claude Code statusline (the bar Claude Code renders at the bottom of the CLI), or mentions wanting to see model/context/rate-limit info in their CLI chrome. Trigger on phrases like "set up my statusline", "install a statusline", "show context usage in the CLI", "show rate-limit usage", "give me back my statusline", "the bar at the bottom", or any request to edit `statusLine` in `~/.claude/settings.json`. Also use proactively when the user has lost or wiped their Claude Code configuration and needs the statusline restored to match their previous setup. Do NOT use this skill for terminal prompt customization (PS1, starship, oh-my-posh) — that is the shell prompt, not the Claude Code statusline.
---

# statusline — Claude Code CLI statusline

## What this skill produces

A single Python script that Claude Code runs on every status refresh. It reads the JSON status payload from stdin, plus `~/.claude/settings.json` for the configured effort level, and prints one colored line with four segments:

```
 [model]  effort:[level]  [ctx_current/ctx_max]  [pct]% 5h · [Hh][MMm]
```

- **Model** — `data.model.display_name`, bold, on a deep-blue background.
- **Effort** — read from `effortLevel` in `~/.claude/settings.json` (`high`, `medium`, `low`, etc.), on a purple background.
- **Context** — sum of `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` from `data.context_window.current_usage`, over `context_window_size` (defaults to 200000 if absent). Background color grades by absolute token count:
  - green   < 250k
  - orange  ≥ 250k
  - red     ≥ 500k
- **5-hour rate limit** — `data.rate_limits.five_hour.used_percentage` and `resets_at` (unix seconds). Shows `NN% 5h · 2h13m`. Background color grades by percent:
  - green   < 60%
  - orange  ≥ 60%
  - red     ≥ 80%
  - gray when the API hasn't reported a number yet

Segments are separated by a single black-background space, so the line looks like contiguous tinted pills.

Numbers > 1M render as `1.23M`, > 1k as `12.3k`.

## When to use this skill

Install or restore this statusline whenever the user:

- Asks to set up, install, or customize a Claude Code statusline.
- Wants context-window usage, rate-limit usage, or current effort visible in the CLI.
- Has reset / wiped `~/.claude/settings.json` and wants their previous statusline back.
- Says "the bar at the bottom" or refers to the line beneath the chat.

Do **not** confuse with shell prompts (`PS1`, starship, oh-my-posh). Those are a separate skill domain — this one is purely about Claude Code's `statusLine` setting.

## Install steps

1. **Copy `statusline.py`** (sibling of this SKILL.md) to `~/.claude/statusline.py` and make it executable:

   ```bash
   cp <skill_dir>/statusline.py ~/.claude/statusline.py
   chmod +x ~/.claude/statusline.py
   ```

2. **Wire it into `~/.claude/settings.json`** by adding (or merging) the `statusLine` key:

   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "~/.claude/statusline.py",
       "refreshInterval": 60
     }
   }
   ```

   `refreshInterval` is in seconds. 60s is a good balance — context/rate-limit values don't change fast enough to need 1s polling, and quicker refreshes flicker.

3. **Set `effortLevel`** in the same `settings.json` if you want the effort segment to read anything other than `?`:

   ```json
   { "effortLevel": "high" }
   ```

4. **Restart Claude Code** (or open a new session). The statusline reads stdin on every refresh, so no daemon, no background process.

## Verifying it works

Pipe a fake payload through the script to confirm it renders:

```bash
echo '{
  "model": {"display_name": "Opus 4.7"},
  "context_window": {
    "context_window_size": 1000000,
    "current_usage": {"input_tokens": 120000, "cache_read_input_tokens": 30000}
  },
  "rate_limits": {"five_hour": {"used_percentage": 42, "resets_at": '"$(($(date +%s)+7200))"'}}
}' | python3 ~/.claude/statusline.py
```

You should see four colored pills with the model name, `effort:<your level>`, `150.0k/1.00M`, and `42% 5h · 2h00m`.

## Customizing

All knobs are constants at the top of `statusline.py`:

- `MODEL_BG`, `EFFORT_BG`, `GREEN`, `ORANGE`, `RED`, `GRAY` — 8-bit ANSI color codes (xterm 256 palette). Change to match your terminal theme.
- `grade_ctx()` thresholds — adjust the 250k / 500k cutoffs if you live on a 200k or 1M context window.
- `grade_pct()` thresholds — adjust the 60% / 80% cutoffs for the 5-hour bar.
- `fmt()` — change number formatting (e.g., always show `k`, drop decimals).
- `SEP` — currently a single black space; swap for `│` or `▏` if you want a visible separator.

## Troubleshooting

- **Statusline shows nothing / blank line**: Claude Code couldn't run the command. Check `chmod +x ~/.claude/statusline.py` and that `#!/usr/bin/env python3` resolves on your `PATH`.
- **Garbled escape codes (`\x1b[...m` visible)**: your terminal doesn't support 256-color ANSI. Either upgrade the terminal or replace `fg()`/`bg()` with 16-color equivalents.
- **`effort:?`**: `effortLevel` key is missing from `~/.claude/settings.json`. Add it, or comment out the effort segment in `segments = [...]`.
- **Context shows `0/200000`**: Claude Code didn't pass a `context_window.current_usage`. This happens at the very start of a session before the first tool call — it'll populate after the first turn.
- **Stale rate-limit info**: `refreshInterval` is the polling cadence. Lower it (e.g., to 30) for snappier updates, but expect more spawned Python processes.
