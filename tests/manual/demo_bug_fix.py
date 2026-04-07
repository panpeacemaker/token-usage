import importlib

fetch_usage = importlib.import_module("token_usage.claude.oauth_usage").fetch_usage

u = fetch_usage()
if not u.available:
    print(f"Cannot fetch: {u.error}")
    raise SystemExit(1)

print("AUTHORITATIVE (from /api/oauth/usage):")
print(f"  5-hour:  {u.five_hour_pct:5.1f}%   resets {u.five_hour_resets_at}")
print(f"  7-day:   {u.seven_day_pct:5.1f}%   resets {u.seven_day_resets_at}")
print(f"  subscription: {u.subscription_type} / {u.rate_limit_tier}")
print()
print("Anthropic computes this server-side based on their internal metric.")
print("This is what Claude Code /status displays and what the user sees.")
print("Our old JSONL-based approach was a local approximation and did not match.")
