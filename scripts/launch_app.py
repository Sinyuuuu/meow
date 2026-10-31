"""One-click Windows launcher that selects a usable local port and opens the site."""

from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings as _settings  # Loads the project's optional .env file.


def port_available(port: int) -> bool:
    """Return whether the loopback port can be bound by this process."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def choose_port() -> int:
    """Honor APP_PORT, otherwise fall back through common local demo ports."""
    configured = os.getenv("APP_PORT")
    if configured:
        port = int(configured)
        if not port_available(port):
            raise RuntimeError(f"APP_PORT {port} is unavailable; close the program using it or change APP_PORT")
        return port
    for port in (8000, 8010, 8080, 8765):
        if port_available(port):
            return port
    raise RuntimeError("No local demo port is available (tried 8000, 8010, 8080, 8765)")


def main() -> None:
    port = choose_port()
    url = f"http://127.0.0.1:{port}"
    print("=" * 52)
    print(" Meow一下 · 智慧貓咪寄養照護平台")
    print(f" 網站位置：{url}")
    database_url = make_url(_settings.database_url)
    if database_url.drivername.startswith("sqlite"):
        print(f" 固定資料庫：{Path(database_url.database or '').resolve()}")
    else:
        print(
            f" 資料庫：{database_url.drivername}://"
            f"{database_url.host or 'local'}/{database_url.database or ''}"
        )
    print(" 保持此視窗開啟；按 Ctrl+C 或關閉視窗即可停止。")
    print("=" * 52)
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()
