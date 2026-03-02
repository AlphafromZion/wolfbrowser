"""
Stealth configuration and anti-detection patches.
Applied via CDP before any page JavaScript executes.
"""

import random
import json
from dataclasses import dataclass, field
from typing import Optional


# Common real-world screen resolutions (width, height)
SCREEN_RESOLUTIONS = [
    (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
    (1280, 720), (1600, 900), (2560, 1440), (1280, 800),
    (1680, 1050), (1920, 1200), (2560, 1080), (3840, 2160),
]

# Realistic GPU renderers (must match platform)
WEBGL_RENDERERS = {
    "Windows": [
        ("ANGLE (NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("ANGLE (NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("ANGLE (Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("ANGLE (AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0)", "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ],
    "Linux": [
        ("Mesa Intel(R) UHD Graphics 630 (CFL GT2)", "Mesa/X.Org"),
        ("NVIDIA GeForce RTX 3060/PCIe/SSE2", "NVIDIA Corporation"),
        ("AMD Radeon RX 580 (polaris10, LLVM 15.0.7, DRM 3.49, 6.1.0-18-amd64)", "AMD"),
    ],
    "Mac": [
        ("Apple M1", "Apple"),
        ("Apple M2", "Apple"),
        ("AMD Radeon Pro 5500M", "Apple"),
        ("Intel(R) Iris(TM) Plus Graphics", "Apple"),
    ],
}

# Chrome version components
CHROME_VERSIONS = [
    "141.0.7587.0", "142.0.7612.0", "143.0.7651.0", "144.0.7698.0", "145.0.7632.116",
]

PLATFORMS = [
    {"platform": "Win32", "oscpu": "Windows NT 10.0; Win64; x64", "ua_platform": "Windows NT 10.0; Win64; x64"},
    {"platform": "Linux x86_64", "oscpu": "Linux x86_64", "ua_platform": "X11; Linux x86_64"},
    {"platform": "MacIntel", "oscpu": "Intel Mac OS X 10_15_7", "ua_platform": "Macintosh; Intel Mac OS X 10_15_7"},
]

LANGUAGES = [
    ["en-US", "en"],
    ["en-GB", "en"],
    ["en-AU", "en"],
]

TIMEZONES = {
    "en-US": ["America/New_York", "America/Chicago", "America/Los_Angeles", "America/Denver"],
    "en-GB": ["Europe/London"],
    "en-AU": ["Australia/Sydney", "Australia/Melbourne", "Australia/Brisbane"],
}


@dataclass
class StealthConfig:
    """Fingerprint configuration for a browser session."""
    
    # Screen
    screen_width: int = 1920
    screen_height: int = 1080
    device_pixel_ratio: float = 1.0
    color_depth: int = 24
    
    # Platform
    platform: str = "Win32"
    oscpu: str = "Windows NT 10.0; Win64; x64"
    ua_platform: str = "Windows NT 10.0; Win64; x64"
    
    # Browser
    chrome_version: str = "145.0.7632.116"
    user_agent: str = ""
    
    # Locale
    languages: list = field(default_factory=lambda: ["en-US", "en"])
    timezone: str = "America/New_York"
    locale: str = "en-US"
    
    # WebGL
    webgl_vendor: str = "Google Inc. (NVIDIA)"
    webgl_renderer: str = "ANGLE (NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0)"
    
    # Hardware
    hardware_concurrency: int = 8
    device_memory: int = 8
    max_touch_points: int = 0
    
    # Plugins
    plugin_count: int = 5
    
    def __post_init__(self):
        if not self.user_agent:
            self.user_agent = f"Mozilla/5.0 ({self.ua_platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{self.chrome_version} Safari/537.36"


def generate_fingerprint(platform_hint: Optional[str] = None) -> StealthConfig:
    """Generate a random but internally consistent fingerprint."""
    
    # Pick platform
    if platform_hint:
        plat = next((p for p in PLATFORMS if platform_hint.lower() in p["platform"].lower()), random.choice(PLATFORMS))
    else:
        plat = random.choice(PLATFORMS)
    
    # Pick matching GPU
    plat_key = "Windows" if "Win" in plat["platform"] else ("Mac" if "Mac" in plat["platform"] else "Linux")
    gpu = random.choice(WEBGL_RENDERERS[plat_key])
    
    # Pick screen
    screen = random.choice(SCREEN_RESOLUTIONS)
    dpr = random.choice([1.0, 1.0, 1.0, 1.25, 1.5, 2.0])  # 1.0 most common
    
    # Pick locale
    langs = random.choice(LANGUAGES)
    tz_key = langs[0]
    tz = random.choice(TIMEZONES.get(tz_key, ["America/New_York"]))
    
    # Pick Chrome version
    version = random.choice(CHROME_VERSIONS)
    
    # Hardware
    cores = random.choice([4, 8, 8, 12, 16])
    memory = random.choice([4, 8, 8, 16, 16, 32])
    
    return StealthConfig(
        screen_width=screen[0],
        screen_height=screen[1],
        device_pixel_ratio=dpr,
        platform=plat["platform"],
        oscpu=plat["oscpu"],
        ua_platform=plat["ua_platform"],
        chrome_version=version,
        languages=langs,
        timezone=tz,
        locale=langs[0],
        webgl_vendor=gpu[1] if len(gpu) > 1 else "Google Inc.",
        webgl_renderer=gpu[0],
        hardware_concurrency=cores,
        device_memory=memory,
        max_touch_points=0 if "Mac" not in plat["platform"] else 0,
    )


def build_stealth_scripts(config: StealthConfig) -> list[str]:
    """Build JavaScript snippets to inject via CDP Page.addScriptToEvaluateOnNewDocument."""
    
    scripts = []
    
    # 1. Hide webdriver flag (THE critical one)
    scripts.append("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        // Also delete from prototype
        delete Object.getPrototypeOf(navigator).webdriver;
    """)
    
    # 2. Fake plugins array
    scripts.append(f"""
        Object.defineProperty(navigator, 'plugins', {{
            get: () => {{
                const plugins = [];
                const names = [
                    'Chrome PDF Plugin', 'Chrome PDF Viewer', 'Native Client',
                    'Chromium PDF Plugin', 'Chromium PDF Viewer'
                ];
                for (let i = 0; i < {config.plugin_count}; i++) {{
                    plugins.push({{
                        name: names[i] || 'Plugin ' + i,
                        description: names[i] || 'Plugin',
                        filename: 'internal-' + names[i].toLowerCase().replace(/ /g, '-'),
                        length: 1
                    }});
                }}
                plugins.refresh = () => {{}};
                return plugins;
            }},
            configurable: true
        }});
    """)
    
    # 3. Languages
    scripts.append(f"""
        Object.defineProperty(navigator, 'languages', {{
            get: () => {json.dumps(config.languages)},
            configurable: true
        }});
        Object.defineProperty(navigator, 'language', {{
            get: () => {json.dumps(config.languages[0])},
            configurable: true
        }});
    """)
    
    # 4. Platform
    scripts.append(f"""
        Object.defineProperty(navigator, 'platform', {{
            get: () => {json.dumps(config.platform)},
            configurable: true
        }});
    """)
    
    # 5. Hardware concurrency + device memory
    scripts.append(f"""
        Object.defineProperty(navigator, 'hardwareConcurrency', {{
            get: () => {config.hardware_concurrency},
            configurable: true
        }});
        Object.defineProperty(navigator, 'deviceMemory', {{
            get: () => {config.device_memory},
            configurable: true
        }});
    """)
    
    # 6. Screen dimensions
    scripts.append(f"""
        Object.defineProperty(screen, 'width', {{ get: () => {config.screen_width} }});
        Object.defineProperty(screen, 'height', {{ get: () => {config.screen_height} }});
        Object.defineProperty(screen, 'availWidth', {{ get: () => {config.screen_width} }});
        Object.defineProperty(screen, 'availHeight', {{ get: () => {config.screen_height - 40} }});
        Object.defineProperty(screen, 'colorDepth', {{ get: () => {config.color_depth} }});
        Object.defineProperty(screen, 'pixelDepth', {{ get: () => {config.color_depth} }});
        Object.defineProperty(window, 'devicePixelRatio', {{ get: () => {config.device_pixel_ratio} }});
    """)
    
    # 7. window.chrome object (must exist in real Chrome)
    scripts.append("""
        if (!window.chrome) {
            window.chrome = {
                app: {
                    isInstalled: false,
                    InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                    RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
                    getDetails: () => null,
                    getIsInstalled: () => false,
                },
                runtime: {
                    OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
                    OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
                    PlatformArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                    PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
                    PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
                    RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' },
                    connect: () => { throw new TypeError('Error in invocation of runtime.connect'); },
                    sendMessage: () => { throw new TypeError('Error in invocation of runtime.sendMessage'); },
                },
                csi: () => ({}),
                loadTimes: () => ({}),
            };
        }
    """)
    
    # 8. Permissions API — don't leak automation state
    scripts.append("""
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => {
            if (parameters.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission });
            }
            return originalQuery(parameters);
        };
    """)
    
    # 9. WebGL fingerprint
    scripts.append(f"""
        const getParameterProxyHandler = {{
            apply: function(target, thisArg, args) {{
                const param = args[0];
                // UNMASKED_VENDOR_WEBGL
                if (param === 0x9245) return {json.dumps(config.webgl_vendor)};
                // UNMASKED_RENDERER_WEBGL
                if (param === 0x9246) return {json.dumps(config.webgl_renderer)};
                return Reflect.apply(target, thisArg, args);
            }}
        }};
        
        // Patch both WebGL and WebGL2
        ['WebGLRenderingContext', 'WebGL2RenderingContext'].forEach(ctx => {{
            if (window[ctx]) {{
                const proto = window[ctx].prototype;
                const origGetParameter = proto.getParameter;
                proto.getParameter = new Proxy(origGetParameter, getParameterProxyHandler);
            }}
        }});
    """)
    
    # 10. Prevent iframe contentWindow detection
    scripts.append("""
        // Fix iframe contentWindow.chrome being undefined
        const origContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
        if (origContentWindow) {
            Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                get: function() {
                    const win = origContentWindow.get.call(this);
                    if (win && !win.chrome) {
                        win.chrome = window.chrome;
                    }
                    return win;
                }
            });
        }
    """)
    
    # 11. Prevent toString detection of patched functions
    scripts.append("""
        // Make our overrides look native
        const nativeToString = Function.prototype.toString;
        const proxyHandler = {
            apply: function(target, thisArg, args) {
                // If someone calls toString on one of our patched getters, return native-looking string
                if (thisArg && thisArg.name && thisArg.name.startsWith('get ')) {
                    return `function ${thisArg.name}() { [native code] }`;
                }
                return Reflect.apply(target, thisArg, args);
            }
        };
        Function.prototype.toString = new Proxy(nativeToString, proxyHandler);
    """)
    
    return scripts


def build_cdp_stealth_commands(config: StealthConfig) -> list[dict]:
    """Build CDP commands to execute for stealth (non-JS patches)."""
    
    commands = []
    
    # Set user agent via CDP (more reliable than JS override)
    commands.append({
        "method": "Network.setUserAgentOverride",
        "params": {
            "userAgent": config.user_agent,
            "acceptLanguage": ",".join(config.languages),
            "platform": config.platform,
            "userAgentMetadata": {
                "brands": [
                    {"brand": "Chromium", "version": config.chrome_version.split(".")[0]},
                    {"brand": "Google Chrome", "version": config.chrome_version.split(".")[0]},
                    {"brand": "Not-A.Brand", "version": "99"},
                ],
                "fullVersionList": [
                    {"brand": "Chromium", "version": config.chrome_version},
                    {"brand": "Google Chrome", "version": config.chrome_version},
                    {"brand": "Not-A.Brand", "version": "99.0.0.0"},
                ],
                "platform": "Windows" if "Win" in config.platform else ("macOS" if "Mac" in config.platform else "Linux"),
                "platformVersion": "10.0.0" if "Win" in config.platform else ("14.6.1" if "Mac" in config.platform else "6.1.0"),
                "architecture": "x86" if "Win" in config.platform else "x86",
                "bitness": "64",
                "mobile": False,
                "model": "",
            },
        },
    })
    
    # Set timezone
    commands.append({
        "method": "Emulation.setTimezoneOverride",
        "params": {"timezoneId": config.timezone},
    })
    
    # Set locale
    commands.append({
        "method": "Emulation.setLocaleOverride",
        "params": {"locale": config.locale},
    })
    
    return commands
