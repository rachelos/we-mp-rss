import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import cfg

cfg.config["db"] = "sqlite:////tmp/werss-refresh-task-import.db"

from apis import article as article_api
from core.models.article import Article
from core.models.base import Base, DATA_STATUS


class ArticleRefreshTaskTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        self.session.add(
            Article(
                id="article-id",
                title="article",
                url="https://mp.weixin.qq.com/s/article-id",
                content="",
                has_content=0,
                status=DATA_STATUS.ACTIVE,
            )
        )
        self.session.commit()
        article_api._refresh_tasks.clear()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_manual_refresh_uses_shared_sync_and_reports_timeout(self):
        with (
            patch.object(article_api.DB, "get_session", return_value=self.session),
            patch.object(
                article_api,
                "sync_article_content",
                return_value=(False, "timeout"),
            ) as sync_content,
        ):
            article_api._run_refresh_article_task("task-id", "article-id")

        sync_content.assert_called_once()
        self.assertTrue(sync_content.call_args.kwargs["force"])
        task = article_api._refresh_tasks["task-id"]
        self.assertEqual(task["status"], "failed")
        self.assertIn("timeout", task["message"])


if __name__ == "__main__":
    unittest.main()
