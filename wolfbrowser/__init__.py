"""
wolfbrowser — Alpha's stealth browser toolkit.

Browse like a human. Direct CDP, no Selenium, no WebDriver traces.
"""

from .browser import WolfBrowser
from .stealth import StealthConfig, generate_fingerprint
from .session import SessionManager

__version__ = "0.1.0"
__all__ = ["WolfBrowser", "StealthConfig", "SessionManager", "generate_fingerprint"]
