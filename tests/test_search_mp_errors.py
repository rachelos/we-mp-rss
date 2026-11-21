import unittest
from unittest import mock

import requests

from apis.mps import _search_mp_error_message
from core.wx.base import WxAuthError, WxGather, WxRateLimitError


class SearchMpErrorMessageTest(unittest.TestCase):
    def test_auth_error_asks_for_rescan(self):
        self.assertIn("重新扫码授权", _search_mp_error_message(WxAuthError("x")))

    def test_rate_limit_is_not_reported_as_auth(self):
        msg = _search_mp_error_message(WxRateLimitError("x"))
        self.assertIn("限流", msg)
        self.assertNotIn("扫码", msg)

    def test_network_error_is_not_reported_as_auth(self):
        msg = _search_mp_error_message(requests.exceptions.SSLError("tls"))
        self.assertIn("网络或代理", msg)
        self.assertNotIn("扫码", msg)

    def test_unknown_error_is_not_reported_as_auth(self):
        self.assertNotIn("扫码", _search_mp_error_message(ValueError("x")))


class SearchBizRaisesTest(unittest.TestCase):
    def _gather(self, token="tok"):
        ga = WxGather()
        ga.get_token = mock.Mock()
        ga.token = token
        ga.proxy_enabled = False
        ga.fix_header = mock.Mock(return_value={})
        return ga

    def test_rate_limit_raises(self):
        resp = mock.Mock(text='{"base_resp": {"ret": 200013, "err_msg": "freq control"}}')
        with mock.patch("core.wx.base.requests.get", return_value=resp):
            with self.assertRaises(WxRateLimitError):
                self._gather().search_Biz("kw")

    def test_missing_token_raises_auth_error(self):
        with self.assertRaises(WxAuthError):
            self._gather(token="").search_Biz("kw")

    def test_network_error_propagates(self):
        with mock.patch("core.wx.base.requests.get",
                        side_effect=requests.exceptions.SSLError("tls")):
            with self.assertRaises(requests.exceptions.SSLError):
                self._gather().search_Biz("kw")


if __name__ == "__main__":
    unittest.main()
