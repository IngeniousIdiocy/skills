#!/usr/bin/env python3
import json, sys, os, time

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
UNBOLD = "\x1b[22m"

def fg(n): return f"\x1b[38;5;{n}m"
def bg(n): return f"\x1b[48;5;{n}m"

WHITE = 231
BLACK = 16
MODEL_BG = 24
EFFORT_BG = 54
GREEN = 28
ORANGE = 166
RED = 124
GRAY = 240

SEP = RESET + bg(BLACK) + " " + RESET

def grade_ctx(n):
    if n >= 500_000:
        return RED
    if n >= 250_000:
        return ORANGE
    return GREEN

def grade_pct(p):
    if p >= 80:
        return RED
    if p >= 60:
        return ORANGE
    return GREEN

def fmt(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)

data = json.load(sys.stdin)

model = (data.get("model") or {}).get("display_name", "?")

effort = "?"
try:
    with open(os.path.expanduser("~/.claude/settings.json")) as f:
        effort = json.load(f).get("effortLevel") or "?"
except Exception:
    pass

cw = data.get("context_window") or {}
cu = cw.get("current_usage") or {}
ctx = sum(
    (cu.get(k) or 0)
    for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
)
ctx_max = cw.get("context_window_size") or 200000
ctx_str = f"{fmt(ctx)}/{fmt(ctx_max)}"
ctx_bg = grade_ctx(ctx)

rl = (data.get("rate_limits") or {}).get("five_hour") or {}
pct = rl.get("used_percentage")
resets_at = rl.get("resets_at")
reset_str = ""
if resets_at:
    remaining = int(resets_at - time.time())
    if remaining > 0:
        h = remaining // 3600
        m = (remaining % 3600) // 60
        reset_str = f" \u00b7 {h}h{m:02d}m"
if pct is not None:
    five_str = f"{pct:.0f}% 5h{reset_str}"
    five_bg = grade_pct(pct)
else:
    five_str = f"5h --{reset_str}"
    five_bg = GRAY

segments = [
    (MODEL_BG, f" {BOLD}{model}{UNBOLD} "),
    (EFFORT_BG, f" effort:{effort} "),
    (ctx_bg,    f" {ctx_str} "),
    (five_bg,   f" {five_str} "),
]

out = ""
for i, (color, text) in enumerate(segments):
    out += bg(color) + fg(WHITE) + text + RESET
    if i + 1 < len(segments):
        out += SEP

print(out)
