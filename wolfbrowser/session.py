"""
Session management — save/load cookies, manage browser profiles.
Lets Alpha maintain logged-in state across sessions.
"""

import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime


DEFAULT_PROFILES_DIR = os.path.expanduser("~/.openclaw/workspace/projects/stealth-browser/profiles")


class SessionManager:
    """Manage named browser sessions with persistent cookies and state."""
    
    def __init__(self, profiles_dir: str = None):
        self.profiles_dir = Path(profiles_dir or DEFAULT_PROFILES_DIR)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
    
    def list_sessions(self) -> list[str]:
        """List all saved session names."""
        sessions = []
        for f in self.profiles_dir.glob("*.json"):
            sessions.append(f.stem)
        return sorted(sessions)
    
    async def save_session(self, tab, name: str):
        """Save cookies and session data from a tab."""
        # Get all cookies via CDP
        result = await tab.send("Network.getAllCookies")
        cookies = result.get("cookies", [])
        
        # Get localStorage for current domain
        local_storage = await tab.evaluate("""
            (() => {
                const data = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    data[key] = localStorage.getItem(key);
                }
                return data;
            })()
        """)
        
        # Get current URL
        url = await tab.get_url()
        
        session_data = {
            "name": name,
            "url": url,
            "saved_at": datetime.now().isoformat(),
            "cookies": cookies,
            "local_storage": local_storage or {},
        }
        
        path = self.profiles_dir / f"{name}.json"
        path.write_text(json.dumps(session_data, indent=2))
        return path
    
    async def load_session(self, tab, name: str) -> bool:
        """Restore cookies and navigate to saved URL."""
        path = self.profiles_dir / f"{name}.json"
        if not path.exists():
            return False
        
        session_data = json.loads(path.read_text())
        
        # Set cookies
        cookies = session_data.get("cookies", [])
        for cookie in cookies:
            # CDP setCookie needs slightly different format
            params = {
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie.get("domain", ""),
                "path": cookie.get("path", "/"),
                "secure": cookie.get("secure", False),
                "httpOnly": cookie.get("httpOnly", False),
            }
            if cookie.get("expires", -1) > 0:
                params["expires"] = cookie["expires"]
            if cookie.get("sameSite"):
                params["sameSite"] = cookie["sameSite"]
            
            try:
                await tab.send("Network.setCookie", params)
            except Exception:
                pass  # Some cookies may fail (expired, wrong domain)
        
        # Navigate to saved URL
        url = session_data.get("url", "about:blank")
        if url and url != "about:blank":
            await tab.goto(url)
        
        # Restore localStorage
        local_storage = session_data.get("local_storage", {})
        if local_storage:
            for key, value in local_storage.items():
                await tab.evaluate(f"localStorage.setItem({json.dumps(key)}, {json.dumps(value)})")
        
        return True
    
    def delete_session(self, name: str) -> bool:
        """Delete a saved session."""
        path = self.profiles_dir / f"{name}.json"
        if path.exists():
            path.unlink()
            return True
        return False
    
    def get_session_info(self, name: str) -> Optional[dict]:
        """Get metadata about a saved session."""
        path = self.profiles_dir / f"{name}.json"
        if not path.exists():
            return None
        
        data = json.loads(path.read_text())
        return {
            "name": name,
            "url": data.get("url", ""),
            "saved_at": data.get("saved_at", ""),
            "cookie_count": len(data.get("cookies", [])),
            "storage_keys": len(data.get("local_storage", {})),
        }
