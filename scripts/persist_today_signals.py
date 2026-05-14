"""One-shot: run scanner with persist=True so today's LONG signals are
written to edge_signals for future walk-forward evaluation."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

from app.db.session import async_session_maker  # noqa: E402
from app.services.scanner_service import scan_universe  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s - %(message)s")


async def main() -> None:
    async with async_session_maker() as s:
        res = await scan_universe(s, bias_filter="LONG", persist=True, limit=200)
    print(f"scanned={res['scanned']} LONG matched={res['matched']} "
          f"(persisted to edge_signals)")
    for item in res["items"][:20]:
        print(f"  {item['symbol']:>6s} {item.get('setup','—'):>28s} "
              f"rr={item.get('risk_reward'):>4.2f}  "
              f"conf={item.get('confidence'):>4.2f}  "
              f"regime={(item.get('regime') or {}).get('label','—')}")


if __name__ == "__main__":
    asyncio.run(main())
