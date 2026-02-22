from __future__ import annotations

import threading
import unittest

from app.services.runtime_store import RuntimeStore


class RuntimeStoreTest(unittest.TestCase):
    def test_concurrent_ingest_is_stable(self) -> None:
        store = RuntimeStore()

        def worker(source: str, offset: int) -> None:
            for i in range(120):
                store.ingest_cursor_sample(
                    {
                        "x": i + offset,
                        "y": i,
                        "source": source,
                    },
                    default_source=source,
                )

        threads = [
            threading.Thread(target=worker, args=("serial", 0)),
            threading.Thread(target=worker, args=("wireless", 1000)),
            threading.Thread(target=worker, args=("api", 2000)),
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        state = store.get_state()
        self.assertIn(state["active_source"], {"serial", "wireless", "api"})
        self.assertIsNotNone(state["cursor"]["last_sample"])
        self.assertGreaterEqual(state["cursor"]["sample_rate_hz"], 0)


if __name__ == "__main__":
    unittest.main()
