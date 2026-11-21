from logging import info
import re
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.background import BackgroundTasks
from core.auth import get_current_user_or_ak
from core.db import DB
from core.wx import search_Biz
from driver.wx import Wx
from .base import success_response, error_response
from datetime import datetime
from core.config import cfg
from core.res import save_avatar_locally
from core.models.feed import FEATURED_MP_ID, FEATURED_MP_NAME, FEATURED_MP_INTRO
from core.models.base import DATA_STATUS
from core.cache import clear_cache_pattern
import io
import os
from jobs.article import UpdateArticle
from driver.wxarticle import WXArticleFetcher
import threading
from uuid import uuid4
router = APIRouter(prefix=f"/mps", tags=["公众号管理"])
# import core.db as db
# UPDB=db.Db("数据抓取")
# def UpdateArticle(art:dict):
#             return UPDB.add_article(art)


def build_featured_mp_item():
    now = datetime.now().isoformat()
    return {
        "id": FEATURED_MP_ID,
        "mp_name": FEATURED_MP_NAME,
        "mp_cover": "/static/logo.svg",
        "mp_intro": FEATURED_MP_INTRO,
        "status": 1,
        "created_at": now,
        "is_system": True
    }


_featured_article_tasks = {}
_featured_article_tasks_lock = threading.Lock()


def _set_featured_article_task(task_id: str, data: dict):
    with _featured_article_tasks_lock:
        _featured_article_tasks[task_id] = data


def _ensure_featured_feed(session):
    from core.models.feed import Feed

    featured_feed = session.query(Feed).filter(Feed.id == FEATURED_MP_ID).first()
    if featured_feed:
        return featured_feed

    now = datetime.now()
    featured_feed = Feed(
        id=FEATURED_MP_ID,
        mp_name=FEATURED_MP_NAME,
        mp_cover="",
        mp_intro=FEATURED_MP_INTRO,
        status=1,
        sync_time=0,
        update_time=0,
        created_at=now,
        updated_at=now,
        faker_id=FEATURED_MP_ID
    )
    session.add(featured_feed)
    return featured_feed


def _run_add_featured_article_task_wrapper(task_id: str, url: str):
    """包装器:在线程中运行 async 函数"""
    import asyncio
    asyncio.run(_run_add_featured_article_task(task_id, url))

