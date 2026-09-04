"""Collect WeChat Official Account articles through WeRead Web."""

import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from core.log import logger
from core.models.feed import Feed
from core.print import print_info, print_warning
from core.wx.model.weread import MpsWeread


WEREAD_WEB_BASE = "https://weread.qq.com"


class WereadMPAPIError(Exception):
    def __init__(self, code, message, retriable=True):
        super().__init__(f"WeRead MP API error {code}: {message}")
        self.code = code
        self.message = message
        self.retriable = retriable


def build_mp_url(original_id: str) -> str:
    original_id = str(original_id or "").strip()
    if not original_id:
        return ""
    # 注意：微信文章短链 token 中可能含 '~'（如 4OcS7~rrtk2Lwe4P0YPiGg），
    # 这是合法字符，必须原样保留。若替换为 '_'，微信会 302 跳转、部分阅读器无法打开。
    article_token = quote(original_id, safe="~")
    return f"https://mp.weixin.qq.com/s/{article_token}"


def build_mp_link_from_review_id(review_id: str, book_id: str = "") -> str:
    """从 WeRead 的 reviewId 推导公众号原文链接。

    reviewId 形如 ``MP_WXS_<bookId>_<articleToken>``，末尾段即为
    mp.weixin.qq.com 原文短链的 token。token 中可能含 ``~``（如
    ``4OcS7~rrtk2Lwe4P0YPiGg``），须原样保留。新版接口 ``/api/mp/cover``
    不返回 originalId，只能由此推导。
    """
    review_id = str(review_id or "").strip()
    if not review_id:
        return ""
    token = review_id
    prefix = f"{book_id}_" if book_id else ""
    if prefix and review_id.startswith(prefix):
        token = review_id[len(prefix):]
    elif "_" in token:
        token = token.split("_")[-1]
    return f"https://mp.weixin.qq.com/s/{quote(token, safe='~')}"


def _raise_response_error(payload: dict):
    code = payload.get("errCode", payload.get("errcode", 0))
    try:
        code = int(code or 0)
    except (TypeError, ValueError):
        code = 0
    if code == 0:
        return
    message = payload.get("errMsg") or payload.get("errmsg") or str(code)
    raise WereadMPAPIError(
        code,
        message,
        retriable=code not in (-2041, -2012, -2010),
    )


def parse_mp_articles(payload: dict):
    if not isinstance(payload, dict):
        raise WereadMPAPIError("invalid_response", "response is not an object")
    _raise_response_error(payload)

    groups = payload.get("reviews", []) or []
    articles = []
    for group in groups:
        group_time = group.get("createTime", 0)
        for sub_review in group.get("subReviews", []) or []:
            review = sub_review.get("review") or {}
            mp_info = review.get("mpInfo") or {}
            review_id = review.get("reviewId") or sub_review.get("reviewId")
            if not review_id:
                continue
            create_time = review.get("createTime") or group_time or 0
            update_time = mp_info.get("time") or create_time
            articles.append({
                "aid": review_id,
                "id": review_id,
                "title": mp_info.get("title", ""),
                "link": build_mp_url(mp_info.get("originalId", "")),
                "cover": mp_info.get("pic_url", ""),
                "digest": mp_info.get("content") or review.get("content", ""),
                "content": "",
                "create_time": create_time,
                "update_time": update_time,
                "read_num": mp_info.get("readNum", 0),
                "like_num": mp_info.get("likeNum", 0),
                "item_show_type": 0,
            })
    return articles, len(groups)


