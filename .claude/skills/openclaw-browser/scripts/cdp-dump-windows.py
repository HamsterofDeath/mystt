#!/usr/bin/env python3
"""Dump text, HTML, and a screenshot from a Windows Chrome CDP page.

Run this with Windows Python when WSL cannot reach Chrome's loopback-only CDP
port but Windows can. Dependencies:

    python -m pip install --user requests websocket-client
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

try:
    import requests
    import websocket
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Run in Windows PowerShell: "
        "python -m pip install --user requests websocket-client"
    ) from exc


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class Cdp:
    def __init__(self, ws_url: str) -> None:
        self.ws = websocket.create_connection(ws_url, timeout=20, suppress_origin=True)
        self.next_id = 1

    def send(self, method: str, params: dict | None = None, session_id: str | None = None, timeout: int = 20) -> dict:
        msg_id = self.next_id
        self.next_id += 1
        msg = {"id": msg_id, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        self.ws.send(json.dumps(msg))
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = json.loads(self.ws.recv())
            if data.get("id") == msg_id:
                if "error" in data:
                    raise RuntimeError(f"{method}: {data['error']}")
                return data.get("result", {})
        raise TimeoutError(method)

    def close(self) -> None:
        self.ws.close()


def browser_ws(port: int) -> str:
    version = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=5).json()
    return version["webSocketDebuggerUrl"]


def eval_js(cdp: Cdp, session: str, expression: str, timeout: int = 20):
    result = cdp.send(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
            "timeout": timeout * 1000,
        },
        session_id=session,
        timeout=timeout + 5,
    )
    return result.get("result", {}).get("value")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--port", type=int, default=18802)
    parser.add_argument("--wait", type=float, default=25)
    parser.add_argument("--prefix", default="C:/Users/dhaup/AppData/Local/Temp/openclaw-cdp-page")
    parser.add_argument("--head", type=int, default=6000)
    parser.add_argument("--keep-open", action="store_true", help="Leave the temporary tab open for manual inspection")
    args = parser.parse_args()

    cdp = Cdp(browser_ws(args.port))
    target_id = None
    try:
        target_id = cdp.send("Target.createTarget", {"url": "about:blank"})["targetId"]
        session = cdp.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})["sessionId"]
        cdp.send("Page.enable", session_id=session)
        cdp.send("Runtime.enable", session_id=session)
        cdp.send("Page.navigate", {"url": args.url}, session_id=session)
        time.sleep(args.wait)

        text = eval_js(cdp, session, "document.body ? document.body.innerText : ''", timeout=10) or ""
        html = eval_js(cdp, session, "document.documentElement ? document.documentElement.outerHTML : ''", timeout=10) or ""
        href = eval_js(cdp, session, "location.href", timeout=5)
        title = eval_js(cdp, session, "document.title", timeout=5)
        png = cdp.send("Page.captureScreenshot", {"format": "png", "fromSurface": True}, session_id=session, timeout=30)

        prefix = Path(args.prefix)
        prefix.with_suffix(".txt").write_text(text, encoding="utf-8")
        prefix.with_suffix(".html").write_text(html, encoding="utf-8")
        prefix.with_suffix(".png").write_bytes(base64.b64decode(png["data"]))

        print(f"URL={href}")
        print(f"TITLE={title}")
        print(f"TEXT_PATH={prefix.with_suffix('.txt')}")
        print(f"HTML_PATH={prefix.with_suffix('.html')}")
        print(f"SCREENSHOT_PATH={prefix.with_suffix('.png')}")
        print("TEXT_HEAD_START")
        print(text[: args.head])
        print("TEXT_HEAD_END")
    finally:
        if target_id and not args.keep_open:
            try:
                cdp.send("Target.closeTarget", {"targetId": target_id}, timeout=5)
            except Exception:
                pass
        cdp.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
