import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from core.config import cfg

cfg.config["db"] = "sqlite:////tmp/werss-content-queue-import.db"

from core import article_content
from core.models.article import Article
from core.models.base import Base, DATA_STATUS

module_spec = importlib.util.spec_from_file_location(
    "fetch_no_article_under_test",
    Path(__file__).parents[1] / "jobs" / "fetch_no_article.py",
)
fetch_no_article = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(fetch_no_article)


def config_value(key, default=None):
    values = {
        "gather.content_batch_size": 2,
        "gather.content_fetch_stale_timeout": 300,
        "gather.content_max_failures": 3,
        "gather.content_mode": "web",
    }
    return values.get(key, default)


WECHAT_SHELL = """
<p>知道了 取消 允许</p>
<p>微信扫一扫可打开此内容，使用完整服务</p>
<p>视频 小程序 赞 在看 分享 留言 收藏 听过</p>
"""


class ContentFetchQueueTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.config_patch = patch.object(cfg, "get", side_effect=config_value)
        self.config_patch.start()

    def tearDown(self):
        self.config_patch.stop()
        self.session.close()
        self.engine.dispose()

    def add_article(self, article_id, **values):
        defaults = {
            "id": article_id,
            "title": article_id,
            "url": f"https://mp.weixin.qq.com/s/{article_id}",
            "publish_time": 1,
            "status": DATA_STATUS.ACTIVE,
            "has_content": 0,
            "fix_fail_count": 0,
        }
        defaults.update(values)
        article = Article(**defaults)
        self.session.add(article)
        self.session.commit()
        return article

    def test_recovers_legacy_and_stale_locks_but_not_fresh_lock(self):
        now_millis = 1_000_000
        self.add_article(
            "legacy",
            status=DATA_STATUS.FETCHING,
            fetch_started_at=None,
        )
        self.add_article(
            "stale",
            status=DATA_STATUS.FETCHING,
            fetch_started_at=600_000,
        )
        self.add_article(
            "fresh",
            status=DATA_STATUS.FETCHING,
            fetch_started_at=900_000,
        )

        recovered = fetch_no_article.recover_stale_fetching_articles(
            self.session,
            now_millis=now_millis,
        )

        self.assertEqual(recovered, 2)
        for article_id in ("legacy", "stale"):
            article = self.session.get(Article, article_id)
            self.assertEqual(article.status, DATA_STATUS.ACTIVE)
            self.assertEqual(article.fix_fail_count, 1)
            self.assertIsNone(article.fetch_started_at)
        fresh = self.session.get(Article, "fresh")
        self.assertEqual(fresh.status, DATA_STATUS.FETCHING)
        self.assertEqual(fresh.fix_fail_count, 0)
        self.assertEqual(fresh.fetch_started_at, 900_000)

    def test_claims_only_one_article(self):
        self.add_article("older", publish_time=1)
        self.add_article("newer", publish_time=2)

        claimed = fetch_no_article.claim_next_article(
            self.session,
            now_millis=123_000,
        )

        self.assertEqual(claimed.id, "newer")
        self.assertEqual(claimed.status, DATA_STATUS.FETCHING)
        self.assertEqual(claimed.fetch_started_at, 123_000)
        self.assertEqual(self.session.get(Article, "older").status, DATA_STATUS.ACTIVE)

    def test_legacy_table_gets_fetch_started_at_column(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE articles (id VARCHAR(255) PRIMARY KEY)"))

        database = fetch_no_article.db.Db.__new__(fetch_no_article.db.Db)
        database.engine = engine
        database.tag = "test"
        database.ensure_article_columns()

        columns = {column["name"] for column in inspect(engine).get_columns("articles")}
        self.assertIn("fetch_started_at", columns)
        engine.dispose()

    def test_empty_fetch_increments_failure_and_releases_lock(self):
        article = self.add_article(
            "empty",
            status=DATA_STATUS.FETCHING,
            fetch_started_at=123_000,
        )

        with patch.object(
            article_content,
            "fetch_article_content",
            return_value=("", "web", ""),
        ):
            updated, mode = article_content.sync_article_content(
                self.session,
                article,
            )

        self.assertFalse(updated)
        self.assertEqual(mode, "web")
        self.assertEqual(article.fix_fail_count, 1)
        self.assertEqual(article.status, DATA_STATUS.ACTIVE)
        self.assertIsNone(article.fetch_started_at)

    def test_failed_forced_refresh_preserves_existing_content(self):
        article = self.add_article(
            "existing",
            content="<p>existing body</p>",
            has_content=1,
        )

        with patch.object(
            article_content,
            "fetch_article_content",
            return_value=("", "web", ""),
        ):
            updated, _ = article_content.sync_article_content(
                self.session,
                article,
                force=True,
            )

        self.assertFalse(updated)
        self.assertEqual(article.content, "<p>existing body</p>")
        self.assertEqual(article.has_content, 1)
        self.assertEqual(article.status, DATA_STATUS.ACTIVE)

    def test_failed_refresh_does_not_preserve_wechat_shell_as_content(self):
        article = self.add_article(
            "shell",
            content=WECHAT_SHELL,
            has_content=1,
        )

        with patch.object(
            article_content,
            "fetch_article_content",
            return_value=("", "api", ""),
        ):
            updated, _ = article_content.sync_article_content(
                self.session,
                article,
                force=True,
            )

        self.assertFalse(updated)
        self.assertEqual(article.has_content, 0)
        self.assertEqual(article.status, DATA_STATUS.ACTIVE)

    def test_wechat_shell_is_not_usable_article_content(self):
        self.assertFalse(article_content.is_usable_article_content(WECHAT_SHELL))
        self.assertTrue(
            article_content.is_usable_article_content(
                '<div id="js_content"><p>real article body</p></div>'
            )
        )

    def test_api_fetch_extracts_only_article_container(self):
        response_html = """
        <html><body>
          <div>page chrome</div>
          <div id="js_content"><p>article body</p></div>
        </body></html>
        """
        with patch(
            "core.wx.model.api.MpsApi.content_extract",
            return_value=response_html,
        ):
            content, metadata = article_content._fetch_with_api(
                "https://example.com/article"
            )

        self.assertIn("article body", content)
        self.assertNotIn("page chrome", content)
        self.assertEqual(metadata, {})

    def test_api_fetch_rejects_page_without_article_container(self):
        with patch(
            "core.wx.model.api.MpsApi.content_extract",
            return_value="<html><body>未知错误，请稍后再试</body></html>",
        ):
            content, _ = article_content._fetch_with_api(
                "https://example.com/article"
            )

        self.assertEqual(content, "")

    def test_unusable_web_result_falls_back_to_api(self):
        with (
            patch.object(
                article_content,
                "_fetch_with_web",
                return_value=(WECHAT_SHELL, {}),
            ),
            patch.object(
                article_content,
                "_fetch_with_api",
                return_value=("<p>real article body</p>", {}),
            ),
        ):
            content, mode, _ = article_content._fetch_article_content_unbounded(
                "https://example.com/article",
                preferred_mode="web",
                allow_fallback=True,
            )

        self.assertEqual(content, "<p>real article body</p>")
        self.assertEqual(mode, "api")

    def test_api_only_mode_does_not_fall_back_to_web(self):
        with (
            patch.object(article_content, "_fetch_with_api", return_value=("", {})),
            patch.object(article_content, "_fetch_with_web") as web_fetch,
        ):
            content, mode, _ = article_content._fetch_article_content_unbounded(
                "https://example.com/article",
                preferred_mode="api",
                allow_fallback=False,
            )

        self.assertEqual(content, "")
        self.assertEqual(mode, "api")
        web_fetch.assert_not_called()

    def test_failed_article_does_not_prevent_next_batch_item(self):
        self.add_article("first", publish_time=2)
        self.add_article("second", publish_time=1)
        processed_ids = []

        def fail_fetch(session, article, preferred_mode=None):
            processed_ids.append(article.id)
            article.status = DATA_STATUS.ACTIVE
            article.fetch_started_at = None
            article.fix_fail_count += 1
            session.commit()
            return False, "web"

        with (
            patch.object(
                fetch_no_article,
                "DB",
                SimpleNamespace(get_session=self.Session),
            ),
            patch.object(fetch_no_article, "sync_article_content", side_effect=fail_fetch),
            patch.object(fetch_no_article, "Wait"),
        ):
            fetch_no_article.fetch_articles_without_content()

        self.assertEqual(processed_ids, ["first", "second"])


if __name__ == "__main__":
    unittest.main()
