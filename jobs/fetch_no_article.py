from core.models.article import Article,DATA_STATUS
import core.db as db
from core.config import cfg
from core.wait import Wait
from core.print import print_success,print_error,print_warning
from core.article_content import (
    build_article_url,
    mark_article_fetch_failed,
    sync_article_content,
)
DB=db.Db(tag="内容修正")


def recover_stale_fetching_articles(session, now_millis: int = None) -> int:
    """Release expired or legacy FETCHING locks and account for the failure."""
    import time
    from sqlalchemy import case, func, or_

    now_millis = now_millis or int(time.time() * 1000)
    stale_seconds = int(cfg.get("gather.content_fetch_stale_timeout", 300) or 300)
    stale_before = now_millis - stale_seconds * 1000
    max_failures = int(cfg.get("gather.content_max_failures", 3) or 3)
    next_fail_count = func.coalesce(Article.fix_fail_count, 0) + 1

    recovered = session.query(Article).filter(
        Article.status == DATA_STATUS.FETCHING,
        or_(
            Article.fetch_started_at.is_(None),
            Article.fetch_started_at < stale_before,
        ),
    ).update(
        {
            Article.status: case(
                (next_fail_count >= max_failures, DATA_STATUS.FAILED),
                else_=DATA_STATUS.ACTIVE,
            ),
            Article.fix_fail_count: next_fail_count,
            Article.fetch_started_at: None,
        },
        synchronize_session=False,
    )
    session.commit()
    if recovered:
        print_warning(f"已恢复 {recovered} 篇陈旧 FETCHING 文章")
    return recovered


def claim_next_article(session, excluded_ids=None, now_millis: int = None):
    """Atomically claim one article immediately before it is fetched."""
    import time
    from sqlalchemy import or_

    excluded_ids = excluded_ids or set()
    max_failures = int(cfg.get("gather.content_max_failures", 3) or 3)

    while True:
        query = session.query(Article).filter(
            Article.has_content == 0,
            Article.status != DATA_STATUS.FETCHING,
            Article.status != DATA_STATUS.DELETED,
            or_(Article.fix_fail_count.is_(None), Article.fix_fail_count < max_failures),
        )
        if excluded_ids:
            query = query.filter(~Article.id.in_(excluded_ids))

        candidate = query.order_by(Article.publish_time.desc()).first()
        if candidate is None:
            return None

        claimed = session.query(Article).filter(
            Article.id == candidate.id,
            Article.has_content == 0,
            Article.status == candidate.status,
            or_(Article.fix_fail_count.is_(None), Article.fix_fail_count < max_failures),
        ).update(
            {
                Article.status: DATA_STATUS.FETCHING,
                Article.fetch_started_at: now_millis or int(time.time() * 1000),
            },
            synchronize_session=False,
        )
        session.commit()
        if claimed:
            session.expire_all()
            return session.query(Article).filter(Article.id == candidate.id).first()

        session.expire_all()


def fetch_articles_without_content():
    """
    查询content为空的文章，调用微信内容提取方法获取内容并更新数据库
    使用 FETCHING 状态锁定，防止多节点同时获取相同数据
    """
    session = DB.get_session()
    try:
        recover_stale_fetching_articles(session)
        batch_size = int(cfg.get("gather.content_batch_size", 5) or 5)
        processed_ids = set()

        for _ in range(batch_size):
            article = claim_next_article(session, excluded_ids=processed_ids)
            if article is None:
                if not processed_ids:
                    print_warning("暂无需要获取内容的文章")
                break

            processed_ids.add(article.id)
            article_id = article.id
            article_title = article.title
            try:
                url = build_article_url(article)
                print(f"正在处理文章: {article.title}, URL: {url}")
                
                # 获取内容
                updated, fetch_mode = sync_article_content(
                    session=session,
                    article=article,
                    preferred_mode=cfg.get("gather.content_mode", "web"),
                )
                if updated:
                    if article.status == DATA_STATUS.DELETED:
                        print_error(f"获取文章 {article.title} 内容已被发布者删除")
                    else:
                        print_success(f"成功更新文章 {article.title} 的内容, mode={fetch_mode} url: http://127.0.0.1:{cfg.get('port', 8001)}/views/article/{article.id}")
                else:
                    print_error(f"获取文章 {article.title} 内容失败, mode={fetch_mode}")
                Wait(min=5,max=10,tips=f"修正 {article.title}... 完成")
            except Exception as e:
                session.rollback()
                article = session.query(Article).filter(Article.id == article_id).first()
                if article and article.status == DATA_STATUS.FETCHING:
                    mark_article_fetch_failed(session, article, str(e))
                print_error(f"处理文章 {article_title} 时发生错误: {e}")
    except Exception as e:
        print_error(f"处理过程中发生错误: {e}")
        raise  # 重新抛出异常，让队列记录错误
    finally:
        session.close()
from core.task import TaskScheduler
from core.queue import ContentTaskQueue

scheduler = TaskScheduler()
def start_sync_content():
    """
    根据配置自动启动文章内容同步任务
    
    功能：
    - 检查是否启用了自动同步功能
    - 根据配置的间隔时间设置定时任务
    - 清除现有任务队列和调度器中的所有作业
    - 添加新的定时同步任务并启动调度器
    - 立即执行一次同步任务
    
    Args:
        无显式参数，从配置中读取以下设置：
        - gather.content_auto_check: 是否启用自动同步功能
        - gather.content_auto_interval: 同步间隔时间（分钟）
    
    Returns:
        None
    
    Raises:
        无显式异常抛出，但内部可能打印警告或成功信息
    """
    if not cfg.get("gather.content_auto_check",False):
        print_warning("自动检查并同步文章内容功能未启用")
        return
    interval=int(cfg.get("gather.content_auto_interval",10)) # 每隔多少分钟
    cron_exp=f"*/{interval} * * * *"
    # ContentTaskQueue.clear_queue()  # 已注释：避免清空消息任务队列
    scheduler.clear_all_jobs()
    def do_sync():
        ContentTaskQueue.add_task(fetch_articles_without_content, task_name="补抓文章内容")
    job_id=scheduler.add_cron_job(do_sync,cron_expr=cron_exp)
    print_success(f"已添自动同步文章内容任务: {job_id}")
    scheduler.start()
    # 立即执行一次
    do_sync()
    print_success("已添加首次执行任务到队列")
if __name__ == "__main__":
    fetch_articles_without_content()
