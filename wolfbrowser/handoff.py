"""
Human handoff — pause automation on challenges (CAPTCHA, 2FA, login walls),
notify the human, wait for resolution, then resume.

Supports:
- Challenge detection (CAPTCHA, 2FA, login forms, custom patterns)
- Notification callbacks (Telegram, webhook, console)
- Headed mode with visible browser for human interaction
- Auto-resume on challenge resolution (DOM polling)
- Timeout with configurable fallback
"""

import asyncio
import json
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Awaitable


class ChallengeType(Enum):
    CAPTCHA = "captcha"
    TWO_FA = "2fa"
    LOGIN = "login"
    COOKIE_CONSENT = "cookie_consent"
    AGE_GATE = "age_gate"
    CUSTOM = "custom"


@dataclass
class Challenge:
    """Detected challenge requiring human intervention."""
    challenge_type: ChallengeType
    url: str
    title: str
    description: str
    detected_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    resolved: bool = False

    @property
    def wait_seconds(self) -> float:
        if self.resolved_at:
            return self.resolved_at - self.detected_at
        return time.time() - self.detected_at


@dataclass
class DetectionRule:
    """Rule for detecting a challenge on a page."""
    challenge_type: ChallengeType
    name: str
    # CSS selectors — if ANY match, challenge is detected
    selectors: list[str] = field(default_factory=list)
    # URL substrings — if ANY match, challenge is detected
    url_patterns: list[str] = field(default_factory=list)
    # JS expression returning truthy if challenge present
    js_check: Optional[str] = None
    # CSS selectors that indicate challenge is RESOLVED
    resolution_selectors: list[str] = field(default_factory=list)
    # URL patterns that indicate challenge is RESOLVED (navigated away)
    resolution_url_patterns: list[str] = field(default_factory=list)
    # JS expression returning truthy if challenge resolved
    resolution_js_check: Optional[str] = None
    # Human-readable description for notification
    description: str = ""


# Built-in detection rules for common challenges
BUILTIN_RULES: list[DetectionRule] = [
    # reCAPTCHA
    DetectionRule(
        challenge_type=ChallengeType.CAPTCHA,
        name="recaptcha",
        selectors=[
            "iframe[src*='recaptcha']",
            "iframe[src*='google.com/recaptcha']",
            ".g-recaptcha",
            "#recaptcha",
            "[data-sitekey]",
        ],
        description="Google reCAPTCHA detected",
        resolution_js_check="!document.querySelector('iframe[src*=\"recaptcha\"]') || document.querySelector('.recaptcha-checkbox-checked, .rc-anchor-checked')",
    ),
    # hCaptcha
    DetectionRule(
        challenge_type=ChallengeType.CAPTCHA,
        name="hcaptcha",
        selectors=[
            "iframe[src*='hcaptcha']",
            ".h-captcha",
            "[data-hcaptcha-sitekey]",
        ],
        description="hCaptcha detected",
        resolution_js_check="!document.querySelector('iframe[src*=\"hcaptcha\"]')",
    ),
    # Cloudflare Turnstile
    DetectionRule(
        challenge_type=ChallengeType.CAPTCHA,
        name="cloudflare_turnstile",
        selectors=[
            "iframe[src*='challenges.cloudflare.com']",
            ".cf-turnstile",
            "[data-turnstile-sitekey]",
        ],
        url_patterns=["challenges.cloudflare.com"],
        description="Cloudflare Turnstile challenge",
        resolution_js_check="!document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]')",
    ),
    # Cloudflare challenge page (full page)
    DetectionRule(
        challenge_type=ChallengeType.CAPTCHA,
        name="cloudflare_challenge",
        selectors=[
            "#challenge-form",
            "#challenge-running",
            "#cf-challenge-running",
        ],
        url_patterns=["/cdn-cgi/challenge-platform/"],
        description="Cloudflare full-page challenge",
        resolution_js_check="!document.querySelector('#challenge-form, #challenge-running')",
    ),
    # Generic 2FA — SMS/TOTP code input
    DetectionRule(
        challenge_type=ChallengeType.TWO_FA,
        name="2fa_code_input",
        selectors=[
            "input[name*='otp']",
            "input[name*='totp']",
            "input[name*='2fa']",
            "input[name*='verification_code']",
            "input[name*='verificationCode']",
            "input[name*='sms_code']",
            "input[autocomplete='one-time-code']",
            "[data-testid*='2fa']",
            "[data-testid*='otp']",
        ],
        description="Two-factor authentication code required",
        # Resolved when the input disappears (submitted successfully)
        resolution_js_check="!document.querySelector(\"input[name*='otp'], input[name*='totp'], input[name*='2fa'], input[name*='verification_code'], input[autocomplete='one-time-code']\")",
    ),
    # Google 2FA
    DetectionRule(
        challenge_type=ChallengeType.TWO_FA,
        name="google_2fa",
        url_patterns=[
            "accounts.google.com/signin/v2/challenge",
            "accounts.google.com/v3/signin/challenge",
        ],
        description="Google 2-step verification",
        resolution_url_patterns=["myaccount.google.com", "mail.google.com", "drive.google.com"],
    ),
    # Instagram login/checkpoint
    DetectionRule(
        challenge_type=ChallengeType.TWO_FA,
        name="instagram_checkpoint",
        url_patterns=[
            "instagram.com/accounts/login/two_factor",
            "instagram.com/challenge/",
        ],
        description="Instagram security checkpoint",
        resolution_url_patterns=["instagram.com/"],
        resolution_js_check="!window.location.href.includes('/challenge/') && !window.location.href.includes('/two_factor')",
    ),
    # Generic login page detection
    DetectionRule(
        challenge_type=ChallengeType.LOGIN,
        name="login_form",
        selectors=[
            "form[action*='login']",
            "form[action*='signin']",
            "form[action*='sign-in']",
            "#login-form",
            "[data-testid='login-form']",
        ],
        js_check="document.querySelector(\"input[type='password']:not([style*='display:none'])\") && document.querySelector(\"input[type='password']\").offsetParent !== null",
        description="Login form detected — credentials may be required",
        resolution_js_check="!document.querySelector(\"input[type='password']:not([style*='display:none'])\")",
    ),
    # Cookie consent (lower priority, usually auto-dismissable)
    DetectionRule(
        challenge_type=ChallengeType.COOKIE_CONSENT,
        name="cookie_banner",
        selectors=[
            "#cookie-consent",
            "#cookieConsent",
            ".cookie-banner",
            "[data-testid='cookie-banner']",
            "#onetrust-consent-sdk",
            "#CybotCookiebotDialog",
            ".cc-banner",
        ],
        description="Cookie consent banner",
        resolution_js_check="!document.querySelector('#cookie-consent, #cookieConsent, .cookie-banner, #onetrust-consent-sdk, #CybotCookiebotDialog, .cc-banner')",
    ),
]


