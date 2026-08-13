import threading
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status as fast_status, Query
from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.base import DATA_STATUS
from core.models.article import Article,ArticleBase
from sqlalchemy import and_, or_, desc
from .base import success_response, error_response
from core.config import cfg
from apis.base import format_search_kw
from core.print import print_warning, print_info, print_error, print_success
from core.cache import clear_cache_pattern
from tools.fix import fix_article
from core.article_content import sync_article_content
router = APIRouter(prefix=f"/articles", tags=["文章管理"])

_refresh_tasks = {}
_refresh_tasks_lock = threading.Lock()


def _set_refresh_task(task_id: str, data: dict):
    with _refresh_tasks_lock:
        _refresh_tasks[task_id] = data


def _get_active_refresh_task(article_id: str):
    with _refresh_tasks_lock:
        for task in _refresh_tasks.values():
            if task.get("article_id") != article_id:
                continue
            if task.get("status") in {"pending", "running"}:
                return dict(task)
    return None


def _run_refresh_article_task_wrapper(task_id: str, article_id: str):
    _run_refresh_article_task(task_id, article_id)


def _run_refresh_article_task(task_id: str, article_id: str):
    session = DB.get_session()
    try:
        _set_refresh_task(task_id, {
            "task_id": task_id,
            "article_id": article_id,
            "status": "running",
            "message": "任务执行中"
        })

        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            _set_refresh_task(task_id, {
                "task_id": task_id,
                "article_id": article_id,
                "status": "failed",
                "message": "文章不存在"
            })
            return

        updated, fetch_mode = sync_article_content(
            session=session,
            article=article,
            preferred_mode=cfg.get("gather.content_mode", "web"),
            force=True,
        )
        if not updated:
            _set_refresh_task(task_id, {
                "task_id": task_id,
                "article_id": article_id,
                "status": "failed",
                "message": f"文章刷新失败: {fetch_mode}"
            })
            return

        now_seconds = int(time.time())
        article.updated_at = now_seconds
        article.updated_at_millis = int(time.time() * 1000)
        session.commit()
        session.refresh(article)

        clear_cache_pattern("articles_list")
        clear_cache_pattern("article_detail")
        clear_cache_pattern("home_page")
        clear_cache_pattern("tag_detail")

        _set_refresh_task(task_id, {
            "task_id": task_id,
            "article_id": article_id,
            "status": "success",
            "message": (
                "文章已被发布者删除"
                if article.status == DATA_STATUS.DELETED
                else "文章刷新成功"
            ),
            "fetch_mode": fetch_mode,
            "updated_at": now_seconds
        })
    except Exception as e:
        session.rollback()
        _set_refresh_task(task_id, {
            "task_id": task_id,
            "article_id": article_id,
            "status": "failed",
            "message": f"文章刷新失败: {str(e)}"
        })
    finally:
        session.close()


    
@router.delete("/clean", summary="清理无效文章(MP_ID不存在于Feeds表中的文章)")
async def clean_orphan_articles(
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        from core.models.article import Article
        
        # 找出Articles表中mp_id不在Feeds表中的记录
        subquery = session.query(Feed.id).subquery()
        deleted_count = session.query(Article)\
            .filter(~Article.mp_id.in_(subquery))\
            .delete(synchronize_session=False)
        
        session.commit()
        
        # 清除相关缓存
        clear_cache_pattern("articles_list")
        clear_cache_pattern("home_page")
        clear_cache_pattern("tag_detail")
        
        return success_response({
            "message": "清理无效文章成功",
            "deleted_count": deleted_count
        })
    except Exception as e:
        session.rollback()
        print(f"清理无效文章错误: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="清理无效文章失败"
            )
        )
    finally:
        session.close()


