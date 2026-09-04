import unittest
from unittest.mock import Mock, patch

from core.wx.model.weread_mp import (
    MpsWereadMP,
    WereadMPAPIError,
    build_mp_url,
    extract_mp_content,
    parse_mp_articles,
)


class WereadMpParsingTest(unittest.TestCase):
    def test_parse_mp_articles_maps_article_fields(self):
        payload = {
            "synckey": 1782304237,
            "reviews": [
                {
                    "createTime": 1778580000,
                    "subReviews": [
                        {
                            "reviewId": "MP_WXS_1_review-1",
                            "review": {
                                "reviewId": "MP_WXS_1_review-1",
                                "createTime": 1778580001,
                                "mpInfo": {
                                    "title": "Article title",
                                    "content": "Article summary",
                                    "time": 1778580002,
                                    "originalId": "abc~def",
                                    "pic_url": "https://example.test/cover.jpg",
                                    "readNum": 12,
                                    "likeNum": 3,
                                },
                            },
                        }
                    ],
                }
            ],
        }

        articles, group_count = parse_mp_articles(payload)

        self.assertEqual(group_count, 1)
        self.assertEqual(len(articles), 1)
        self.assertEqual(
            articles[0],
            {
                "aid": "MP_WXS_1_review-1",
                "id": "MP_WXS_1_review-1",
                "title": "Article title",
                "link": "https://mp.weixin.qq.com/s/abc~def",
                "cover": "https://example.test/cover.jpg",
                "digest": "Article summary",
                "content": "",
                "create_time": 1778580001,
                "update_time": 1778580002,
                "read_num": 12,
                "like_num": 3,
                "item_show_type": 0,
            },
        )

    def test_parse_mp_articles_classifies_rate_limit(self):
        with self.assertRaises(WereadMPAPIError) as caught:
            parse_mp_articles({"errCode": -2041, "errMsg": "request blocked"})

        self.assertEqual(caught.exception.code, -2041)
        self.assertFalse(caught.exception.retriable)

    def test_extract_mp_content_returns_article_body(self):
        html = """
        <html><body>
          <div id="js_content"><p>Hello</p><script>bad()</script></div>
        </body></html>
        """

        self.assertEqual(extract_mp_content(html), '<p>Hello</p>')

    def test_build_mp_url_rejects_missing_original_id(self):
        self.assertEqual(build_mp_url(""), "")