# --- Notification backends ---

async def notify_console(challenge: Challenge, context: dict = None):
    """Print challenge to console (default fallback)."""
    print(f"\n{'='*60}")
    print(f"🚨 HUMAN HANDOFF REQUIRED")
    print(f"  Type:    {challenge.challenge_type.value}")
    print(f"  URL:     {challenge.url}")
    print(f"  Detail:  {challenge.description}")
    print(f"  Browser: Waiting for you to solve it...")
    print(f"{'='*60}\n")


async def notify_telegram(challenge: Challenge, context: dict = None):
    """Send notification via Telegram Bot API."""
    bot_token = (context or {}).get("bot_token", "")
    chat_id = (context or {}).get("chat_id", "")
    if not bot_token or not chat_id:
        await notify_console(challenge, context)
        return

    text = (
        f"🚨 *BROWSER HANDOFF*\n\n"
        f"*Challenge:* {challenge.challenge_type.value}\n"
        f"*URL:* `{challenge.url}`\n"
        f"*Detail:* {challenge.description}\n\n"
        f"Jump on the browser and solve it. I'll auto-resume when it's clear."
    )
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    })
    try:
        subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                "-H", "Content-Type: application/json",
                "-d", payload,
            ],
            capture_output=True, timeout=10,
        )
    except Exception:
        await notify_console(challenge, context)


async def notify_webhook(challenge: Challenge, context: dict = None):
    """POST challenge info to a webhook URL."""
    webhook_url = (context or {}).get("webhook_url", "")
    if not webhook_url:
        await notify_console(challenge, context)
        return

    payload = json.dumps({
        "event": "handoff_required",
        "challenge_type": challenge.challenge_type.value,
        "url": challenge.url,
        "title": challenge.title,
        "description": challenge.description,
        "detected_at": challenge.detected_at,
    })
    try:
        subprocess.run(
            ["curl", "-s", "-X", "POST", webhook_url,
             "-H", "Content-Type: application/json", "-d", payload],
            capture_output=True, timeout=10,
        )
    except Exception:
        await notify_console(challenge, context)


