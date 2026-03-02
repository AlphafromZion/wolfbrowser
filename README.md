# 🐺 wolfbrowser

Stealth browser toolkit for Python. Direct CDP connection, no Selenium, no WebDriver traces.

Built for AI agents that need to browse the real web — not the sanitised version that anti-bot systems let through.

## What It Does

- **Bypasses anti-bot detection** — Cloudflare, Imperva, DataDome, hCaptcha challenges
- **Realistic fingerprints** — randomised screen, GPU, platform, timezone, locale (internally consistent)
- **Human-like interaction** — bezier curve mouse movement, variable typing speed, smooth scrolling
- **Session persistence** — save/load cookies and localStorage across runs
- **Pure CDP** — no Selenium, no chromedriver binary, no WebDriver protocol traces

## Quick Start

```bash
pip install websockets httpx
```

```python
import asyncio
from wolfbrowser import WolfBrowser

async def main():
    async with WolfBrowser(headless=True) as browser:
        tab = await browser.get_tab()
        await tab.goto("https://example.com")
        
        print(await tab.get_title())
        print(await tab.get_text())
        
        # Interact like a human
        await tab.click("Accept Cookies")
        await tab.type_text("#search", "something")
        await tab.scroll("down", 500)
        
        # Screenshot
        await tab.screenshot("page.png", full_page=True)

asyncio.run(main())
```

## CLI

```bash
# Fetch page content with stealth
python -m wolfbrowser.cli fetch "https://example.com" --output text

# Screenshot
python -m wolfbrowser.cli screenshot "https://example.com" -o page.png --full-page

# Extract specific elements
python -m wolfbrowser.cli extract "https://example.com" -s "h1,h2,p" --format json

# Verify stealth is working
python -m wolfbrowser.cli stealth-test
```

## Stealth Test Results

```
Testing bot.sannysoft.com...
  navigator.webdriver: None ✅
  window.chrome: True ✅
  plugins.length: 5 ✅
  languages: en-AU,en ✅
  platform: Win32 ✅

Testing nowsecure.nl (Cloudflare)...
  Title: nowsecure.nl
  Result: ✅ PASSED
```

## Anti-Detection

11 stealth patches applied via CDP before any page JavaScript executes:

| Check | Status |
|-------|--------|
| navigator.webdriver | Hidden |
| window.chrome | Present |
| Plugins array | Populated (5) |
| Languages | Realistic |
| Platform | Matches fingerprint |
| WebGL renderer | Spoofed GPU |
| Screen dimensions | Randomised |
| User-Agent consistency | sec-ch-ua matched |
| Timezone/locale | Matched |
| Function.toString | Native-looking |
| Permissions API | Patched |

## Session Management

Save login state and restore it later:

```python
from wolfbrowser import WolfBrowser, SessionManager

sm = SessionManager()

async with WolfBrowser() as browser:
    tab = await browser.get_tab()
    await tab.goto("https://somesite.com")
    # ... log in ...
    await sm.save_session(tab, "mysite")

# Later
async with WolfBrowser() as browser:
    tab = await browser.get_tab()
    await sm.load_session(tab, "mysite")  # Logged in!
```

## How It Works

1. Launches Chrome with `--disable-blink-features=AutomationControlled` and stealth flags
2. Connects via Chrome DevTools Protocol (CDP) over websocket — no chromedriver needed
3. Injects 11 anti-detection scripts via `Page.addScriptToEvaluateOnNewDocument` (runs before any site JS)
4. Sets User-Agent, timezone, locale via CDP commands (not JS injection)
5. Generates internally consistent fingerprints (GPU matches platform, timezone matches locale, etc.)
6. Human-like interaction via `Input.dispatchMouseEvent` with bezier curves and variable timing

## Requirements

- Python 3.10+
- Chrome or Chromium installed
- `websockets` and `httpx` packages

## License

MIT

---

Built by [@AlphafromZion](https://github.com/AlphafromZion) 🐺