class WereadMpRequestTest(unittest.TestCase):
    def make_collector(self):
        collector = object.__new__(MpsWereadMP)
        collector._weread_cookies = "wr_vid=1; wr_skey=skey"
        collector._weread_ticket = "ticket-value"
        collector.user_agent = "test-agent"
        collector.proxy_enabled = False
        collector.http_proxy_url = ""
        return collector

    def make_collector_with_vid(self):
        collector = self.make_collector()
        collector._weread_vid = "123"
        return collector

    @patch("core.wx.model.weread.MpsWeread._get_shelf_books")
    def test_ensure_mp_on_shelf_skips_when_already_present(self, shelf):
        shelf.return_value = [{"book_id": "MP_WXS_1", "title": "t"}]
        collector = self.make_collector_with_vid()

        ok, detail = collector.ensure_mp_on_shelf("MP_WXS_1", "Name")

        self.assertTrue(ok)
        self.assertEqual(detail, "已在书架")

    @patch("core.wx.model.weread.MpsWeread._weread_post")
    @patch("core.wx.model.weread.MpsWeread._get_shelf_books")
    def test_ensure_mp_on_shelf_adds_missing_mp(self, shelf, post):
        shelf.return_value = [{"book_id": "MP_WXS_2", "title": "other"}]
        post.return_value = {"errCode": 0, "errMsg": ""}
        collector = self.make_collector_with_vid()

        ok, detail = collector.ensure_mp_on_shelf("MP_WXS_1", "Name")

        self.assertTrue(ok)
        self.assertIn("已自动添加", detail)
        post.assert_called_once()
        url, kwargs = post.call_args
        self.assertIn("/web/shelf/add", url[0])
        self.assertEqual(kwargs["json_data"], {"bookIds": ["MP_WXS_1"]})

    @patch("core.wx.model.weread.MpsWeread._weread_post")
    @patch("core.wx.model.weread.MpsWeread._get_shelf_books")
    def test_ensure_mp_on_shelf_reports_login_expired(self, shelf, post):
        shelf.return_value = [{"book_id": "MP_WXS_2", "title": "other"}]
        post.return_value = {"errCode": -2012, "errMsg": "login expired"}
        collector = self.make_collector_with_vid()

        ok, detail = collector.ensure_mp_on_shelf("MP_WXS_1", "Name")

        self.assertFalse(ok)
        self.assertIn("登录态失效", detail)

    def test_ensure_mp_on_shelf_skips_non_mp(self):
        collector = self.make_collector_with_vid()

        ok, detail = collector.ensure_mp_on_shelf("3300008485", "Book")

        self.assertTrue(ok)
        self.assertIn("跳过", detail)

    @patch("requests.get")
    def test_article_list_request_uses_official_endpoint_and_ticket(self, get):
        response = Mock(status_code=200)
        response.json.return_value = {"reviews": []}
        get.return_value = response
        collector = self.make_collector()

        payload = collector._get_mp_articles_page("MP_WXS_1", offset=20)

        self.assertEqual(payload, {"reviews": []})
        _, kwargs = get.call_args
        self.assertEqual(get.call_args.args[0], "https://weread.qq.com/web/mp/articles")
        self.assertEqual(
            kwargs["params"],
            {"bookId": "MP_WXS_1", "offset": 20},
        )
        self.assertEqual(kwargs["headers"]["x-wr-ticket"], "ticket-value")

    @patch("requests.get")
    def test_article_list_allows_missing_ticket(self, get):
        response = Mock(status_code=200)
        response.json.return_value = {"reviews": []}
        get.return_value = response
        collector = self.make_collector()
        collector._weread_ticket = ""

        payload = collector._get_mp_articles_page("MP_WXS_1", offset=0)

        self.assertEqual(payload, {"reviews": []})
        self.assertNotIn("x-wr-ticket", get.call_args.kwargs["headers"])

    @patch("requests.get")
    def test_content_request_extracts_official_article_html(self, get):
        response = Mock(
            status_code=200,
            text='<html><div id="js_content"><p>Full text</p></div></html>',
        )
        get.return_value = response
        collector = self.make_collector()

        content = collector._get_mp_content("MP_WXS_1_review-1")

        self.assertEqual(content, "<p>Full text</p>")
        self.assertEqual(get.call_args.args[0], "https://weread.qq.com/web/mp/content")
        self.assertEqual(
            get.call_args.kwargs["params"],
            {"reviewId": "MP_WXS_1_review-1"},
        )