async def _run_add_featured_article_task(task_id: str, url: str):
    session = DB.get_session()
    fetcher = None
    try:
        _set_featured_article_task(task_id, {
            "task_id": task_id,
            "url": url,
            "status": "running",
            "message": "任务执行中"
        })

        from core.models.article import Article

        target_url = str(url or "").strip()
        if not target_url:
            raise ValueError("请输入文章链接")

        fetcher = WXArticleFetcher()
        info = await fetcher.get_article_content(target_url)
        if not info or info.get("fetch_error"):
            raise ValueError(info.get("fetch_error") or "文章抓取失败，请检查链接或登录状态")

        if info.get("content") == "DELETED":
            raise ValueError("该文章暂不可访问或已删除")

        raw_article_id = info.get("id") or fetcher.extract_id_from_url(target_url)
        if not raw_article_id:
            raise ValueError("无法解析文章ID，请确认链接格式")

        _ensure_featured_feed(session)

        article_id = f"{FEATURED_MP_ID}-{raw_article_id}".replace("MP_WXS_", "")
        now = datetime.now()
        publish_time = info.get("publish_time")
        if not isinstance(publish_time, int):
            try:
                publish_time = int(publish_time)
            except Exception:
                publish_time = int(now.timestamp())

        article_data = {
            "title": info.get("title") or target_url,
            "description": info.get("description") or fetcher.get_description(info.get("content") or ""),
            "content": info.get("content") or "",
            "publish_time": publish_time,
            "url": target_url,
            "pic_url": info.get("topic_image") or info.get("pic_url") or "",
        }

        existing = session.query(Article).filter(Article.id == article_id).first()
        if existing:
            existing.mp_id = FEATURED_MP_ID
            existing.title = article_data["title"]
            existing.description = article_data["description"]
            existing.content = article_data["content"]
            existing.publish_time = article_data["publish_time"]
            existing.url = article_data["url"]
            existing.pic_url = article_data["pic_url"]
            existing.status = DATA_STATUS.ACTIVE
            existing.updated_at = int(now.timestamp())
            existing.updated_at_millis = int(now.timestamp() * 1000)
            created = False
        else:
            session.add(Article(
                id=article_id,
                mp_id=FEATURED_MP_ID,
                title=article_data["title"],
                description=article_data["description"],
                content=article_data["content"],
                publish_time=article_data["publish_time"],
                url=article_data["url"],
                pic_url=article_data["pic_url"],
                status=DATA_STATUS.ACTIVE,
                created_at=now,
                updated_at=int(now.timestamp()),
                updated_at_millis=int(now.timestamp() * 1000),
                is_read=0,
                is_favorite=0
            ))
            created = True

        session.commit()
        clear_cache_pattern("articles_list")
        clear_cache_pattern("article_detail")
        clear_cache_pattern("home_page")
        clear_cache_pattern("tag_detail")

        _set_featured_article_task(task_id, {
            "task_id": task_id,
            "url": target_url,
            "status": "success",
            "message": "精选文章添加成功" if created else "精选文章更新成功",
            "id": article_id,
            "mp_id": FEATURED_MP_ID,
            "mp_name": FEATURED_MP_NAME,
            "title": article_data["title"],
            "created": created
        })
    except Exception as e:
        session.rollback()
        _set_featured_article_task(task_id, {
            "task_id": task_id,
            "url": url,
            "status": "failed",
            "message": str(e)
        })
    finally:
        if fetcher is not None:
            try:
                await fetcher.Close()
            except Exception:
                pass
        session.close()


@router.get("/search/{kw}", summary="搜索公众号")
async def search_mp(
    kw: str = "",
    limit: int = 10,
    offset: int = 0,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        result = search_Biz(kw,limit=limit,offset=offset)
        data={
            'list':result.get('list') if result is not None else [],
            'page':{
                'limit':limit,
                'offset':offset
            },
            'total':result.get('total') if result is not None else 0
        }
        return success_response(data)
    except Exception as e:
        # requests 的异常信息里带有请求 URL，其中包含 token，打印前先脱敏
        safe_err = re.sub(r"(token=)[^&\s'\"]+", r"\1***", str(e))
        print(f"搜索公众号错误: {type(e).__name__}: {safe_err}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message=_search_mp_error_message(e),
            )
        )


def _search_mp_error_message(e: Exception) -> str:
    """按异常类型给出搜索失败提示，避免把网络错误误报为授权失效"""
    import requests
    from core.wx.base import WxAuthError, WxRateLimitError
    if isinstance(e, WxAuthError):
        return "搜索公众号失败,请重新扫码授权！"
    if isinstance(e, WxRateLimitError):
        return "搜索公众号过于频繁，已被微信限流，请稍后再试"
    if isinstance(e, requests.exceptions.RequestException):
        return f"无法连接微信公众平台（{type(e).__name__}），请检查网络或代理设置"
    return "搜索公众号失败，请查看服务日志"

@router.get("", summary="获取公众号列表")
async def get_mps(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    status: int = Query(None, description="状态筛选: 1=启用, 0=停用, 不传=全部"),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        query = session.query(Feed).filter(Feed.id != FEATURED_MP_ID)
        if kw:
            query = query.filter(Feed.mp_name.ilike(f"%{kw}%"))
        if status is not None:
            query = query.filter(Feed.status == status)
        total = query.count()
        mps = query.order_by(Feed.created_at.desc()).limit(limit).offset(offset).all()
        mps_list = [{
                "id": mp.id,
                "mp_name": mp.mp_name,
                "mp_cover": mp.mp_cover,
                "mp_intro": mp.mp_intro,
                "status": mp.status,
                "created_at": mp.created_at.isoformat()
            } for mp in mps]
        return success_response({
            "list": mps_list,
            "page": {
                "limit": limit,
                "offset": offset,
                "total": total
            },
            "total": total
        })
    except Exception as e:
        print(f"获取公众号列表错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="获取公众号列表失败"
            )
        )


