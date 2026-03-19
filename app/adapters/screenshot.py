from __future__ import annotations

from playwright.async_api import async_playwright

# Screenshot yolu Playwright doğrudan: browser-use CDP Page bazen navigasyon sonrası
# "Not attached to an active page" veriyor; görev ajanı browser-use'ta kalır.
_NAV_TIMEOUT_MS = 90_000


async def capture_url_png(url: str, *, headless: bool) -> bytes:
    """Tek seferlik Chromium ile sayfa açıp PNG ekran görüntüsü alır."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
            shot = await page.screenshot(type="png", full_page=False)
            if not isinstance(shot, (bytes, bytearray)):
                raise TypeError(f"unexpected screenshot type: {type(shot)}")
            return bytes(shot)
        finally:
            await browser.close()
