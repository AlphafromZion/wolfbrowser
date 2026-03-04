"""
wolfbrowser — Alpha's stealth browser toolkit.

Browse like a human. Direct CDP, no Selenium, no WebDriver traces.
"""

from .browser import WolfBrowser
from .stealth import StealthConfig, generate_fingerprint
from .session import SessionManager
from .handoff import HandoffManager, ChallengeType, Challenge, DetectionRule

__version__ = "0.2.0"
__all__ = [
    "WolfBrowser",
    "StealthConfig",
    "SessionManager",
    "HandoffManager",
    "ChallengeType",
    "Challenge",
    "DetectionRule",
    "generate_fingerprint",
]
