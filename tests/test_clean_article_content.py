import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.article_content import clean_article_content, sync_article_content
from core.rss import RSS, prepare_rss_articles, select_article_content


class FakeSession:
    def __init__(self):
        self.commit_count = 0

    def commit(self):
        self.commit_count += 1

    def refresh(self, _article):
        return None

    def rollback(self):
        return None


class CleanArticleContentTest(unittest.TestCase):
    @patch("tools.fix.fix_html", return_value="<p>clean body</p>")
    def test_clean_article_content_uses_normalized_body(self, fix_html):
        result = clean_article_content("<html><script>large payload</script></html>")

        self.assertEqual(result, "<p>clean body</p>")
        fix_html.assert_called_once()

    @patch("tools.fix.fix_html", return_value="<p>clean body</p>")
    @patch(
        "core.article_content.fetch_article_content",
        return_value=("<html><script>large payload</script></html>", "web", ""),
    )
    def test_sync_stores_only_cleaned_content(self, _fetch, _fix_html):
        article = SimpleNamespace(
            id="article-1",
            mp_id="feed-1",
            url="https://example.com/article",
            content="",
            content_html="",
            description="existing description",
            has_content=0,
            fix_fail_count=2,
            show_type=0,
            status=1,
        )
        session = FakeSession()

        updated, mode = sync_article_content(session, article)

        self.assertTrue(updated)
        self.assertEqual(mode, "web")
        self.assertEqual(article.content, "<p>clean body</p>")
        self.assertEqual(article.content_html, "<p>clean body</p>")
        self.assertEqual(article.has_content, 1)
        self.assertEqual(article.fix_fail_count, 0)
        self.assertEqual(session.commit_count, 1)

    def test_rss_prefers_cleaned_content_for_existing_rows(self):
        article = SimpleNamespace(
            content="<html><script>large payload</script></html>",
            content_html="<p>clean body</p>",
        )

        self.assertEqual(select_article_content(article), "<p>clean body</p>")

    @patch("core.rss.clean_article_content", return_value="<p>clean legacy body</p>")
    def test_rss_cleans_legacy_content_before_fallback(self, clean_content):
        article = SimpleNamespace(
            content="<!DOCTYPE html><script>large payload</script>",
            content_html=None,
        )

        self.assertEqual(select_article_content(article), "<p>clean legacy body</p>")
        clean_content.assert_called_once_with(article.content)

    @patch("core.rss.clean_article_content", side_effect=lambda content: content or "")
    def test_full_content_feed_omits_incomplete_articles(self, _clean_content):
        complete = SimpleNamespace(content="<p>body</p>", content_html=None)
        incomplete = SimpleNamespace(content="", content_html=None)
        articles = [("feed", complete), ("feed", incomplete)]

        prepared = prepare_rss_articles(articles, require_content=True)

        self.assertEqual(prepared, [("feed", complete, "<p>body</p>")])

    @patch("core.rss.clean_article_content", side_effect=lambda content: content or "")
    def test_summary_feed_keeps_incomplete_articles(self, _clean_content):
        incomplete = SimpleNamespace(content="", content_html=None)

        prepared = prepare_rss_articles([("feed", incomplete)], require_content=False)

        self.assertEqual(prepared, [("feed", incomplete, "")])

    @patch("core.rss.clean_article_content", side_effect=lambda content: content or "")
    def test_full_content_feed_omits_wechat_shell_page(self, _clean_content):
        shell_page = SimpleNamespace(
            content=(
                "<p>知道了 取消 允许</p>"
                "<p>微信扫一扫可打开此内容，使用完整服务</p>"
                "<p>视频 小程序 赞 在看 分享 留言 收藏 听过</p>"
            ),
            content_html=None,
        )

        prepared = prepare_rss_articles(
            [("feed", shell_page)],
            require_content=True,
        )

        self.assertEqual(prepared, [])

    def test_content_cache_receives_compact_body(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            rss = RSS(name="test", cache_dir=temp_dir)
            rss.content_cache_dir = temp_dir
            rss.cache_content("article-1", {"content": "<p>clean body</p>"})

            cached = rss.get_cached_content("article-1")

        self.assertEqual(cached["content"], "<p>clean body</p>")


if __name__ == "__main__":
    unittest.main()
