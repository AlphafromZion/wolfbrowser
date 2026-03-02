"""
Human-like interaction patterns.
Mouse movement via bezier curves, variable typing speed, smooth scrolling.
"""

import asyncio
import random
import math
from typing import Tuple


def bezier_curve(start: Tuple[float, float], end: Tuple[float, float], steps: int = 20) -> list[Tuple[float, float]]:
    """
    Generate points along a bezier curve between start and end.
    Uses 2 random control points for natural-looking mouse movement.
    """
    # Random control points with some variance
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    
    cp1 = (
        start[0] + dx * random.uniform(0.2, 0.4) + random.uniform(-50, 50),
        start[1] + dy * random.uniform(0.1, 0.3) + random.uniform(-50, 50),
    )
    cp2 = (
        start[0] + dx * random.uniform(0.6, 0.8) + random.uniform(-30, 30),
        start[1] + dy * random.uniform(0.7, 0.9) + random.uniform(-30, 30),
    )
    
    points = []
    for i in range(steps + 1):
        t = i / steps
        # Cubic bezier formula
        x = (1-t)**3 * start[0] + 3*(1-t)**2*t * cp1[0] + 3*(1-t)*t**2 * cp2[0] + t**3 * end[0]
        y = (1-t)**3 * start[1] + 3*(1-t)**2*t * cp1[1] + 3*(1-t)*t**2 * cp2[1] + t**3 * end[1]
        
        # Add micro-jitter (humans aren't perfectly smooth)
        x += random.gauss(0, 0.5)
        y += random.gauss(0, 0.5)
        
        points.append((x, y))
    
    return points


class HumanInteraction:
    """Human-like interaction helpers for a browser tab."""
    
    def __init__(self, tab):
        self.tab = tab
        self._mouse_x = random.randint(100, 500)
        self._mouse_y = random.randint(100, 400)
    
    async def human_move(self, target_x: float, target_y: float):
        """Move mouse along a bezier curve to target position."""
        steps = random.randint(15, 30)
        points = bezier_curve(
            (self._mouse_x, self._mouse_y),
            (target_x, target_y),
            steps=steps,
        )
        
        for x, y in points:
            await self.tab.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": int(x),
                "y": int(y),
            })
            # Variable delay — faster in the middle, slower at start/end
            await asyncio.sleep(random.uniform(0.005, 0.025))
        
        self._mouse_x = target_x
        self._mouse_y = target_y
    
    async def human_click(self, x: float, y: float, double: bool = False):
        """Move to element and click with human-like timing."""
        # Move to target
        await self.human_move(x, y)
        
        # Small pause before click (reaction time)
        await asyncio.sleep(random.uniform(0.05, 0.15))
        
        # Click
        click_count = 2 if double else 1
        for _ in range(click_count):
            await self.tab.send("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": int(x),
                "y": int(y),
                "button": "left",
                "clickCount": 1,
            })
            await asyncio.sleep(random.uniform(0.03, 0.08))
            await self.tab.send("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": int(x),
                "y": int(y),
                "button": "left",
                "clickCount": 1,
            })
            if double:
                await asyncio.sleep(random.uniform(0.05, 0.1))
    
    async def human_type(self, text: str, wpm: int = None):
        """Type text with variable speed, like a human."""
        if wpm is None:
            wpm = random.randint(60, 120)  # Words per minute
        
        chars_per_sec = (wpm * 5) / 60  # Average 5 chars per word
        base_delay = 1.0 / chars_per_sec
        
        for i, char in enumerate(text):
            # Key down
            await self.tab.send("Input.dispatchKeyEvent", {
                "type": "keyDown",
                "text": char,
                "key": char,
                "code": f"Key{char.upper()}" if char.isalpha() else "",
                "windowsVirtualKeyCode": ord(char.upper()) if char.isalpha() else ord(char),
            })
            
            # Tiny delay between down and up
            await asyncio.sleep(random.uniform(0.02, 0.06))
            
            # Key up
            await self.tab.send("Input.dispatchKeyEvent", {
                "type": "keyUp",
                "key": char,
                "code": f"Key{char.upper()}" if char.isalpha() else "",
                "windowsVirtualKeyCode": ord(char.upper()) if char.isalpha() else ord(char),
            })
            
            # Variable inter-key delay
            delay = base_delay * random.uniform(0.5, 1.8)
            
            # Occasional longer pause (thinking, switching fingers)
            if random.random() < 0.05:
                delay += random.uniform(0.2, 0.5)
            
            # Faster for repeated characters
            if i > 0 and text[i] == text[i-1]:
                delay *= 0.6
            
            # Slightly slower after space (word boundary)
            if char == " ":
                delay *= random.uniform(1.0, 1.5)
            
            await asyncio.sleep(delay)
    
    async def human_scroll(self, direction: str = "down", amount: int = 300):
        """Scroll with variable speed, like a human using mouse wheel."""
        total = 0
        target = abs(amount)
        sign = 1 if direction == "down" else -1
        
        while total < target:
            # Variable scroll chunk
            chunk = random.randint(30, 100)
            if total + chunk > target:
                chunk = target - total
            
            await self.tab.send("Input.dispatchMouseEvent", {
                "type": "mouseWheel",
                "x": int(self._mouse_x),
                "y": int(self._mouse_y),
                "deltaX": 0,
                "deltaY": chunk * sign,
            })
            
            total += chunk
            await asyncio.sleep(random.uniform(0.02, 0.08))
        
        # Pause after scrolling (reading)
        await asyncio.sleep(random.uniform(0.1, 0.3))
    
    async def random_idle(self, min_sec: float = 0.5, max_sec: float = 2.0):
        """Simulate idle time — small random mouse movements."""
        duration = random.uniform(min_sec, max_sec)
        end_time = asyncio.get_event_loop().time() + duration
        
        while asyncio.get_event_loop().time() < end_time:
            # Small random mouse movement
            new_x = self._mouse_x + random.gauss(0, 5)
            new_y = self._mouse_y + random.gauss(0, 5)
            
            await self.tab.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved",
                "x": int(new_x),
                "y": int(new_y),
            })
            
            self._mouse_x = new_x
            self._mouse_y = new_y
            
            await asyncio.sleep(random.uniform(0.1, 0.4))