class WereadMpCollectorTest(unittest.TestCase):
    def make_collector(self):
        collector = object.__new__(MpsWereadMP)
        collector.articles = []
        collector.aids = []
        collector.start_time = None
        collector.Gather_Content = False
        collector._weread_cookies = "wr_vid=1; wr_skey=skey"
        collector._weread_ticket = "ticket-value"
        collector._weread_vid = "1"
        collector._weread_name = "tester"
        collector._cookies = {}
        collector.user_agent = "test-agent"
        collector.proxy_enabled = False
        collector.http_proxy_url = ""
        collector.get_token = Mock()
        collector._load_weread_auth = Mock()
        collector.update_mps = Mock()
        collector._get_feed_update_time = Mock(return_value=0)
        collector._get_content_interval = Mock(return_value=0)
        collector._get_page_interval = Mock(return_value=0)
        return collector

    @patch("core.wx.base.RSS.clear_cache")
    @patch("core.wx.base.setStatus")
    def test_get_articles_collects_mp_article_and_advances_after_success(
        self, _set_status, _clear_cache
    ):
        collector = self.make_collector()
        collector._get_mp_articles_page = Mock(return_value={
            "reviews": [{
                "subReviews": [{
                    "review": {
                        "reviewId": "MP_WXS_1_review-1",
                        "createTime": 1778580001,
                        "mpInfo": {
                            "title": "Article title",
                            "content": "Summary",
                            "time": 1778580002,
                            "originalId": "abc~def",
                            "pic_url": "https://example.test/cover.jpg",
                        },
                    }
                }]
            }]
        })
        collector._get_mp_content = Mock(return_value="<p>Full text</p>")
        saved = []

        collector.get_Articles(
            faker_id="legacy-fake-id",
            Mps_id="MP_WXS_1",
            Mps_title="Feed title",
            CallBack=lambda article: saved.append(article) or True,
            MaxPage=1,
            Gather_Content=True,
            interval=0,
        )

        collector._get_mp_articles_page.assert_called_once_with("MP_WXS_1", offset=0)
        self.assertEqual(saved[0]["url"], "https://mp.weixin.qq.com/s/abc~def")
        self.assertEqual(saved[0]["content"], "<p>Full text</p>")
        self.assertEqual(saved[0]["publish_time"], 1778580002)
        self.assertEqual(collector.all_count(), 1)
        collector.update_mps.assert_called_once()
        updated_feed = collector.update_mps.call_args.args[1]
        self.assertEqual(updated_feed.update_time, 1778580002)

    @patch("core.wx.base.RSS.clear_cache")
    def test_get_articles_does_not_advance_after_list_failure(self, _clear_cache):
        collector = self.make_collector()
        collector._get_mp_articles_page = Mock(
            side_effect=WereadMPAPIError(-2041, "blocked", retriable=False)
        )
        collector._get_mp_cover = Mock(
            side_effect=WereadMPAPIError(-2012, "login expired")
        )

        with self.assertRaises(WereadMPAPIError):
            collector.get_Articles(
                Mps_id="MP_WXS_1",
                Mps_title="Feed title",
                CallBack=lambda article: True,
                MaxPage=1,
                interval=0,
            )

        collector.update_mps.assert_not_called()

    @patch("core.wx.base.RSS.clear_cache")
    def test_list_failure_falls_back_to_cover_latest_article(self, _clear_cache):
        collector = self.make_collector()
        collector._get_mp_articles_page = Mock(
            side_effect=WereadMPAPIError(-2041, "blocked", retriable=False)
        )
        collector._get_mp_cover = Mock(return_value={
            "reviewId": "MP_WXS_1_latest",
            "title": "Latest",
            "pic": "https://example.test/pic.jpg",
        })
        saved = []

        collector.get_Articles(
            Mps_id="MP_WXS_1",
            Mps_title="Feed title",
            CallBack=lambda article: saved.append(article) or True,
            MaxPage=1,
            interval=0,
        )

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["title"], "Latest")
        self.assertEqual(saved[0]["url"], "https://mp.weixin.qq.com/s/latest")
        collector.update_mps.assert_called_once()

    @patch("core.wx.base.RSS.clear_cache")
    def test_pagination_counts_groups_not_articles(self, _clear_cache):
        collector = self.make_collector()
        collector._get_mp_articles_page = Mock(side_effect=[
            {
                "reviews": [
                    {"subReviews": [{} for _ in range(20)]},
                ],
            },
            {"reviews": []},
        ])

        collector.get_Articles(
            Mps_id="MP_WXS_1",
            Mps_title="Feed title",
            CallBack=lambda article: True,
            MaxPage=2,
            interval=0,
        )

        self.assertEqual(
            collector._get_mp_articles_page.call_args_list,
            [
                unittest.mock.call("MP_WXS_1", offset=0),
                unittest.mock.call("MP_WXS_1", offset=1),
            ],
        )

    @patch("core.wx.base.RSS.clear_cache")
    def test_scheduled_run_catches_up_to_previous_update_time(self, _clear_cache):
        collector = self.make_collector()
        collector._get_feed_update_time.return_value = 1778580001
        collector._get_catchup_page_limit = Mock(return_value=3)
        collector._is_article_gathered = Mock(
            side_effect=lambda mp_id, aid: aid == "MP_WXS_1_old"
        )
        collector._get_mp_articles_page = Mock(side_effect=[
            {
                "reviews": [{
                    "subReviews": [{
                        "review": {
                            "reviewId": "MP_WXS_1_new",
                            "createTime": 1778580003,
                            "mpInfo": {"title": "New", "originalId": "new"},
                        }
                    }]
                }]
            },
            {
                "reviews": [{
                    "subReviews": [{
                        "review": {
                            "reviewId": "MP_WXS_1_old",
                            "createTime": 1778580001,
                            "mpInfo": {"title": "Old", "originalId": "old"},
                        }
                    }]
                }]
            },
        ])

        collector.get_Articles(
            Mps_id="MP_WXS_1",
            Mps_title="Feed title",
            CallBack=lambda article: True,
            MaxPage=1,
            interval=0,
        )

        self.assertEqual(
            collector._get_mp_articles_page.call_args_list,
            [
                unittest.mock.call("MP_WXS_1", offset=0),
                unittest.mock.call("MP_WXS_1", offset=1),
            ],
        )
        collector.update_mps.assert_called_once()

    @patch("core.wx.base.RSS.clear_cache")
    def test_cover_era_update_time_does_not_block_backfill(self, _clear_cache):
        """cover 模式写入的 update_time 是抓取时间（晚于文章发布时间），
        不能因此跳过 cover 时代漏采的文章；以入库记录为停止边界。"""
        collector = self.make_collector()
        collector._get_feed_update_time.return_value = 1778700000
        collector._is_article_gathered = Mock(
            side_effect=lambda mp_id, aid: aid == "MP_WXS_1_latest"
        )
        collector._get_mp_articles_page = Mock(return_value={
            "reviews": [{
                "subReviews": [
                    {
                        "review": {
                            "reviewId": "MP_WXS_1_latest",
                            "createTime": 1778580003,
                            "mpInfo": {"title": "Latest", "originalId": "latest"},
                        }
                    },
                    {
                        "review": {
                            "reviewId": "MP_WXS_1_missed",
                            "createTime": 1778580002,
                            "mpInfo": {"title": "Missed", "originalId": "missed"},
                        }
                    },
                ]
            }]
        })
        saved = []

        collector.get_Articles(
            Mps_id="MP_WXS_1",
            Mps_title="Feed title",
            CallBack=lambda article: saved.append(article) or True,
            MaxPage=1,
            interval=0,
        )

        self.assertEqual([a["title"] for a in saved], ["Missed"])
        collector.update_mps.assert_called_once()

    @patch("core.wx.base.RSS.clear_cache")
    def test_incomplete_catchup_does_not_mark_feed_synced(self, _clear_cache):
        collector = self.make_collector()
        collector._get_feed_update_time.return_value = 1778580001
        collector._get_catchup_page_limit = Mock(return_value=1)
        collector._get_mp_articles_page = Mock(return_value={
            "reviews": [{
                "subReviews": [{
                    "review": {
                        "reviewId": "MP_WXS_1_new",
                        "createTime": 1778580003,
                        "mpInfo": {"title": "New", "originalId": "new"},
                    }
                }]
            }]
        })

        with self.assertRaises(WereadMPAPIError) as caught:
            collector.get_Articles(
                Mps_id="MP_WXS_1",
                Mps_title="Feed title",
                CallBack=lambda article: True,
                MaxPage=1,
                interval=0,
            )

        self.assertEqual(caught.exception.code, "backlog_incomplete")
        collector.update_mps.assert_not_called()

    @patch("core.wx.model.weread_mp.time.sleep")
    @patch("core.wx.base.RSS.clear_cache")
    def test_fulltext_requests_are_throttled_between_articles(self, _clear_cache, sleep):
        collector = self.make_collector()
        collector._get_content_interval.return_value = 2
        collector._get_mp_articles_page = Mock(return_value={
            "reviews": [{
                "subReviews": [
                    {
                        "review": {
                            "reviewId": "MP_WXS_1_a",
                            "createTime": 1778580002,
                            "mpInfo": {"title": "A", "originalId": "a"},
                        }
                    },
                    {
                        "review": {
                            "reviewId": "MP_WXS_1_b",
                            "createTime": 1778580001,
                            "mpInfo": {"title": "B", "originalId": "b"},
                        }
                    },
                ]
            }]
        })
        collector._get_mp_content = Mock(return_value="<p>Full text</p>")

        collector.get_Articles(
            Mps_id="MP_WXS_1",
            Mps_title="Feed title",
            CallBack=lambda article: True,
            MaxPage=1,
            Gather_Content=True,
            interval=0,
        )

        sleep.assert_called_once_with(2)

    @patch("core.wx.base.RSS.clear_cache")
    def test_fulltext_failure_is_not_saved_or_marked_synced(self, _clear_cache):
        collector = self.make_collector()
        collector._get_mp_articles_page = Mock(return_value={
            "reviews": [{
                "subReviews": [{
                    "review": {
                        "reviewId": "MP_WXS_1_review-1",
                        "createTime": 1778580001,
                        "mpInfo": {
                            "title": "Article title",
                            "originalId": "abc~def",
                        },
                    }
                }]
            }]
        })
        collector._get_mp_content = Mock(
            side_effect=WereadMPAPIError(503, "content unavailable")
        )
        saved = []

        with self.assertRaises(WereadMPAPIError) as caught:
            collector.get_Articles(
                Mps_id="MP_WXS_1",
                Mps_title="Feed title",
                CallBack=lambda article: saved.append(article) or True,
                MaxPage=1,
                Gather_Content=True,
                interval=0,
            )

        self.assertEqual(caught.exception.code, "content_incomplete")
        self.assertEqual(saved, [])
        collector.update_mps.assert_not_called()

if __name__ == "__main__":
    unittest.main()
