from __future__ import annotations

import io
import unittest

try:
    from app.app import create_app
    from app.services.runtime_context import runtime_store, wireless_video_service

    RUNTIME_DEPS_AVAILABLE = True
except ModuleNotFoundError:
    RUNTIME_DEPS_AVAILABLE = False
    runtime_store = None
    wireless_video_service = None


@unittest.skipUnless(RUNTIME_DEPS_AVAILABLE, "flask and pyserial are required for route tests")
class RouteContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app().test_client()
        runtime_store.clear_runtime()
        wireless_video_service.set_processor_availability(
            ready=True,
            error=None,
            processor_name=wireless_video_service.get_processor_status().get("processor_name"),
        )

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

    def test_wireless_frame_ingest_requires_file(self) -> None:
        response = self.app.post('/ingest/wireless/frame', data={})
        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload['ok'])

    def test_wireless_frame_ingest_ack_and_state(self) -> None:
        response = self.app.post(
            '/ingest/wireless/frame',
            data={
                'device_id': 'esp-frame-test',
                'frame_ts_ms': '1730000000000',
                'seq': '42',
                'width': '320',
                'height': '240',
                'format': 'jpeg',
                'source_tag': 'unit-test',
                'frame': (io.BytesIO(b'\\xff\\xd8\\xff\\xd9'), 'frame.jpg'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['ok'])

        state_resp = self.app.get('/runtime/state')
        state = state_resp.get_json()['data']
        self.assertIn('wireless_video', state)
        self.assertGreaterEqual(state['wireless_video']['frames_received'], 1)
        self.assertTrue(state['wireless']['connected'])
        self.assertEqual(state['wireless']['device_id'], 'esp-frame-test')
        self.assertIn('processor_name', state['wireless_video'])
        self.assertIn('cv_ready', state['wireless_video'])
        self.assertIn('cv_error', state['wireless_video'])
        self.assertIn('last_detection_ok', state['wireless_video'])
        self.assertIn('fallback_count', state['wireless_video'])

    def test_wireless_frame_ingest_returns_503_when_cv_unavailable(self) -> None:
        wireless_video_service.set_processor_availability(
            ready=False,
            error='forced unavailable for test',
            processor_name='contour_pupil',
        )

        response = self.app.post(
            '/ingest/wireless/frame',
            data={
                'device_id': 'esp-frame-test',
                'frame_ts_ms': '1730000000000',
                'seq': '42',
                'width': '320',
                'height': '240',
                'format': 'jpeg',
                'source_tag': 'unit-test',
                'frame': (io.BytesIO(b'\\xff\\xd8\\xff\\xd9'), 'frame.jpg'),
            },
            content_type='multipart/form-data',
        )
        self.assertEqual(response.status_code, 503)
        payload = response.get_json()
        self.assertFalse(payload['ok'])
        self.assertEqual(payload['error'], 'cv processor unavailable')


if __name__ == '__main__':
    unittest.main()
