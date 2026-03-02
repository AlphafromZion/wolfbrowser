# Stealth Browser — Alpha's Web Toolkit

## Problem
Alpha constantly hits walls when browsing the web:
- Cloudflare challenges block automated requests
- Anti-bot fingerprinting detects headless Chrome
- Can't maintain logged-in sessions across platforms
- Can't interact with JS-rendered content (click, scroll, type)
- `web_fetch` is text-only, `browser` tool has limited stealth

## Solution
Build `wolfbrowser` — a stealth browser Python toolkit that lets Alpha browse like a human.

## Architecture

```
wolfbrowser/
├── __init__.py          # Public API
├── browser.py           # Core browser manager (start, stop, sessions)
├── stealth.py           # Anti-detection: fingerprint rotation, CDP patches
├── interaction.py       # Human-like: mouse movement, typing, scrolling
├── session.py           # Persistent sessions: cookies, localStorage, profiles
├── extractor.py         # Page data extraction: text, structured, screenshots
├── cli.py               # CLI interface for quick use
└── profiles/            # Saved browser profiles (cookies, state)
```

## Core Capabilities

### 1. Anti-Detection (stealth.py)
Based on research from nodriver, camoufox, playwright-stealth:
- **No Selenium/WebDriver traces** — direct CDP protocol, no chromedriver binary
- **navigator.webdriver = false** — patch via CDP at page creation
- **Realistic fingerprint** — screen size, platform, plugins, WebGL renderer
- **Randomized fingerprint rotation** — different "device" each session
- **Human-like headers** — realistic User-Agent, Accept-Language, sec-ch-ua
- **Timezone/locale matching** — fingerprint matches claimed location
- **Chrome runtime patches** — window.chrome, Permission.query, etc.

### 2. Human Interaction (interaction.py)
- **Mouse movement** — bezier curve paths, not teleporting
- **Typing** — variable speed, occasional pauses, realistic WPM
- **Scrolling** — smooth scroll with variable speed, not instant jump
- **Click delays** — random micro-delays between actions
- **Tab behavior** — background tab creation, focus switching

### 3. Session Management (session.py)
- **Save/load cookies** — persist login state to JSON
- **Profile directories** — Chrome user data dirs for full state persistence
- **Named sessions** — `wolfbrowser.load("instagram")` restores full logged-in state
- **Session rotation** — switch between profiles for different identities

### 4. Data Extraction (extractor.py)
- **Full page text** — rendered DOM, not raw HTML
- **Structured extraction** — CSS selectors, XPath
- **Screenshots** — full page or element-specific
- **PDF generation** — save pages as PDF
- **Table extraction** — HTML tables to JSON/CSV

### 5. CLI (cli.py)
```bash
# Quick fetch with stealth
python -m wolfbrowser fetch "https://example.com" --output markdown

# Interactive session
python -m wolfbrowser session --profile instagram

# Screenshot
python -m wolfbrowser screenshot "https://example.com" --output page.png

# Extract specific data
python -m wolfbrowser extract "https://example.com" --selector "h1,h2,p"
```

## Technology Choice

**Foundation: `nodriver` (ultrafunkamsterdam)**
- Why: Pure Python, async, CDP-direct (no Selenium), battle-tested against Cloudflare/Imperva
- We don't USE nodriver as a dependency — we study its approach and build our own
- Key insight: CDP (Chrome DevTools Protocol) directly, no chromedriver = no webdriver detection

**Why not the others:**
- `camoufox`: Firefox-based, C++ level patches = can't extend easily, tied to Firefox releases
- `playwright-stealth`: JS injection = detectable by sophisticated WAFs
- `undetected-chromedriver`: Legacy, still uses Selenium underneath

**Our edge: nodriver's CDP approach + our own fingerprint/interaction layers = minimal detection surface**

## Implementation Plan

1. CDP connection layer (talk to Chrome directly via websocket)
2. Stealth patches (run at page creation, before any site JS executes)
3. Fingerprint generator (realistic, randomized per session)
4. Human interaction helpers (mouse, keyboard, scroll)
5. Session persistence (cookie save/load, profile management)
6. Extraction helpers (text, screenshot, structured data)
7. CLI wrapper
8. Integration as OpenClaw skill

## Dependencies
- Chrome/Chromium (already on ZionAlpha via Docker/host)
- `websockets` (CDP communication)
- `aiohttp` or `httpx` (async HTTP for CDP discovery)
- Standard library: `asyncio`, `json`, `pathlib`, `random`, `math`

## Anti-Detection Checklist
Based on bot.sannysoft.com and CreepJS tests:
- [ ] navigator.webdriver = undefined
- [ ] navigator.plugins length > 0
- [ ] navigator.languages populated
- [ ] window.chrome object present
- [ ] Permissions API not leaking
- [ ] WebGL renderer = realistic GPU string
- [ ] Canvas fingerprint varies naturally
- [ ] No `cdc_` markers in DOM
- [ ] User-Agent consistent with sec-ch-ua
- [ ] Screen dimensions match common resolutions
- [ ] Timezone matches locale/geolocation