@router.post("/featured/article", summary="添加精选文章")
async def add_featured_article(
    url: str = Body(..., embed=True, min_length=1),
    current_user: dict = Depends(get_current_user_or_ak)
):
    try:
        target_url = str(url or "").strip()
        if not target_url:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40001,
                    message="请输入文章链接"
                )
            )
        if "mp.weixin.qq.com/s/" not in target_url:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40002,
                    message="请输入有效的公众号文章链接"
                )
            )

        task_id = str(uuid4())
        _set_featured_article_task(task_id, {
            "task_id": task_id,
            "url": target_url,
            "status": "pending",
            "message": "任务已创建"
        })
        threading.Thread(
            target=_run_add_featured_article_task_wrapper,
            args=(task_id, target_url),
            daemon=True
        ).start()

        return success_response({
            "task_id": task_id,
            "url": target_url,
            "status": "pending"
        }, message="已开始添加/抓取，请稍后刷新查看结果")
    except HTTPException:
        raise
    except Exception as e:
        print(f"添加精选文章任务启动失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="添加精选文章失败"
            )
        )


@router.get("/featured/article/tasks/{task_id}", summary="查询精选文章添加任务状态")
async def get_featured_article_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    with _featured_article_tasks_lock:
        task = _featured_article_tasks.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(
                code=40404,
                message="任务不存在"
            )
        )
    return success_response(task)

@router.get("/update/{mp_id}", summary="更新公众号文章")
async def update_mps(
     mp_id: str,
     start_page: int = 0,
     end_page: int = 1,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
           return error_response(
                    code=40401,
                    message="请选择一个公众号"
                )
        import time
        sync_interval=cfg.get("sync_interval",60)
        if mp.update_time is None:
            mp.update_time=int(time.time())-sync_interval
        time_span=int(time.time())-int(mp.update_time)
        if time_span<sync_interval:
           return error_response(
                    code=40402,
                    message="请不要频繁更新操作",
                    data={"time_span":time_span}
                )
        # 同步采集，等待结果返回；失败时把真实原因透出给前端，
        # 避免「异步线程 + 异常被吞」导致前端只看到“刷新成功”但实际 0 篇入库。
        from core.wx import WxGather
        wx = WxGather().Model()
        try:
            wx.get_Articles(
                mp.faker_id,
                Mps_id=mp.id,
                Mps_title=mp.mp_name,
                CallBack=UpdateArticle,
                start_page=start_page,
                MaxPage=end_page,
            )
        except Exception as e:
            err = str(e)
            # 微信读书登录态失效等，给出可操作的明确提示
            hint = ""
            if any(k in err for k in ("401", "鉴权", "-2013", "-2012", "登录超时", "登录态")):
                hint = " 微信读书 Cookie 已失效，请到「微信读书管理」页重新扫码授权或更新 Cookie。"
            print(f"更新公众号文章失败 [{mp.mp_name}]: {err}")
            return error_response(
                code=50002,
                message=f"更新「{mp.mp_name}」失败: {err}{hint}",
                data={"mp_id": mp_id},
            )
        return success_response({
            "time_span":time_span,
            "list":wx.articles,
            "total":len(wx.articles),
            "mps":mp
        })
    except Exception as e:
        print(f"更新公众号文章: {str(e)}",e)
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message=f"更新公众号文章{str(e)}"
            )
        )

@router.get("/{mp_id}", summary="获取公众号详情")
async def get_mp(
    mp_id: str,
    # current_user: dict = Depends(get_current_user)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="公众号不存在"
                )
            )
        return success_response(mp)
    except Exception as e:
        print(f"获取公众号详情错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="获取公众号详情失败"
            )
        )