def extract_mp_content(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    content = soup.select_one("#js_content") or soup.select_one(".rich_media_content")
    if content is None:
        raise WereadMPAPIError("invalid_content", "article body was not found")
    for element in content.select("script, style"):
        element.decompose()
    return content.decode_contents().strip()


class MpsWereadMP(MpsWeread):
    """WeRead-backed collector for existing ``MP_WXS_*`` feeds."""

    def _get_feed_update_time(self, mp_id: str) -> int:
        from core.db import DB

        session = DB.get_session()
        try:
            row = session.query(Feed.update_time).filter(Feed.id == mp_id).first()
            return int(row[0] or 0) if row else 0
        finally:
            session.close()

    def _get_catchup_page_limit(self, requested_pages: int) -> int:
        from core.config import cfg

        configured_limit = int(cfg.get("weread.mp_max_pages", 20) or 20)
        return max(requested_pages, configured_limit, 1)

    def _get_content_interval(self) -> float:
        from core.config import cfg

        return max(float(cfg.get("weread.content_interval", 2) or 0), 0)

    def _get_page_interval(self) -> float:
        from core.config import cfg

        return max(float(cfg.get("weread.page_interval", 1) or 0), 0)

    def _request_headers(self, include_ticket=False):
        headers = {
            "Cookie": self._weread_cookies,
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": "https://weread.qq.com",
            "Referer": "https://weread.qq.com/",
        }
        if include_ticket and self._weread_ticket:
            # 新版微信读书已弃用 x-wr-ticket，仅需有效 Cookie 即可拉取文章列表；
            # 保留旧逻辑以便兼容旧版微信读书。无 ticket 时不拦截请求。
            headers["x-wr-ticket"] = self._weread_ticket
        return headers

    def _get_mp_articles_page(self, book_id: str, offset=0):
        # /web/mp/articles 曾在部分旧 Cookie 上返回 -2041，当时据此回退到 cover 方案；
        # 实测该列表接口可用，是增量补抓的主路径。失败时由 get_Articles 回退 cover。
        try:
            response = requests.get(
                f"{WEREAD_WEB_BASE}/web/mp/articles",
                params={"bookId": book_id, "offset": offset},
                headers=self._request_headers(include_ticket=True),
                proxies=self._get_proxies(),
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            raise WereadMPAPIError("network_error", str(exc)) from exc
        if response.status_code != 200:
            raise WereadMPAPIError(
                response.status_code,
                f"article list returned HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise WereadMPAPIError("invalid_json", "article list is not JSON") from exc
        if not isinstance(payload, dict):
            raise WereadMPAPIError("invalid_response", "article list is not an object")
        _raise_response_error(payload)
        return payload

    def _get_mp_cover(self, book_id: str) -> dict:
        """获取公众号最新一篇文章（列表接口不可用时的兜底入口）。

        返回: {"name", "title", "pic", "reviewId", ...}；无文章或接口异常时抛错。
        """
        try:
            response = requests.get(
                f"{WEREAD_WEB_BASE}/api/mp/cover",
                params={"bookId": book_id},
                headers=self._request_headers(),
                proxies=self._get_proxies(),
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            raise WereadMPAPIError("network_error", str(exc)) from exc
        if response.status_code != 200:
            raise WereadMPAPIError(
                response.status_code,
                f"mp cover returned HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise WereadMPAPIError("invalid_json", "mp cover is not JSON") from exc
        if not isinstance(payload, dict):
            raise WereadMPAPIError("invalid_response", "mp cover is not an object")
        if not payload.get("reviewId"):
            _raise_response_error(payload)
            raise WereadMPAPIError(
                "empty_cover",
                "公众号未返回最新文章（可能从未在微信读书内发布过文章）",
                retriable=False,
            )
        return payload

    def _is_article_gathered(self, mp_id: str, review_id: str) -> bool:
        """判断 reviewId 是否已入库（跨会话增量，避免重复推送）。

        Article.id 存储格式为 ``{mp_id}-{aid}`` 并去掉 ``MP_WXS_`` 前缀，
        与 ``Db.add_article`` 的归一化规则保持一致。
        """
        if not mp_id or not review_id:
            return False
        from core.db import DB
        from core.models.article import Article

        session = DB.get_session()
        try:
            stored_id = f"{mp_id}-{review_id}".replace("MP_WXS_", "")
            row = session.query(Article.id).filter(
                Article.mp_id == mp_id,
                Article.id == stored_id,
            ).first()
            return row is not None
        except Exception:
            return False
        finally:
            session.close()

    def _get_mp_content(self, review_id: str):
        headers = self._request_headers()
        headers["Accept"] = "text/html,application/xhtml+xml,*/*"
        try:
            response = requests.get(
                f"{WEREAD_WEB_BASE}/web/mp/content",
                params={"reviewId": review_id},
                headers=headers,
                proxies=self._get_proxies(),
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            raise WereadMPAPIError("network_error", str(exc)) from exc
        if response.status_code != 200:
            raise WereadMPAPIError(
                response.status_code,
                f"article content returned HTTP {response.status_code}",
            )
        return extract_mp_content(response.text)

    def _collect_latest_via_cover(
        self,
        book_id: str,
        Mps_id: str,
        Mps_title: str,
        gather_content: bool,
        CallBack=None,
        Item_Over_CallBack=None,
    ) -> int:
        """兜底方案：通过 /api/mp/cover 只采集最新一篇文章。"""
        cover = self._get_mp_cover(book_id)
        review_id = (cover.get("reviewId") or "").strip()
        title = (cover.get("title") or "").strip()
        self.response_valid = True

        if not review_id:
            raise WereadMPAPIError(
                "empty_cover",
                f"公众号「{Mps_title}」暂无文章",
                retriable=False,
            )

        # 跨会话增量：最新文章已入库则无需重复采集
        if self._is_article_gathered(Mps_id, review_id):
            print_info(f"无新文章：最新《{title}》已在库中，跳过")
            return self._get_feed_update_time(Mps_id)

        print_info(f"发现新文章: {title}")
        item = {
            "aid": review_id,
            "id": review_id,
            "title": title,
            "link": build_mp_link_from_review_id(review_id, book_id),
            "cover": cover.get("pic") or "",
            "digest": cover.get("digest") or "",
            "content": "",
            "create_time": int(time.time()),
            "update_time": int(time.time()),
            "read_num": 0,
            "like_num": 0,
            "item_show_type": 0,
            "copyright_stat": 1,
            "mp_id": Mps_id,
        }
        if gather_content:
            content_interval = self._get_content_interval()
            if content_interval:
                time.sleep(content_interval)
            try:
                item["content"] = self._get_mp_content(review_id)
            except WereadMPAPIError as exc:
                logger.warning(f"微信读书正文获取失败 [{review_id}]: {exc}")
        if CallBack is not None:
            super().FillBack(
                CallBack=CallBack,
                data=item,
                Ext_Data={"mp_title": Mps_title, "mp_id": Mps_id},
            )
        if Item_Over_CallBack is not None:
            Item_Over_CallBack(item)
        return int(item["update_time"])

    def _collect_via_article_list(
        self,
        book_id: str,
        Mps_id: str,
        Mps_title: str,
        gather_content: bool,
        start_page: int,
        MaxPage: int,
        CallBack=None,
        Item_Over_CallBack=None,
    ) -> int:
        """增量补抓：翻页扫描文章列表，采集所有尚未入库的文章。

        停止条件（满足其一即停止翻页）：
        - 遇到已入库的文章（``_is_article_gathered``，以 articles 表为已采记录的唯一权威）
        - 列表翻完（空页）或达到 ``weread.mp_max_pages`` 页数上限

        注意：不以 ``Feed.update_time`` 作为停止边界。cover 兜底模式会把
        **抓取时间**（而非文章发布时间）写入 update_time，若按时间停止，
        cover 时代漏采的文章（发布早于上次抓取、但不是当时最新一篇）将被永久
        跳过。以入库记录为边界可以在 cover → 列表切换后一次性补齐这些漏采文章，
        稳态下第一页就会命中已入库文章，效率不受影响。

        翻页间隔 ``weread.page_interval``、正文请求间隔 ``weread.content_interval``
        用于控制请求频率，避免触发微信读书流控。
        """
        start_page = max(int(start_page or 0), 0)
        end_page = max(int(MaxPage or 1), start_page + 1)
        offset = start_page
        latest_publish_time = 0
        content_failures = []
        previous_update_time = self._get_feed_update_time(Mps_id)
        requested_pages = end_page - start_page
        page_limit = (
            self._get_catchup_page_limit(requested_pages)
            if previous_update_time
            else requested_pages
        )
        reached_gathered = not previous_update_time
        content_request_count = 0
        content_interval = self._get_content_interval()
        page_interval = self._get_page_interval()
        new_count = 0

        for page in range(start_page, start_page + page_limit):
            if page > start_page and page_interval:
                time.sleep(page_interval)
            payload = self._get_mp_articles_page(book_id, offset=offset)
            articles, group_count = parse_mp_articles(payload)
            self.response_valid = True

            for item in articles:
                if super().HasGathered(item["aid"]):
                    continue
                publish_time = int(item.get("update_time") or item.get("create_time") or 0)
                if self._is_article_gathered(Mps_id, item["aid"]):
                    reached_gathered = True
                    continue
                item["mp_id"] = Mps_id
                latest_publish_time = max(latest_publish_time, publish_time)
                if gather_content:
                    if content_request_count and content_interval:
                        time.sleep(content_interval)
                    content_request_count += 1
                    try:
                        item["content"] = self._get_mp_content(item["aid"])
                    except WereadMPAPIError as exc:
                        logger.warning(f"微信读书正文获取失败 [{item['aid']}]: {exc}")
                        content_failures.append(item["aid"])
                        continue
                if CallBack is not None:
                    super().FillBack(
                        CallBack=CallBack,
                        data=item,
                        Ext_Data={"mp_title": Mps_title, "mp_id": Mps_id},
                    )
                if Item_Over_CallBack is not None:
                    Item_Over_CallBack(item)
                new_count += 1

            if group_count == 0:
                reached_gathered = True
                break
            # WeRead defines offset in top-level review groups, not subReviews.
            offset += group_count
            if previous_update_time and reached_gathered:
                break

        if content_failures:
            raise WereadMPAPIError(
                "content_incomplete",
                f"{len(content_failures)} article bodies could not be fetched",
            )
        if not reached_gathered:
            raise WereadMPAPIError(
                "backlog_incomplete",
                f"catch-up did not reach any gathered article after {page_limit} pages",
            )

        print_info(f"[{Mps_title}] 增量补抓完成: 新增 {new_count} 篇")
        return latest_publish_time or previous_update_time

    def get_Articles(
        self,
        faker_id: str = None,
        Mps_id: str = None,
        Mps_title="",
        CallBack=None,
        start_page: int = 0,
        MaxPage: int = 1,
        interval=10,
        Gather_Content=False,
        Item_Over_CallBack=None,
        Over_CallBack=None,
    ):
        """Collect one existing WeChat feed without changing its RSS identity.

        主路径走 ``/web/mp/articles`` 列表接口做增量补抓：从最新一页开始翻页，
        采集所有尚未入库的文章，遇到已入库文章即停止（上一轮到这一轮之间漏采的
        文章会一并补齐）。列表接口不可用（如 -2012 登录超时 / -2041 等）时回退到
        ``/api/mp/cover`` 只取最新一篇的兜底逻辑，保证采集不中断。
        """
        self.articles = []
        self.aids = []
        self.get_token()
        self.start_time = time.time()
        self.response_valid = False
        self.last_error = None
        self._load_weread_auth()

        if not self._weread_cookies:
            raise WereadMPAPIError(
                "missing_cookie",
                "WEREAD_COOKIE is required",
                retriable=False,
            )

        book_id = Mps_id if str(Mps_id or "").startswith("MP_WXS_") else faker_id
        if not str(book_id or "").startswith("MP_WXS_"):
            raise WereadMPAPIError(
                "invalid_book_id",
                "the feed id must use the MP_WXS_ prefix",
                retriable=False,
            )

        # 未在微信读书书架上的公众号自动添加到书架（关注），保证采集可用。
        # 失败仅告警不中断：采集接口会给出最终结果。
        try:
            ok, detail = self.ensure_mp_on_shelf(book_id, Mps_title)
            if ok:
                print_info(f"[{Mps_title}] 书架检查: {detail}")
            else:
                print_warning(f"[{Mps_title}] 书架检查失败: {detail}")
        except Exception as exc:
            print_warning(f"[{Mps_title}] 书架检查异常: {exc}")

        gather_content = bool(Gather_Content or self.Gather_Content)

        print_info(f"微信读书公众号采集模式: {Mps_title} ({book_id})")
        try:
            try:
                latest_publish_time = self._collect_via_article_list(
                    book_id,
                    Mps_id,
                    Mps_title,
                    gather_content,
                    start_page,
                    MaxPage,
                    CallBack=CallBack,
                    Item_Over_CallBack=Item_Over_CallBack,
                )
            except WereadMPAPIError as exc:
                if self.response_valid:
                    # 列表接口本身可用（已成功翻页），属于正文缺失或补抓不完整
                    # 等真实错误，直接上抛，下次任务重试。
                    raise
                print_warning(
                    f"[{Mps_title}] 文章列表接口不可用({exc})，回退到仅取最新一篇"
                )
                latest_publish_time = self._collect_latest_via_cover(
                    book_id,
                    Mps_id,
                    Mps_title,
                    gather_content,
                    CallBack=CallBack,
                    Item_Over_CallBack=Item_Over_CallBack,
                )

            self.update_mps(
                Mps_id,
                Feed(
                    sync_time=int(time.time()),
                    update_time=latest_publish_time or None,
                ),
            )
        except Exception as exc:
            self.last_error = {
                "message": str(exc),
                "code": getattr(exc, "code", "weread_mp_error"),
                "retriable": getattr(exc, "retriable", True),
            }
            super().Over(CallBack=Over_CallBack)
            raise

        super().Over(CallBack=Over_CallBack)