@router.delete("/clean-old", summary="清理指定天数前的旧文章")
async def clean_old_articles(
    days: int = Query(3, ge=1, le=365, description="清理多少天前的文章，默认3天"),
    mp_id: str = Query(None, description="公众号ID，不指定则清理所有公众号"),
    dry_run: bool = Query(False, description="是否只预览不实际删除"),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    清理指定天数前的旧文章
    
    Args:
        days: 清理多少天前的文章，默认3天
        mp_id: 公众号ID，不指定则清理所有公众号
        dry_run: 是否只预览不实际删除（用于确认要删除的文章）
    
    Returns:
        删除结果，包含删除数量和预览信息
    """
    import time as time_module
    from datetime import datetime, timedelta
    
    session = DB.get_session()
    try:
        # 计算截止时间戳（N天前）
        cutoff_date = datetime.now() - timedelta(days=days)
        cutoff_timestamp = int(cutoff_date.timestamp())
        
        print_info(f"清理旧文章: 截止日期={cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}, 时间戳={cutoff_timestamp}")
        
        # 构建查询 - 只查询未删除的文章
        query = session.query(Article).filter(
            Article.publish_time < cutoff_timestamp,
            Article.status != DATA_STATUS.DELETED  # 排除已删除的文章
        )
        
        # 如果指定了公众号ID，只删除该公众号的文章
        if mp_id:
            query = query.filter(Article.mp_id == mp_id)
        
        # 先获取总数
        total_count = query.count()
        print_info(f"符合条件的文章总数: {total_count}")
        
        # 获取预览文章（最多100条）
        articles_to_delete = query.limit(100).all()
        
        # 调试：打印一些文章的时间信息
        if articles_to_delete:
            print_info(f"示例文章时间信息:")
            for i, article in enumerate(articles_to_delete[:5]):
                try:
                    if article.publish_time:
                        # 检查时间戳是否合理（秒级 vs 毫秒级）
                        if article.publish_time > 10000000000:  # 毫秒级时间戳
                            publish_date = datetime.fromtimestamp(article.publish_time / 1000)
                            print_info(f"  [{i}] 毫秒时间戳: {article.publish_time} -> {publish_date}")
                        else:
                            publish_date = datetime.fromtimestamp(article.publish_time)
                            print_info(f"  [{i}] 秒时间戳: {article.publish_time} -> {publish_date}")
                    else:
                        print_info(f"  [{i}] publish_time 为空")
                except Exception as e:
                    print_error(f"  [{i}] 时间解析失败: {article.publish_time}, 错误: {e}")
        
        # 预览信息
        preview = []
        for article in articles_to_delete[:20]:  # 最多显示20条预览
            try:
                if article.publish_time:
                    # 处理毫秒级时间戳
                    if article.publish_time > 10000000000:
                        publish_date = datetime.fromtimestamp(article.publish_time / 1000).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        publish_date = datetime.fromtimestamp(article.publish_time).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    publish_date = None
                    
                preview.append({
                    "id": article.id,
                    "title": article.title,
                    "mp_id": article.mp_id,
                    "publish_time": article.publish_time,
                    "publish_date": publish_date
                })
            except Exception as e:
                print_error(f"预览文章 {article.id} 时间解析失败: {e}")
                preview.append({
                    "id": article.id,
                    "title": article.title,
                    "mp_id": article.mp_id,
                    "publish_time": article.publish_time,
                    "publish_date": None
                })
        
        if dry_run:
            # 只预览，不实际删除
            return success_response({
                "message": f"预览：将删除 {total_count} 篇 {days} 天前的文章",
                "total_count": total_count,
                "cutoff_date": cutoff_date.strftime("%Y-%m-%d %H:%M:%S"),
                "cutoff_timestamp": cutoff_timestamp,
                "preview_count": len(preview),
                "preview": preview,
                "dry_run": True,
                "days": days
            })
        
        # 实际删除
        if cfg.get("article.true_delete", False):
            # 物理删除
            deleted_count = query.delete(synchronize_session=False)
        else:
            # 逻辑删除（更新状态为 DELETED）
            deleted_count = query.update(
                {Article.status: DATA_STATUS.DELETED},
                synchronize_session=False
            )
        
        session.commit()
        
        # 清除相关缓存
        clear_cache_pattern("articles_list")
        clear_cache_pattern("article_detail")
        clear_cache_pattern("home_page")
        clear_cache_pattern("tag_detail")
        
        return success_response({
            "message": f"成功删除 {deleted_count} 篇 {days} 天前的文章",
            "deleted_count": deleted_count,
            "cutoff_date": cutoff_date.strftime("%Y-%m-%d %H:%M:%S"),
            "days": days,
            "mp_id": mp_id,
            "physical_delete": cfg.get("article.true_delete", False)
        })
    except Exception as e:
        session.rollback()
        print_error(f"清理旧文章错误: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50001,
                message=f"清理旧文章失败: {str(e)}"
            )
        )
    finally:
        session.close()

@router.put("/{article_id}/read", summary="改变文章阅读状态")
async def toggle_article_read_status(
    article_id: str,
    is_read: bool = Query(..., description="阅读状态: true为已读, false为未读"),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.article import Article
        
        # 检查文章是否存在
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        
        # 更新阅读状态
        article.is_read = 1 if is_read else 0
        session.commit()
        
        # 清除相关缓存
        clear_cache_pattern("articles_list")
        clear_cache_pattern("article_detail")
        clear_cache_pattern("tag_detail")
        
        return success_response({
            "message": f"文章已标记为{'已读' if is_read else '未读'}",
            "is_read": is_read
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"更新文章阅读状态失败: {str(e)}"
            )
        )


@router.put("/{article_id}/favorite", summary="改变文章收藏状态")
async def toggle_article_favorite_status(
    article_id: str,
    is_favorite: bool = Query(..., description="收藏状态: true为收藏, false为取消收藏"),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )

        article.is_favorite = 1 if is_favorite else 0
        session.commit()

        clear_cache_pattern("articles_list")
        clear_cache_pattern("article_detail")
        clear_cache_pattern("tag_detail")

        return success_response({
            "message": "文章已收藏" if is_favorite else "已取消收藏",
            "is_favorite": is_favorite
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"更新文章收藏状态失败: {str(e)}"
            )
        )

@router.delete("/clean_duplicate_articles", summary="清理重复文章")
async def clean_duplicate(
    current_user: dict = Depends(get_current_user_or_ak)
):
    try:
        from tools.clean import clean_duplicate_articles
        (msg, deleted_count) =clean_duplicate_articles()
        return success_response({
            "message": msg,
            "deleted_count": deleted_count
        })
    except Exception as e:
        print(f"清理重复文章: {str(e)}")
        raise HTTPException(
            status_code=fast_status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="清理重复文章"
            )
        )


@router.api_route("", summary="获取文章列表",methods= ["GET", "POST"], operation_id="get_articles_list")
async def get_articles(
    offset: int = Query(0, ge=0),
    limit: int = Query(5, ge=1, le=100),
    status: str = Query(None, description="文章状态，多个用逗号分隔，如: updating,deleted"),
    search: str = Query(None),
    mp_id: str = Query(None),
    only_favorite: bool = Query(False),
    has_content: bool = Query(None, description="是否有正文: true=有, false=无, 不传=全部"),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:

        # 状态字符串到状态码的映射
        status_map = {
            'deleted': DATA_STATUS.DELETED,
            'updating': DATA_STATUS.FETCHING,
            'active': DATA_STATUS.ACTIVE,
            'inactive': DATA_STATUS.INACTIVE,
            'pending': DATA_STATUS.PENDING,
            'completed': DATA_STATUS.COMPLETED,
            'failed': DATA_STATUS.FAILED,
        }

        # 构建查询条件 - 使用 ArticleBase 模型（不包含 content 字段，加速查询）
        query = session.query(ArticleBase)

        # 支持多个状态值（逗号分隔），将字符串映射为状态码
        if status:
            status_list = [s.strip() for s in status.split(',') if s.strip()]
            status_codes = [status_map.get(s) for s in status_list if status_map.get(s) is not None]
            if status_codes:
                query = query.filter(Article.status.in_(status_codes))
            else:
                # 无有效状态码时，默认排除已删除
                query = query.filter(Article.status != DATA_STATUS.DELETED)
        else:
            query = query.filter(Article.status != DATA_STATUS.DELETED)
        if mp_id:
            query = query.filter(Article.mp_id == mp_id)
        if only_favorite:
            query = query.filter(Article.is_favorite == 1)
        # 支持 has_content 参数：true=有正文，false=无正文，None=不筛选
        if has_content is not None:
            if has_content:
                query = query.filter(Article.has_content == 1)
            else:
                query = query.filter(Article.has_content == 0)
        if search:
            query = query.filter(format_search_kw(search))
        
        # 获取总数
        total = query.count()
        query= query.order_by(Article.publish_time.desc()).offset(offset).limit(limit)
        # 分页查询（按发布时间降序）
        results = query.all()
        
        # 打印生成的 SQL 语句（包含分页参数）
        print_warning(query.statement.compile(compile_kwargs={"literal_binds": True}))
                       
        # 查询公众号名称
        from core.models.feed import Feed
        mp_names = {}
        for article in results:
            if article.mp_id and article.mp_id not in mp_names:
                feed = session.query(Feed).filter(Feed.id == article.mp_id).first()
                mp_names[article.mp_id] = feed.mp_name if feed else "未知公众号"

        # 合并公众号名称到文章列表
        article_list = []
        for article in results:
            article_dict = article.__dict__.copy()
            article_dict["mp_name"] = mp_names.get(article.mp_id, "未知公众号")
            article_dict["is_favorite"] = int(getattr(article, "is_favorite", 0) or 0)
            article_dict["has_content"] = int(getattr(article, "has_content", 0) or 0)
            article_list.append(article_dict)
        
        from .base import success_response
        return success_response({
            "list": article_list,
            "total": total
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取文章列表失败: {str(e)}"
            )
        )

@router.post("/{article_id}/refresh", summary="刷新单篇文章")
async def refresh_article(
    article_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        article_exists = session.query(Article.id).filter(Article.id == article_id).first()
        if not article_exists:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )

        active_task = _get_active_refresh_task(article_id)
        if active_task:
            return success_response(active_task, message="该文章已有刷新任务在执行")

        task_id = str(uuid4())
        task = {
            "task_id": task_id,
            "article_id": article_id,
            "status": "pending",
            "message": "任务已创建"
        }
        _set_refresh_task(task_id, task)

        threading.Thread(
            target=_run_refresh_article_task_wrapper,
            args=(task_id, article_id),
            daemon=True
        ).start()

        return success_response(task, message="已开始刷新，请稍后查看")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"文章刷新失败: {str(e)}"
            )
        )
    finally:
        session.close()


@router.get("/refresh/tasks/{task_id}", summary="查询文章刷新任务状态")
async def get_refresh_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    with _refresh_tasks_lock:
        task = _refresh_tasks.get(task_id)
    if not task:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(
                code=40404,
                message="刷新任务不存在"
            )
        )
    return success_response(task)


@router.get("/{article_id}", summary="获取文章详情")
def get_article_detail(
    article_id: str,
    content: bool = Query(False),
    # current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        article = session.query(Article).filter(Article.id==article_id).filter(Article.status != DATA_STATUS.DELETED).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        return success_response(article)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取文章详情失败: {str(e)}"
            )
        )   

@router.delete("/{article_id}", summary="删除文章")
async def delete_article(
    article_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.article import Article
        
        # 检查文章是否存在
        article = session.query(Article).filter(Article.id == article_id).first()
        if not article:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(
                    code=40401,
                    message="文章不存在"
                )
            )
        # 逻辑删除文章（更新状态为deleted）
        article.status = DATA_STATUS.DELETED
        if cfg.get("article.true_delete", False):
            session.delete(article)
        session.commit()

        # 清理缓存，确保已删除的文章不会继续显示
        clear_cache_pattern("articles_list")
        clear_cache_pattern("article_detail")
        clear_cache_pattern("home_page")
        clear_cache_pattern("tag_detail")

        return success_response(None, message="文章已标记为删除")
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"删除文章失败: {str(e)}"
            )
        )

@router.get("/{article_id}/next", summary="获取下一篇文章")
def get_next_article(
    article_id: str,
    content: bool = Query(False),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        # 获取当前文章的发布时间
        current_article = session.query(Article).filter(Article.id == article_id).first()
        if not current_article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="当前文章不存在"
                )
            )
        
        # 查询发布时间更晚的第一篇文章
        next_article = session.query(Article)\
            .filter(Article.publish_time > current_article.publish_time)\
            .filter(Article.status != DATA_STATUS.DELETED)\
            .filter(Article.mp_id == current_article.mp_id)\
            .order_by(Article.publish_time.asc())\
            .first()
        
        if not next_article:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(
                    code=40402,
                    message="没有下一篇文章"
                )
            )
        if content:
            updated, _ = sync_article_content(
                session=session,
                article=next_article,
                preferred_mode=cfg.get("gather.content_mode", "web"),
            )
            if updated:
                clear_cache_pattern("articles_list")
                clear_cache_pattern("article_detail")
                clear_cache_pattern("home_page")
                clear_cache_pattern("tag_detail")
        return success_response(fix_article(next_article))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取下一篇文章失败: {str(e)}"
            )
        )

@router.get("/{article_id}/prev", summary="获取上一篇文章")
def get_prev_article(
    article_id: str,
    content: bool = Query(False),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        # 获取当前文章的发布时间
        current_article = session.query(Article).filter(Article.id == article_id).first()
        if not current_article:
            raise HTTPException(
                status_code=fast_status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="当前文章不存在"
                )
            )
        
        # 查询发布时间更早的第一篇文章
        prev_article = session.query(Article)\
            .filter(Article.publish_time < current_article.publish_time)\
            .filter(Article.status != DATA_STATUS.DELETED)\
            .filter(Article.mp_id == current_article.mp_id)\
            .order_by(Article.publish_time.desc())\
            .first()
        
        if not prev_article:
            raise HTTPException(
                status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
                detail=error_response(
                    code=40403,
                    message="没有上一篇文章"
                )
            )
        if content:
            updated, _ = sync_article_content(
                session=session,
                article=prev_article,
                preferred_mode=cfg.get("gather.content_mode", "web"),
            )
            if updated:
                clear_cache_pattern("articles_list")
                clear_cache_pattern("article_detail")
                clear_cache_pattern("home_page")
                clear_cache_pattern("tag_detail")
        return success_response(fix_article(prev_article))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=fast_status.HTTP_406_NOT_ACCEPTABLE,
            detail=error_response(
                code=50001,
                message=f"获取上一篇文章失败: {str(e)}"
            )
        )