# Notification backend registry
NOTIFIERS = {
    "console": notify_console,
    "telegram": notify_telegram,
    "webhook": notify_webhook,
}


class HandoffManager:
    """
    Manages human handoff for browser challenges.

    Usage:
        handoff = HandoffManager(
            notify_via="telegram",
            notify_context={"bot_token": "...", "chat_id": "..."},
        )

        # Check for challenges after navigation
        challenge = await handoff.detect(tab)
        if challenge:
            await handoff.wait_for_resolution(tab, challenge, timeout=300)
            # Automation resumes here
    """

    def __init__(
        self,
        rules: list[DetectionRule] = None,
        notify_via: str = "console",
        notify_context: dict = None,
        notify_fn: Optional[Callable] = None,
        auto_dismiss_cookies: bool = True,
        poll_interval: float = 1.0,
    ):
        self.rules = list(rules or BUILTIN_RULES)
        self.notify_via = notify_via
        self.notify_context = notify_context or {}
        self.notify_fn = notify_fn  # Custom notification function
        self.auto_dismiss_cookies = auto_dismiss_cookies
        self.poll_interval = poll_interval
        self.history: list[Challenge] = []

    def add_rule(self, rule: DetectionRule):
        """Add a custom detection rule."""
        self.rules.append(rule)

    async def detect(self, tab) -> Optional[Challenge]:
        """
        Scan the current page for challenges.
        Returns the first detected Challenge, or None if page is clean.
        """
        current_url = await tab.get_url()
        title = await tab.get_title()

        for rule in self.rules:
            detected = False

            # Check URL patterns
            for pattern in rule.url_patterns:
                if pattern in current_url:
                    detected = True
                    break

            # Check CSS selectors
            if not detected and rule.selectors:
                for selector in rule.selectors:
                    try:
                        exists = await tab.evaluate(
                            f"!!document.querySelector({json.dumps(selector)})"
                        )
                        if exists:
                            detected = True
                            break
                    except Exception:
                        continue

            # Check JS expression
            if not detected and rule.js_check:
                try:
                    result = await tab.evaluate(rule.js_check)
                    if result:
                        detected = True
                except Exception:
                    pass

            if detected:
                # Cookie consent — try auto-dismiss first
                if rule.challenge_type == ChallengeType.COOKIE_CONSENT and self.auto_dismiss_cookies:
                    dismissed = await self._try_dismiss_cookies(tab)
                    if dismissed:
                        continue  # Dismissed, check other rules

                challenge = Challenge(
                    challenge_type=rule.challenge_type,
                    url=current_url,
                    title=title,
                    description=rule.description or f"{rule.name} detected",
                )
                self.history.append(challenge)
                return challenge

        return None

    async def _try_dismiss_cookies(self, tab) -> bool:
        """Try to auto-dismiss cookie consent banners."""
        dismiss_selectors = [
            # "Accept all" buttons in various frameworks
            "#onetrust-accept-btn-handler",
            "[data-testid='cookie-accept']",
            ".cc-btn.cc-allow",
            "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
            "button[data-cookiefirst-action='accept']",
            # Generic accept/agree buttons inside cookie containers
        ]
        for selector in dismiss_selectors:
            try:
                exists = await tab.evaluate(f"!!document.querySelector({json.dumps(selector)})")
                if exists:
                    await tab.click(selector, human_like=True)
                    await asyncio.sleep(0.5)
                    return True
            except Exception:
                continue

        # Fallback: look for buttons with accept/agree text inside known containers
        try:
            dismissed = await tab.evaluate("""
                (() => {
                    const containers = document.querySelectorAll(
                        '#cookie-consent, #cookieConsent, .cookie-banner, #onetrust-consent-sdk, #CybotCookiebotDialog, .cc-banner, [class*=cookie], [id*=cookie]'
                    );
                    for (const c of containers) {
                        const btns = c.querySelectorAll('button, a[role=button], [class*=accept], [class*=agree]');
                        for (const btn of btns) {
                            const text = (btn.textContent || '').toLowerCase();
                            if (text.includes('accept') || text.includes('agree') || text.includes('allow') || text.includes('got it') || text.includes('ok')) {
                                btn.click();
                                return true;
                            }
                        }
                    }
                    return false;
                })()
            """)
            if dismissed:
                await asyncio.sleep(0.5)
                return True
        except Exception:
            pass

        return False

    async def wait_for_resolution(
        self,
        tab,
        challenge: Challenge,
        timeout: float = 300,
        on_timeout: str = "raise",
    ) -> bool:
        """
        Wait for the human to resolve a challenge.

        1. Sends notification via configured backend
        2. Polls the page for resolution signals
        3. Returns True when resolved, raises on timeout

        Args:
            tab: The browser tab with the challenge
            challenge: The detected Challenge object
            timeout: Max seconds to wait (default 5 min)
            on_timeout: "raise" (default) or "continue" or "skip"
        """
        # Notify human
        if self.notify_fn:
            await self.notify_fn(challenge, self.notify_context)
        else:
            notifier = NOTIFIERS.get(self.notify_via, notify_console)
            await notifier(challenge, self.notify_context)

        # Find the matching rule for resolution checks
        matching_rule = None
        for rule in self.rules:
            if rule.description == challenge.description:
                matching_rule = rule
                break

        deadline = time.time() + timeout
        check_count = 0

        while time.time() < deadline:
            await asyncio.sleep(self.poll_interval)
            check_count += 1

            resolved = False

            # Check URL change (navigated away from challenge)
            try:
                current_url = await tab.get_url()
            except Exception:
                # Tab might be navigating
                continue

            if matching_rule:
                # Check resolution URL patterns
                for pattern in matching_rule.resolution_url_patterns:
                    if pattern in current_url:
                        resolved = True
                        break

                # Check resolution selectors (elements that should appear)
                if not resolved and matching_rule.resolution_selectors:
                    for selector in matching_rule.resolution_selectors:
                        try:
                            exists = await tab.evaluate(
                                f"!!document.querySelector({json.dumps(selector)})"
                            )
                            if exists:
                                resolved = True
                                break
                        except Exception:
                            continue

                # Check resolution JS
                if not resolved and matching_rule.resolution_js_check:
                    try:
                        result = await tab.evaluate(matching_rule.resolution_js_check)
                        if result:
                            resolved = True
                    except Exception:
                        pass

            # Fallback: check if original challenge selectors are gone
            if not resolved and matching_rule and matching_rule.selectors:
                all_gone = True
                for selector in matching_rule.selectors:
                    try:
                        exists = await tab.evaluate(
                            f"!!document.querySelector({json.dumps(selector)})"
                        )
                        if exists:
                            all_gone = False
                            break
                    except Exception:
                        continue
                if all_gone:
                    # Also check URL changed from challenge URL
                    if current_url != challenge.url:
                        resolved = True
                    # Or just the elements disappeared (CAPTCHA solved in-place)
                    elif check_count > 3:  # Give it a few polls to be sure
                        resolved = True

            if resolved:
                challenge.resolved = True
                challenge.resolved_at = time.time()
                # Notify resolution
                if self.notify_fn:
                    # Custom notifier might handle resolution too
                    pass
                print(f"✅ Challenge resolved! ({challenge.challenge_type.value}, waited {challenge.wait_seconds:.1f}s)")
                # Small grace period for page to settle
                await asyncio.sleep(1.0)
                return True

        # Timeout
        challenge.resolved = False
        if on_timeout == "raise":
            raise TimeoutError(
                f"Challenge not resolved within {timeout}s: "
                f"{challenge.challenge_type.value} at {challenge.url}"
            )
        elif on_timeout == "skip":
            print(f"⏰ Challenge timed out after {timeout}s, skipping")
            return False
        else:  # continue
            print(f"⏰ Challenge timed out after {timeout}s, continuing anyway")
            return False

    async def detect_and_handle(
        self,
        tab,
        timeout: float = 300,
        on_timeout: str = "raise",
    ) -> Optional[Challenge]:
        """
        Convenience: detect + wait in one call.
        Returns the Challenge if one was found (resolved or not), None if clean.
        """
        challenge = await self.detect(tab)
        if challenge:
            await self.wait_for_resolution(tab, challenge, timeout, on_timeout)
        return challenge

    async def guard_navigation(
        self,
        tab,
        url: str,
        timeout: float = 300,
        on_timeout: str = "raise",
    ) -> Optional[Challenge]:
        """
        Navigate to URL and automatically handle any challenges.
        Use this as a drop-in replacement for tab.goto() when you want
        automatic handoff on challenges.
        """
        await tab.goto(url)
        # Brief pause for page to render challenge elements
        await asyncio.sleep(1.5)
        return await self.detect_and_handle(tab, timeout, on_timeout)
