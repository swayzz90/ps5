#!/usr/bin/env python3
"""Check the exact PlayStation product page and publish a safe status.

Intentionally reports `unknown` instead of inferring availability when a response
is blocked, unavailable, or ambiguous. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PRODUCT_URL = (
    "https://www.playstation.com/de-de/ps5/certified-refurbished-ps5-slim/"
    "product/PSD001-PSDE00233_59-PS5GRADEDCLIZSLE/"
)
STATUS_FILE = Path(__file__).resolve().parents[1] / "site/data/status.json"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class PageText(HTMLParser):
    """Extract text users could see, excluding scripts, styles and navigation."""

    IGNORE = {"script", "style", "noscript", "svg", "nav", "footer"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.VOID:
            return
        if self.skip_depth:
            self.skip_depth += 1
        elif tag.lower() in self.IGNORE:
            self.skip_depth = 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        pass

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth and data.strip():
            self.parts.append(data)


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return re.sub(r"\s+", " ", s).strip()


def classify_page(html: str) -> tuple[str, str]:
    """Return (available|unavailable|unknown, reason) from visible page text."""
    extractor = PageText()
    extractor.feed(html)
    text = normalize(" ".join(extractor.parts))

    # Never declare an unrelated error, consent, captcha, or redirect page as stock.
    if not all(term in text for term in ("generalüberholt", "slim", "konsole")):
        return "unknown", "Die Produktbeschreibung konnte nicht erkannt werden."

    explicit_unavailable = any(
        marker in text
        for marker in (
            "nicht zum kauf erhältlich",
            "derzeit nicht vorrätig",
            "zurzeit nicht vorrätig",
            "momentan nicht vorrätig",
            "derzeit ausverkauft",
            "nicht auf lager",
        )
    )
    explicit_available = any(
        marker in text
        for marker in ("in den einkaufswagen", "zum warenkorb hinzufügen")
    )

    # The product page can contain a general stock banner as well as a button.
    # Contradictions are not enough evidence for a push notification.
    if explicit_unavailable and explicit_available:
        return "unknown", "Die Seite enthält widersprüchliche Kaufsignale."
    if explicit_unavailable:
        return "unavailable", "PlayStation meldet: derzeit nicht kaufbar."
    if explicit_available:
        return "available", "PlayStation zeigt einen Einkaufswagen-Button."
    return "unknown", "Kein eindeutiger Kaufstatus im Seiteninhalt gefunden."


def fetch_product() -> str:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
        "Cache-Control": "no-cache",
    }
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            req = Request(PRODUCT_URL, headers=headers)
            with urlopen(req, timeout=22) as response:
                if response.status != 200:
                    raise ValueError(f"HTTP {response.status}")
                if "text/html" not in response.headers.get("Content-Type", ""):
                    raise ValueError("Unerwarteter Antworttyp")
                if response.url.split("?")[0].rstrip("/") != PRODUCT_URL.rstrip("/"):
                    raise ValueError("Die Produktseite hat weitergeleitet")
                # Cap response size so unexpected pages do not consume excessive memory.
                raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise ValueError("Antwort ist ungewöhnlich groß")
                return raw.decode("utf-8", errors="replace")
        except (HTTPError, URLError, ValueError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(3)
    raise RuntimeError(f"Abruf fehlgeschlagen: {last_error}")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_previous() -> dict:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def send_notification(topic: str) -> None:
    if not re.fullmatch(r"[-_A-Za-z0-9]{1,64}", topic):
        raise ValueError("NTFY_TOPIC darf nur Buchstaben, Zahlen, _ und - enthalten")
    payload = json.dumps(
        {
            "topic": topic,
            "title": "PS5 Slim wieder verfügbar!",
            "message": "Die generalüberholte PS5 Slim könnte wieder bestellbar sein. Jetzt prüfen und schnell kaufen.",
            "priority": 4,
            "tags": ["video_game"],
            "click": PRODUCT_URL,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = Request(
        "https://ntfy.sh/",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "PS5-Stock-Monitor/1.0"},
        method="POST",
    )
    with urlopen(req, timeout=15) as response:
        if response.status not in (200, 201, 202):
            raise ValueError(f"ntfy meldet HTTP {response.status}")


def main() -> None:
    old = load_previous()
    checked_at = utc_now()
    try:
        html = fetch_product()
        status, note = classify_page(html)
    except Exception as exc:  # Network/captcha/errors must never become false positives.
        status, note = "unknown", f"Abruf fehlgeschlagen ({type(exc).__name__})."
        print(f"Hinweis: {exc}")

    prev_known = old.get("last_known_status", "unknown")
    last_change_at = old.get("last_change_at")
    available_since = old.get("available_since")

    if status in ("available", "unavailable") and status != prev_known:
        last_change_at = checked_at
        if status == "available":
            available_since = checked_at
        else:
            available_since = None

    last_known_status = status if status != "unknown" else prev_known
    notified_since = old.get("notified_for_available_since")

    # Retry failed notifications on later checks; once a restock has been alerted,
    # do not alert again unless an out-of-stock state was observed in between.
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if status == "available" and available_since and notified_since != available_since:
        if topic:
            try:
                send_notification(topic)
                notified_since = available_since
                print("ntfy-Benachrichtigung verschickt")
            except (HTTPError, URLError, ValueError, TimeoutError, OSError) as exc:
                print(f"ntfy-Benachrichtigung fehlgeschlagen (später erneut): {exc}")
        else:
            print("Keine Push-Nachricht: GitHub-Secret NTFY_TOPIC fehlt")

    history = old.get("history", [])
    if not isinstance(history, list):
        history = []
    history = (history + [{"at": checked_at, "status": status, "note": note}])[-12:]

    result = {
        "product_url": PRODUCT_URL,
        "status": status,
        "note": note,
        "checked_at": checked_at,
        "last_known_status": last_known_status,
        "last_change_at": last_change_at,
        "available_since": available_since,
        "notified_for_available_since": notified_since,
        "interval_minutes": 30,
        "history": history,
    }
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{checked_at}: {status}: {note}")


if __name__ == "__main__":
    main()
