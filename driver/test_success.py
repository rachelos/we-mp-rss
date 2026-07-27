import importlib
import sys
import types
import unittest
from unittest.mock import patch


class FakeRedisBackend:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def getset(self, key, value):
        previous = self.data.get(key)
        self.data[key] = value
        return previous


class FakeRedisClient:
    def __init__(self):
        self._client = FakeRedisBackend()
        self.is_connected = True


class SuccessStatusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake_redis_client = FakeRedisClient()

        token_module = types.ModuleType("driver.token")
        token_module.set_token = lambda *args, **kwargs: None

        print_module = types.ModuleType("core.print")
        print_module.print_warning = lambda *args, **kwargs: None
        print_module.print_success = lambda *args, **kwargs: None

        redis_module = types.ModuleType("core.redis_client")
        redis_module.redis_client = cls.fake_redis_client

        cls.module_patch = patch.dict(
            sys.modules,
            {
                "driver.token": token_module,
                "core.print": print_module,
                "core.redis_client": redis_module,
            },
        )
        cls.module_patch.start()
        sys.modules.pop("driver.success", None)
        cls.success = importlib.import_module("driver.success")

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("driver.success", None)
        cls.module_patch.stop()

    def setUp(self):
        self.fake_redis_client._client.data = {
            self.success.REDIS_KEY_STATUS: "1"
        }
        self.success.WX_LOGIN_ED = True
        self.notifications = []
        self.success._send_expired_notification = self.notifications.append

    def test_expired_timestamp_invalidates_and_notifies_once(self):
        self.success.getLoginInfo = lambda: {
            "token": "present",
            "expiry": {
                "expiry_timestamp": 1,
                "remaining_seconds": 999999,
            },
        }

        self.assertFalse(self.success.getStatus())
        self.assertFalse(self.success.getStatus())
        self.assertEqual(
            self.fake_redis_client._client.get(self.success.REDIS_KEY_STATUS),
            "0",
        )
        self.assertEqual(len(self.notifications), 1)

    def test_repeated_invalid_session_only_notifies_once(self):
        self.assertTrue(self.success.invalidateStatus("invalid session"))
        self.assertFalse(self.success.invalidateStatus("invalid session"))
        self.assertEqual(self.notifications, ["invalid session"])

    def test_missing_status_key_with_saved_token_notifies_once(self):
        self.fake_redis_client._client.data = {}
        self.success.WX_LOGIN_ED = False
        self.success.getLoginInfo = lambda: {"token": "present"}

        self.assertTrue(self.success.invalidateStatus("invalid session"))
        self.assertFalse(self.success.invalidateStatus("invalid session"))
        self.assertEqual(self.notifications, ["invalid session"])

    def test_valid_timestamp_allows_token(self):
        self.success.getLoginInfo = lambda: {
            "token": "present",
            "expiry": {
                "expiry_timestamp": 4102444800,
                "remaining_seconds": 0,
            },
        }

        self.assertTrue(self.success.CanGetToken())
        self.assertEqual(self.notifications, [])

    def test_missing_token_invalidates_and_notifies_once(self):
        self.success.getLoginInfo = lambda: {"expiry": {}}

        self.assertFalse(self.success.CanGetToken())
        self.assertFalse(self.success.CanGetToken())
        self.assertEqual(len(self.notifications), 1)

    def test_token_read_failure_keeps_current_status(self):
        def raise_read_error():
            raise RuntimeError("read failed")

        self.success.getLoginInfo = raise_read_error

        self.assertTrue(self.success.getStatus())
        self.assertEqual(self.notifications, [])


if __name__ == "__main__":
    unittest.main()
