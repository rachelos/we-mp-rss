import unittest
from unittest.mock import MagicMock, patch


class FreqControlFallbackTest(unittest.TestCase):
    @patch("core.wx.model.web.time.sleep")
    @patch("core.wx.model.web.random.randint", return_value=0)
    def test_web_200013_triggers_fallback_without_duplicate_item_over(self, _mock_rand, _mock_sleep):
        from core.wx.model.web import MpsWeb

        collector = object.__new__(MpsWeb)
        collector.token = "test-token"
        collector.cookies = "test-cookie"
        collector.Gather_Content = False
        collector.articles = []
        collector.aids = []
        collector.start_time = 0

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"base_resp": {"ret": 200013, "err_msg": "freq control"}}
        mock_resp.cookies = {}

        collector.session = MagicMock()
        collector.session.get.return_value = mock_resp
        collector.fix_header = MagicMock(return_value={})
        collector._fallback_to_free_publish = MagicMock()

        item_over_cb = MagicMock()
        over_cb = MagicMock()

        with patch("core.wx.base.WxGather.Start"), patch("core.wx.base.WxGather.Item_Over") as mock_item_over, patch("core.wx.base.WxGather.Over") as mock_over:
            collector.get_Articles(
                faker_id="FAKE_ID",
                Mps_id="MP_WXS_123",
                Mps_title="TestMP",
                MaxPage=1,
                Item_Over_CallBack=item_over_cb,
                Over_CallBack=over_cb,
            )

            # Should retry 3 times (max_retries=3) and then delegate to _fallback_to_free_publish once
            self.assertEqual(collector.session.get.call_count, 3)
            collector._fallback_to_free_publish.assert_called_once()
            # Item_Over and Over in MpsWeb must NOT be called because _fallback_to_free_publish handles them
            mock_item_over.assert_not_called()
            mock_over.assert_not_called()

    def test_free_publish_falls_back_to_weread_mp_when_all_endpoints_200013(self):
        from core.wx.model.free_publish import MpsFreePublish

        fp = object.__new__(MpsFreePublish)
        fp.token = "test-token"
        fp.cookies = "test-cookie"
        fp.Gather_Content = False
        fp.articles = []
        fp.aids = []

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"base_resp": {"ret": 200013, "err_msg": "freq control"}}
        fp.session = MagicMock()
        fp.session.get.return_value = mock_resp
        fp.fix_header = MagicMock(return_value={})

        with patch("core.wx.base.WxGather.Start"), patch("core.wx.model.weread_mp.MpsWereadMP") as mock_wmp_cls:
            mock_wmp = MagicMock()
            mock_wmp._weread_cookies = "wr_vid=123; wr_skey=abc"
            mock_wmp_cls.return_value = mock_wmp

            fp.get_Articles(
                faker_id="FAKE_ID",
                Mps_id="MP_WXS_123",
                Mps_title="TestMP",
                MaxPage=1,
            )

            mock_wmp._load_weread_auth.assert_called_once()
            mock_wmp.get_Articles.assert_called_once()


if __name__ == "__main__":
    unittest.main()
