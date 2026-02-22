from __future__ import annotations

import unittest

try:
    from app.app import create_app
    from app.services.runtime_context import runtime_store

    RUNTIME_DEPS_AVAILABLE = True
except ModuleNotFoundError:
    RUNTIME_DEPS_AVAILABLE = False
    runtime_store = None


@unittest.skipUnless(RUNTIME_DEPS_AVAILABLE, "flask and pyserial are required for route tests")
class RouteContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app().test_client()
        runtime_store.clear_runtime()

    def test_bootstrap_contract(self) -> None:
        response = self.app.get('/app/bootstrap')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        data = payload['data']

        for key in ['has_onboarded', 'esp_connected', 'active_mode', 'calibration_complete', 'recommended_page']:
            self.assertIn(key, data)

    def test_runtime_start_invalid_mode(self) -> None:
        response = self.app.post('/runtime/start', json={'mode': 'bad'})
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload['ok'])

    def test_wireless_ingest_visible_in_runtime_state(self) -> None:
        ingest = self.app.post('/ingest/wireless/cursor', json={'x': 12, 'y': 34, 'device_id': 'esp-01'})
        self.assertEqual(ingest.status_code, 200)

        state_resp = self.app.get('/runtime/state')
        self.assertEqual(state_resp.status_code, 200)
        state = state_resp.get_json()['data']

        self.assertTrue(state['wireless']['connected'])
        self.assertIsNotNone(state['cursor']['last_sample'])


if __name__ == '__main__':
    unittest.main()
