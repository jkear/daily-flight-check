# GNV Daily Flight Check

Automated Uber driving briefer for Gainesville Regional Airport (KGNV/GNV).

## Data Source

**FlightAware AeroAPI** (`aeroapi.flightaware.com`)  
Structured REST API — no scraping, no JS rendering, reliable for US regional airports.

### Required configuration (one-time setup)

1. **Egress allowlist** — add `aeroapi.flightaware.com` in your Claude Code on the web
   session network settings (Settings → Environment → Network egress allowlist).

2. **API key** — register for a free account at https://www.flightaware.com/aeroapi/portal/
   Free tier: 500 requests/month (a daily briefing uses 1-2).
   Set the key as an environment variable named `AEROAPI_KEY` in your session settings.

## How to run a briefing

```bash
python3 fetch_arrivals.py
```

The script outputs plain-text briefing to stdout. Capture it and send via Gmail MCP.

## Callsigns tracked

| Code | Airline             | Aircraft     | Seats | Hub      |
|------|---------------------|--------------|-------|----------|
| DAL  | Delta mainline      | B717         | ~110  | ATL      |
| EDV  | Endeavor (Delta Cx) | CRJ-9        | ~76   | ATL      |
| PDT  | Piedmont (AA Eagle) | E145         | ~50   | CLT      |
| ENY  | Envoy (AA Eagle)    | E170 / E75L  | ~70-76| DFW/MIA  |

## Email

Send briefing to `jordankearfott@gmail.com` via Gmail MCP tool.  
Subject: `GNV Briefing — <DATE> (<STATUS>)` where STATUS is one of:
- `✓ On Time`
- `⚠ Delays`  
- `⚠ Cancellations`

## Fallback if AeroAPI is unavailable

If `AEROAPI_KEY` is missing or the API call fails, emit a failure notice and
send it via Gmail MCP with subject `GNV Briefing — <DATE> (⚠ FAILED — No Data)`.
Do NOT fabricate flight schedules.