@router.post("/by_article", summary="通过文章链接获取公众号详情")
async def get_mp_by_article(
    url: str=Query(..., min_length=1),
    current_user: dict = Depends(get_current_user_or_ak)
):
    try:
        info = await WXArticleFetcher().get_article_content(url)
        
        if not info:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="公众号不存在"
                )
            )
        return success_response(info)
    except Exception as e:
        print(f"获取公众号详情错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="请输入正确的公众号文章链接"
            )
        )

@router.post("", summary="添加公众号")
async def add_mp(
    mp_name: str = Body(..., min_length=1, max_length=255),
    mp_cover: str = Body(None, max_length=255),
    mp_id: str = Body(None, max_length=255),
    avatar: str = Body(None, max_length=500),
    mp_intro: str = Body(None, max_length=255),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        import time
        now = datetime.now()
        
        import base64
        mpx_id = base64.b64decode(mp_id).decode("utf-8")
        local_avatar_path = f"{save_avatar_locally(avatar)}"
        
        # 检查公众号是否已存在
        existing_feed = session.query(Feed).filter(Feed.faker_id == mp_id).first()
        
        if existing_feed:
            # 更新现有记录
            existing_feed.mp_name = mp_name
            existing_feed.mp_cover = local_avatar_path
            existing_feed.mp_intro = mp_intro
            existing_feed.updated_at = now
        else:
            # 创建新的Feed记录
            new_feed = Feed(
                id=f"MP_WXS_{mpx_id}",
                mp_name=mp_name,
                mp_cover= local_avatar_path,
                mp_intro=mp_intro,
                status=1,  # 默认启用状态
                created_at=now,
                updated_at=now,
                faker_id=mp_id,
                update_time=0,
                sync_time=0,
            )
            session.add(new_feed)
           
        session.commit()
        
        feed = existing_feed if existing_feed else new_feed
         #在这里实现第一次添加获取公众号文章
        if not existing_feed:
            from core.queue import TaskQueue
            from core.wx import WxGather
            Max_page=int(cfg.get("max_page","2"))
            TaskQueue.add_task(WxGather().Model().get_Articles, faker_id=feed.faker_id, Mps_id=feed.id, CallBack=UpdateArticle, MaxPage=Max_page, Mps_title=mp_name, task_name=mp_name)
            
        return success_response({
            "id": feed.id,
            "mp_name": feed.mp_name,
            "mp_cover": feed.mp_cover,
            "mp_intro": feed.mp_intro,
            "status": feed.status,
            "faker_id":mp_id,
            "created_at": feed.created_at.isoformat()
        })
    except Exception as e:
        session.rollback()
        print(f"添加公众号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="添加公众号失败"
            )
        )


@router.delete("/{mp_id}", summary="删除订阅号")
async def delete_mp(
    mp_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="订阅号不存在"
                )
            )
        
        session.delete(mp)
        session.commit()
        return success_response({
            "message": "订阅号删除成功",
            "id": mp_id
        })
    except Exception as e:
        session.rollback()
        print(f"删除订阅号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="删除订阅号失败"
            )
        )

@router.put("/{mp_id}", summary="更新订阅号状态")
async def update_mp_status(
    mp_id: str,
    mp_name: str = Body(None),
    mp_cover: str = Body(None),
    mp_intro: str = Body(None),
    status: int = Body(None),
    current_user: dict = Depends(get_current_user_or_ak)
):
    session = DB.get_session()
    try:
        from core.models.feed import Feed
        mp = session.query(Feed).filter(Feed.id == mp_id).first()
        if not mp:
            raise HTTPException(
                status_code=status.HTTP_201_CREATED,
                detail=error_response(
                    code=40401,
                    message="订阅号不存在"
                )
            )
        
        if mp_name is not None:
            mp.mp_name = mp_name
        if mp_cover is not None:
            mp.mp_cover = mp_cover
        if mp_intro is not None:
            mp.mp_intro = mp_intro
        if status is not None:
            mp.status = status
        
        mp.updated_at = datetime.now()
        session.commit()
        
        return success_response({
            "message": "更新成功",
            "id": mp_id,
            "status": mp.status
        })
    except Exception as e:
        session.rollback()
        print(f"更新订阅号错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="更新订阅号失败"
            )
        )
