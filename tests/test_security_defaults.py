"""Exercise HTTP guards without importing production databases or credentials."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import OAuth2PasswordBearer
from fastapi.testclient import TestClient


class SecurityDefaultsTest(unittest.TestCase):
    def setUp(self):
        self.settings = {}
        self.authenticate = AsyncMock(return_value={"role": "admin"})
        fake_auth = types.ModuleType("core.auth")
        fake_auth.oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)
        fake_auth.get_current_user_or_ak = self.authenticate
        fake_config = types.ModuleType("core.config")
        fake_config.cfg = types.SimpleNamespace(get=lambda key, default=None: self.settings.get(key, default))
        source = Path(__file__).resolve().parents[1] / "core" / "security.py"
        spec = importlib.util.spec_from_file_location("security_under_test", source)
        guards = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"core.auth": fake_auth, "core.config": fake_config}):
            spec.loader.exec_module(guards)
        app = FastAPI()
        self.effects = []

        @app.get("/rss/{feed_id}", dependencies=[Depends(guards.guard_rss_template)])
        def rss(feed_id: str):
            self.effects.append("rss")
            return {"feed": feed_id}

        @app.post("/github/update", dependencies=[Depends(guards.require_web_updater)])
        def update():
            self.effects.append("update")
            return {"ok": True}

        self.client = TestClient(app)

    def test_standard_feed_remains_public(self):
        self.assertEqual(self.client.get("/rss/all").status_code, 200)
        self.authenticate.assert_not_awaited()

    def test_disabled_template_including_empty_never_reaches_handler(self):
        for template in ("", "example"):
            self.assertEqual(self.client.get("/rss/all", params={"template": template}).status_code, 403)
        self.assertEqual(self.effects, [])
        self.authenticate.assert_not_awaited()

    def test_updater_disabled_even_for_authenticated_admin(self):
        self.assertEqual(self.client.post("/github/update", headers={"Authorization": "Bearer admin"}).status_code, 403)
        self.assertEqual(self.effects, [])

    def test_enabled_features_require_authentication(self):
        self.settings.update({"safe.enable_custom_rss_template": True, "safe.enable_web_updater": True})
        self.assertEqual(self.client.get("/rss/all?template=example").status_code, 401)
        self.assertEqual(self.client.post("/github/update").status_code, 401)
        self.assertEqual(self.effects, [])

    def test_enabled_features_reject_non_admin_and_cascade_node(self):
        self.settings.update({"safe.enable_custom_rss_template": True, "safe.enable_web_updater": True})
        for role in ("user", "cascade_node"):
            self.authenticate.return_value = {"role": role}
            headers = {"Authorization": "Bearer user"}
            self.assertEqual(self.client.get("/rss/all?template=x", headers=headers).status_code, 403)
            self.assertEqual(self.client.post("/github/update", headers=headers).status_code, 403)
        self.assertEqual(self.effects, [])

    def test_invalid_credentials_do_not_reach_handler(self):
        self.settings["safe.enable_web_updater"] = True
        self.authenticate.side_effect = HTTPException(status_code=401)
        self.assertEqual(self.client.post("/github/update", headers={"Authorization": "Bearer invalid"}).status_code, 401)
        self.assertEqual(self.effects, [])

    def test_admin_can_explicitly_enable_features_with_bearer_or_ak(self):
        self.settings.update({"safe.enable_custom_rss_template": True, "safe.enable_web_updater": True})
        for credential in ("Bearer admin", "AK-SK key:secret"):
            headers = {"Authorization": credential}
            self.assertEqual(self.client.get("/rss/all?template=x", headers=headers).status_code, 200)
            self.assertEqual(self.client.post("/github/update", headers=headers).status_code, 200)

    def test_unparsed_string_flag_fails_closed(self):
        for value in ("false", "true", 1):
            self.settings["safe.enable_web_updater"] = value
            self.assertEqual(self.client.post("/github/update").status_code, 403)
        self.assertEqual(self.effects, [])


if __name__ == "__main__":
    unittest.main()
