"""
Core browser manager — launch Chrome, connect via CDP, manage tabs.
No Selenium, no WebDriver, no chromedriver binary. Pure CDP over websocket.
"""

import asyncio
import json
import subprocess
import tempfile
import shutil
import os
import signal
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

try:
    import websockets
except ImportError:
    websockets = None

try:
    import httpx
except ImportError:
    httpx = None

try:
    import aiohttp
except ImportError:
    aiohttp = None

from .stealth import StealthConfig, generate_fingerprint, build_stealth_scripts, build_cdp_stealth_commands
from .interaction import HumanInteraction


@dataclass
class Tab:
    """Represents a browser tab connected via CDP."""
    
    target_id: str
    ws_url: str
    browser: "WolfBrowser"
    _ws: object = None
    _msg_id: int = 0
    _pending: dict = None
    _listener_task: object = None
    interaction: HumanInteraction = None
    
    def __post_init__(self):
        self._pending = {}
        self.interaction = HumanInteraction(self)
    
    async def connect(self):
        """Open websocket to this tab's CDP endpoint."""
        if websockets:
            self._ws = await websockets.connect(self.ws_url, max_size=50 * 1024 * 1024)
        else:
            raise ImportError("Install websockets: pip install websockets")
        self._listener_task = asyncio.create_task(self._listen())
    
    async def _listen(self):
        """Listen for CDP messages."""
        try:
            async for msg in self._ws:
                data = json.loads(msg)
                msg_id = data.get("id")
                if msg_id and msg_id in self._pending:
                    self._pending[msg_id].set_result(data)
        except Exception:
            pass
    
    async def send(self, method: str, params: dict = None) -> dict:
        """Send a CDP command and wait for response."""
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params
        
        future = asyncio.get_event_loop().create_future()
        self._pending[self._msg_id] = future
        
        await self._ws.send(json.dumps(msg))
        
        try:
            result = await asyncio.wait_for(future, timeout=30)
        finally:
            self._pending.pop(self._msg_id, None)
        
        if "error" in result:
            raise RuntimeError(f"CDP error: {result['error']}")
        return result.get("result", {})
    
    async def goto(self, url: str, wait_for: str = "load", timeout: float = 30) -> dict:
        """Navigate to URL and wait for page load."""
        result = await self.send("Page.navigate", {"url": url})
        
        if wait_for == "load":
            # Wait for loadEventFired
            await asyncio.sleep(0.5)  # Give it a moment
            try:
                await asyncio.wait_for(self._wait_for_load(), timeout=timeout)
            except asyncio.TimeoutError:
                pass  # Page may still be usable
        
        return result
    
    async def _wait_for_load(self):
        """Poll document readyState until complete."""
        for _ in range(60):
            result = await self.evaluate("document.readyState")
            if result == "complete":
                return
            await asyncio.sleep(0.5)
    
    async def evaluate(self, expression: str) -> any:
        """Execute JavaScript and return result."""
        result = await self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        value = result.get("result", {}).get("value")
        return value
    
    async def get_text(self) -> str:
        """Get visible text content of the page."""
        return await self.evaluate("document.body.innerText")
    
    async def get_html(self) -> str:
        """Get full HTML of the page."""
        return await self.evaluate("document.documentElement.outerHTML")
    
    async def get_title(self) -> str:
        """Get page title."""
        return await self.evaluate("document.title")
    
    async def get_url(self) -> str:
        """Get current URL."""
        return await self.evaluate("window.location.href")
    
    async def screenshot(self, path: str = None, full_page: bool = False, quality: int = 80) -> bytes:
        """Take a screenshot."""
        params = {"format": "png"}
        if full_page:
            # Get full page dimensions
            metrics = await self.send("Page.getLayoutMetrics")
            content = metrics.get("contentSize", {})
            params["clip"] = {
                "x": 0, "y": 0,
                "width": content.get("width", 1920),
                "height": content.get("height", 1080),
                "scale": 1,
            }
        
        result = await self.send("Page.captureScreenshot", params)
        import base64
        data = base64.b64decode(result["data"])
        
        if path:
            Path(path).write_bytes(data)
        
        return data
    
    async def pdf(self, path: str) -> bytes:
        """Save page as PDF."""
        result = await self.send("Page.printToPDF", {
            "printBackground": True,
            "preferCSSPageSize": True,
        })
        import base64
        data = base64.b64decode(result["data"])
        Path(path).write_bytes(data)
        return data
    
    async def select(self, css_selector: str) -> list[dict]:
        """Find elements by CSS selector, return their text and attributes."""
        result = await self.evaluate(f"""
            Array.from(document.querySelectorAll({json.dumps(css_selector)})).map(el => ({{
                tag: el.tagName.toLowerCase(),
                text: el.innerText?.substring(0, 500) || '',
                href: el.href || '',
                src: el.src || '',
                id: el.id || '',
                className: el.className || '',
                rect: el.getBoundingClientRect().toJSON(),
            }}))
        """)
        return result or []
    
    async def find(self, text: str) -> Optional[dict]:
        """Find element by visible text (shortest match wins, like nodriver)."""
        result = await self.evaluate(f"""
            (() => {{
                const searchText = {json.dumps(text)}.toLowerCase();
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                const candidates = [];
                while (walker.nextNode()) {{
                    const el = walker.currentNode;
                    const elText = (el.innerText || el.textContent || '').trim();
                    if (elText.toLowerCase().includes(searchText)) {{
                        candidates.push({{
                            element: el,
                            text: elText,
                            length: elText.length,
                        }});
                    }}
                }}
                // Shortest text wins (most specific match)
                candidates.sort((a, b) => a.length - b.length);
                const best = candidates[0];
                if (!best) return null;
                const rect = best.element.getBoundingClientRect();
                return {{
                    tag: best.element.tagName.toLowerCase(),
                    text: best.text.substring(0, 200),
                    rect: rect.toJSON(),
                    selector: (() => {{
                        if (best.element.id) return '#' + best.element.id;
                        return best.element.tagName.toLowerCase();
                    }})(),
                }};
            }})()
        """)
        return result
    
    async def click(self, selector_or_text: str, human_like: bool = True):
        """Click an element by CSS selector or visible text."""
        # Try CSS selector first
        element = await self.evaluate(f"""
            (() => {{
                let el = document.querySelector({json.dumps(selector_or_text)});
                if (!el) {{
                    // Fallback: find by text
                    const searchText = {json.dumps(selector_or_text)}.toLowerCase();
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                    const candidates = [];
                    while (walker.nextNode()) {{
                        const node = walker.currentNode;
                        const text = (node.innerText || '').trim().toLowerCase();
                        if (text.includes(searchText)) {{
                            candidates.push({{ el: node, len: text.length }});
                        }}
                    }}
                    candidates.sort((a, b) => a.len - b.len);
                    el = candidates[0]?.el;
                }}
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                return {{ x: rect.x + rect.width/2, y: rect.y + rect.height/2 }};
            }})()
        """)
        
        if not element:
            raise ValueError(f"Element not found: {selector_or_text}")
        
        x, y = element["x"], element["y"]
        
        if human_like:
            await self.interaction.human_click(x, y)
        else:
            await self.send("Input.dispatchMouseEvent", {
                "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1
            })
            await asyncio.sleep(0.05)
            await self.send("Input.dispatchMouseEvent", {
                "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1
            })
    
    async def type_text(self, selector: str, text: str, human_like: bool = True):
        """Click an input and type text into it."""
        await self.click(selector, human_like=human_like)
        await asyncio.sleep(0.1)
        
        if human_like:
            await self.interaction.human_type(text)
        else:
            for char in text:
                await self.send("Input.dispatchKeyEvent", {
                    "type": "keyDown", "text": char, "key": char
                })
                await self.send("Input.dispatchKeyEvent", {
                    "type": "keyUp", "key": char
                })
    
    async def scroll(self, direction: str = "down", amount: int = 300, human_like: bool = True):
        """Scroll the page."""
        if human_like:
            await self.interaction.human_scroll(direction, amount)
        else:
            delta_y = amount if direction == "down" else -amount
            await self.send("Input.dispatchMouseEvent", {
                "type": "mouseWheel", "x": 400, "y": 400,
                "deltaX": 0, "deltaY": delta_y,
            })
    
    async def wait_for(self, selector: str, timeout: float = 10) -> bool:
        """Wait for an element to appear."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            result = await self.evaluate(f"!!document.querySelector({json.dumps(selector)})")
            if result:
                return True
            await asyncio.sleep(0.3)
        return False
    
    async def close(self):
        """Close this tab."""
        if self._listener_task:
            self._listener_task.cancel()
        if self._ws:
            await self._ws.close()


class WolfBrowser:
    """
    Stealth browser manager. Launches Chrome with anti-detection,
    connects via CDP, provides human-like interaction.
    """
    
    def __init__(
        self,
        headless: bool = True,
        stealth_config: Optional[StealthConfig] = None,
        chrome_path: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        proxy: Optional[str] = None,
    ):
        self.headless = headless
        self.config = stealth_config or generate_fingerprint()
        self.chrome_path = chrome_path or self._find_chrome()
        self.user_data_dir = user_data_dir
        self.proxy = proxy
        self._process: Optional[subprocess.Popen] = None
        self._temp_dir: Optional[str] = None
        self._debug_port: int = 0
        self._tabs: list[Tab] = []
    
    @staticmethod
    def _find_chrome() -> str:
        """Find Chrome/Chromium binary."""
        paths = [
            "google-chrome", "google-chrome-stable", "chromium-browser", "chromium",
            "/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
        for p in paths:
            if shutil.which(p):
                return p
        raise FileNotFoundError("Chrome/Chromium not found. Install it or pass chrome_path.")
    
    async def start(self) -> "WolfBrowser":
        """Launch Chrome and connect."""
        # Find a free port
        import socket
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self._debug_port = sock.getsockname()[1]
        sock.close()
        
        # Create temp profile if not using persistent one
        if not self.user_data_dir:
            self._temp_dir = tempfile.mkdtemp(prefix="wolf_")
            profile_dir = self._temp_dir
        else:
            profile_dir = self.user_data_dir
            os.makedirs(profile_dir, exist_ok=True)
        
        # Chrome launch args — stealth-optimized
        args = [
            self.chrome_path,
            f"--remote-debugging-port={self._debug_port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-client-side-phishing-detection",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-hang-monitor",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--disable-translate",
            "--metrics-recording-only",
            "--no-service-autorun",
            "--password-store=basic",
            "--use-mock-keychain",
            # Anti-detection specific
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            f"--window-size={self.config.screen_width},{self.config.screen_height}",
            # Remove automation indicators
            "--disable-infobars",
        ]
        
        if self.headless:
            args.append("--headless=new")
        
        if self.proxy:
            args.append(f"--proxy-server={self.proxy}")
        
        # Start Chrome
        self._process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )
        
        # Wait for CDP to be ready
        await self._wait_for_cdp()
        
        return self
    
    async def _wait_for_cdp(self, timeout: float = 15):
        """Wait for Chrome's CDP endpoint to be ready."""
        deadline = asyncio.get_event_loop().time() + timeout
        url = f"http://127.0.0.1:{self._debug_port}/json/version"
        
        while asyncio.get_event_loop().time() < deadline:
            try:
                if httpx:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(url, timeout=2)
                        if resp.status_code == 200:
                            return
                elif aiohttp:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                            if resp.status == 200:
                                return
                else:
                    # Fallback: use subprocess curl
                    result = subprocess.run(
                        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                        capture_output=True, text=True, timeout=2,
                    )
                    if result.stdout.strip() == "200":
                        return
            except Exception:
                pass
            await asyncio.sleep(0.3)
        
        raise TimeoutError(f"Chrome CDP not ready after {timeout}s")
    
    async def _get_targets(self) -> list[dict]:
        """Get list of available targets (tabs)."""
        url = f"http://127.0.0.1:{self._debug_port}/json"
        
        if httpx:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                return resp.json()
        elif aiohttp:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    return await resp.json()
        else:
            result = subprocess.run(
                ["curl", "-s", url], capture_output=True, text=True, timeout=5,
            )
            return json.loads(result.stdout)
    
    async def new_tab(self, url: str = "about:blank") -> Tab:
        """Open a new tab, apply stealth, navigate to URL."""
        # Create new target
        create_url = f"http://127.0.0.1:{self._debug_port}/json/new?{url}"
        
        if httpx:
            async with httpx.AsyncClient() as client:
                resp = await client.get(create_url)
                target = resp.json()
        elif aiohttp:
            async with aiohttp.ClientSession() as session:
                async with session.get(create_url) as resp:
                    target = await resp.json()
        else:
            result = subprocess.run(
                ["curl", "-s", create_url], capture_output=True, text=True, timeout=5,
            )
            target = json.loads(result.stdout)
        
        ws_url = target["webSocketDebuggerUrl"]
        tab = Tab(target_id=target["id"], ws_url=ws_url, browser=self)
        await tab.connect()
        
        # Apply stealth
        await self._apply_stealth(tab)
        
        self._tabs.append(tab)
        return tab
    
    async def get_tab(self) -> Tab:
        """Get the first available tab (or create one), with stealth applied."""
        targets = await self._get_targets()
        page_targets = [t for t in targets if t.get("type") == "page"]
        
        if page_targets:
            target = page_targets[0]
            ws_url = target["webSocketDebuggerUrl"]
            tab = Tab(target_id=target["id"], ws_url=ws_url, browser=self)
            await tab.connect()
            await self._apply_stealth(tab)
            self._tabs.append(tab)
            return tab
        
        return await self.new_tab()
    
    async def _apply_stealth(self, tab: Tab):
        """Apply all stealth patches to a tab."""
        # Enable required domains
        await tab.send("Page.enable")
        await tab.send("Network.enable")
        await tab.send("Runtime.enable")
        
        # CDP-level patches (user agent, timezone, locale)
        for cmd in build_cdp_stealth_commands(self.config):
            try:
                await tab.send(cmd["method"], cmd["params"])
            except Exception:
                pass  # Some commands may not be supported in all Chrome versions
        
        # JS stealth scripts — injected BEFORE any page JS runs
        for script in build_stealth_scripts(self.config):
            await tab.send("Page.addScriptToEvaluateOnNewDocument", {"source": script})
    
    async def stop(self):
        """Kill Chrome and clean up."""
        for tab in self._tabs:
            try:
                await tab.close()
            except Exception:
                pass
        
        if self._process:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            self._process = None
        
        if self._temp_dir and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, *args):
        await self.stop()
