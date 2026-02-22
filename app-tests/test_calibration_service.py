from __future__ import annotations

import os
import tempfile
import unittest

from app.services.calibration_service import CalibrationService
from app.services.runtime_store import RuntimeStore


class CalibrationServiceTest(unittest.TestCase):
    def test_calibration_session_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prefs_path = os.path.join(tmp, "prefs.json")
            os.environ["EYE_PREFS_PATH"] = prefs_path
            try:
                runtime_store = RuntimeStore()
                service = CalibrationService(runtime_store)

                session = service.start_session(total_nodes=3, node_order=[0, 1, 2])
                self.assertEqual(session["state"], "running")

                session = service.record_node(session_id=session["session_id"], node_index=0)
                self.assertIn(0, session["completed_nodes"])

                done = service.complete_session(
                    session_id=session["session_id"],
                    calibration_data=[{"index": 0}],
                    timestamp=123,
                )
                self.assertEqual(done["state"], "completed")

                runtime_state = runtime_store.get_state()
                self.assertEqual(runtime_state["calibration"]["state"], "completed")
            finally:
                os.environ.pop("EYE_PREFS_PATH", None)


if __name__ == "__main__":
    unittest.main()
