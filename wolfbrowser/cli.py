"""
CLI interface for wolfbrowser.
Quick stealth browsing from the command line.
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path

from .browser import WolfBrowser
from .stealth import generate_fingerprint
from .session import SessionManager


async def cmd_fetch(args):
    """Fetch a page and output text/html."""
    config = generate_fingerprint()
    async with WolfBrowser(headless=True, stealth_config=config) as browser:
        tab = await browser.get_tab()
        await tab.goto(args.url)
        await asyncio.sleep(args.wait)
        
        if args.output == "text":
            print(await tab.get_text())
        elif args.output == "html":
            print(await tab.get_html())
        elif args.output == "title":
            print(await tab.get_title())
        elif args.output == "json":
            data = {
                "url": await tab.get_url(),
                "title": await tab.get_title(),
                "text": await tab.get_text(),
            }
            print(json.dumps(data, indent=2))


async def cmd_screenshot(args):
    """Take a screenshot of a page."""
    config = generate_fingerprint()
    async with WolfBrowser(headless=True, stealth_config=config) as browser:
        tab = await browser.get_tab()
        await tab.goto(args.url)
        await asyncio.sleep(args.wait)
        
        output = args.output or "screenshot.png"
        await tab.screenshot(path=output, full_page=args.full_page)
        print(f"Screenshot saved: {output}")


async def cmd_extract(args):
    """Extract specific elements from a page."""
    config = generate_fingerprint()
    async with WolfBrowser(headless=True, stealth_config=config) as browser:
        tab = await browser.get_tab()
        await tab.goto(args.url)
        await asyncio.sleep(args.wait)
        
        elements = await tab.select(args.selector)
        if args.format == "json":
            print(json.dumps(elements, indent=2))
        else:
            for el in elements:
                text = el.get("text", "").strip()
                if text:
                    print(f"[{el['tag']}] {text[:200]}")


async def cmd_stealth_test(args):
    """Run bot detection tests to verify stealth is working."""
    config = generate_fingerprint()
    print(f"Fingerprint: {config.platform} / Chrome {config.chrome_version} / {config.screen_width}x{config.screen_height}")
    print(f"GPU: {config.webgl_renderer}")
    print(f"Timezone: {config.timezone} / Locale: {config.locale}")
    print()
    
    async with WolfBrowser(headless=True, stealth_config=config) as browser:
        tab = await browser.get_tab()
        
        # Test 1: bot.sannysoft.com
        print("Testing bot.sannysoft.com...")
        await tab.goto("https://bot.sannysoft.com")
        await asyncio.sleep(3)
        
        # Check key indicators
        webdriver = await tab.evaluate("navigator.webdriver")
        chrome = await tab.evaluate("!!window.chrome")
        plugins = await tab.evaluate("navigator.plugins.length")
        languages = await tab.evaluate("navigator.languages.join(',')")
        platform = await tab.evaluate("navigator.platform")
        
        print(f"  navigator.webdriver: {webdriver} {'✅' if not webdriver else '❌'}")
        print(f"  window.chrome: {chrome} {'✅' if chrome else '❌'}")
        print(f"  plugins.length: {plugins} {'✅' if plugins > 0 else '❌'}")
        print(f"  languages: {languages} {'✅' if languages else '❌'}")
        print(f"  platform: {platform} {'✅' if platform else '❌'}")
        
        if args.screenshot:
            await tab.screenshot(path="stealth_test.png", full_page=True)
            print(f"\n  Screenshot: stealth_test.png")
        
        # Test 2: nowsecure.nl (Cloudflare challenge)
        print("\nTesting nowsecure.nl (Cloudflare)...")
        await tab.goto("https://www.nowsecure.nl")
        await asyncio.sleep(5)
        title = await tab.get_title()
        url = await tab.get_url()
        passed = "nowsecure" in title.lower() or "passed" in (await tab.get_text()).lower()
        print(f"  Title: {title}")
        print(f"  Result: {'✅ PASSED' if passed else '⚠️ May need more work'}")


async def cmd_sessions(args):
    """Manage saved sessions."""
    sm = SessionManager()
    
    if args.subcmd == "list":
        sessions = sm.list_sessions()
        if not sessions:
            print("No saved sessions.")
        for name in sessions:
            info = sm.get_session_info(name)
            print(f"  {name}: {info['url']} ({info['cookie_count']} cookies, saved {info['saved_at']})")
    
    elif args.subcmd == "delete":
        if sm.delete_session(args.name):
            print(f"Deleted session: {args.name}")
        else:
            print(f"Session not found: {args.name}")


def main():
    parser = argparse.ArgumentParser(description="🐺 wolfbrowser — stealth browsing toolkit")
    subparsers = parser.add_subparsers(dest="command")
    
    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch page content")
    p_fetch.add_argument("url")
    p_fetch.add_argument("--output", "-o", choices=["text", "html", "title", "json"], default="text")
    p_fetch.add_argument("--wait", "-w", type=float, default=2.0, help="Wait seconds after load")
    
    # screenshot
    p_ss = subparsers.add_parser("screenshot", help="Take a screenshot")
    p_ss.add_argument("url")
    p_ss.add_argument("--output", "-o", default="screenshot.png")
    p_ss.add_argument("--full-page", "-f", action="store_true")
    p_ss.add_argument("--wait", "-w", type=float, default=2.0)
    
    # extract
    p_ext = subparsers.add_parser("extract", help="Extract elements by selector")
    p_ext.add_argument("url")
    p_ext.add_argument("--selector", "-s", required=True)
    p_ext.add_argument("--format", choices=["text", "json"], default="text")
    p_ext.add_argument("--wait", "-w", type=float, default=2.0)
    
    # stealth-test
    p_test = subparsers.add_parser("stealth-test", help="Run bot detection tests")
    p_test.add_argument("--screenshot", "-s", action="store_true")
    
    # sessions
    p_sess = subparsers.add_parser("sessions", help="Manage saved sessions")
    sess_sub = p_sess.add_subparsers(dest="subcmd")
    sess_sub.add_parser("list")
    p_del = sess_sub.add_parser("delete")
    p_del.add_argument("name")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    cmd_map = {
        "fetch": cmd_fetch,
        "screenshot": cmd_screenshot,
        "extract": cmd_extract,
        "stealth-test": cmd_stealth_test,
        "sessions": cmd_sessions,
    }
    
    asyncio.run(cmd_map[args.command](args))


if __name__ == "__main__":
    main()
