import asyncio
from pydantic import BaseModel

# 标准导入分组和顺序
# 1. 标准库导入
import uuid
from datetime import datetime
from typing import List, Optional
from core.print import print_error, print_info
# 2. 第三方库导入
from fastapi import APIRouter, Depends, HTTPException, status,Body,Query
from sqlalchemy.orm import Session

# 3. 本地应用/模块导入
from core.auth import get_current_user_or_ak
from core.db import DB
from core.models.message_task import MessageTask
from .base import success_response, error_response

router = APIRouter(prefix="/message_tasks", tags=["消息任务"])

@router.get("", summary="获取消息任务列表")
async def list_message_tasks(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[int] = None,
    current_user: dict = Depends(get_current_user_or_ak)
):
    db=DB.get_session()
    """
    获取消息任务列表
    
    参数:
        skip: 跳过的记录数，用于分页
        limit: 每页返回的最大记录数
        status: 可选，按状态筛选任务
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        包含消息任务列表的成功响应，或错误响应
        
    异常:
        数据库查询异常: 返回500内部服务器错误
    """
    try:
        db.expire_all()
        query = db.query(MessageTask)
        if status is not None:
            query = query.filter(MessageTask.status == status)
        
        total = query.count()
        message_tasks = query.offset(offset).limit(limit).all()
        
        return success_response({
            "list": message_tasks ,
            "page": {
                "limit": limit,
                "offset": offset
            },
            "total": total
        })
    except Exception as e:
        return error_response(code=500, message=str(e))

@router.get("/{task_id}", summary="获取单个消息任务详情")
async def get_message_task(
    task_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    db=DB.get_session()
    """
    获取单个消息任务详情
    
    参数:
        task_id: 消息任务ID
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        包含消息任务详情的成功响应，或错误响应
        
    异常:
        404: 消息任务不存在
        500: 数据库查询异常
    """
    try:
        message_task = db.query(MessageTask).filter(MessageTask.id == task_id).first()
        if not message_task:
            raise HTTPException(status_code=404, detail="Message task not found")
        return success_response(data=message_task)
    except Exception as e:
        return error_response(code=500, message=str(e))
@router.post("/message/test/{task_id}", summary="测试消息")
async def test_message_task(
    task_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    db=DB.get_session()
    """
    测试消息任务
    
    参数:
        task_id: 消息任务ID
        
    返回:
        包含测试结果的响应
        
    异常:
        404: 消息任务不存在
        500: 数据库查询异常
    """
    try:
        message_task = db.query(MessageTask).filter(MessageTask.id == task_id).first()
        if not message_task:
            raise HTTPException(status_code=404, detail="Message task not found")
        
        # 获取第一个订阅号进行测试
        from jobs.mps import get_feeds
        import json
        feeds = get_feeds(message_task)
        
        if not feeds or len(feeds) == 0:
            return error_response(code=400, message="没有可用的订阅号进行测试")
        
        feed = feeds[0]  # 使用第一个订阅号进行测试
        
        # 创建测试用的模拟文章数据
        from datetime import datetime, timedelta
        mock_articles = []
        for i in range(1, 10):
            mock_articles.append( {
            "id": f"test-article-00{i}",
            "mp_id": feed.id,
            "title": f"测试文章标题{i}",
            "pic_url": "https://via.placeholder.com/300x200",
            "url": f"https://example.com/test-article-{i}",
            "description": f"这是一篇测试文章的描述内容，用于测试消息任务功能是否正常。第{i}篇文章。",
            "publish_time": (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
            "content": "<p>这是测试文章的正文内容。</p>"
        })
        
        # 执行测试消息发送（web_hook函数内部会处理字典类型）
        from jobs.webhook import MessageWebHook, web_hook
        # 使用类型忽略注释，因为web_hook函数会处理字典和Article对象
        test_hook = MessageWebHook(  # type: ignore
            task=message_task,
            feed=feed,
            articles=mock_articles  # type: ignore
        )
        
        result = await asyncio.to_thread(web_hook, test_hook, is_test=True)
        
        return success_response(
            data={
                "task_id": task_id,
                "feed_name": feed.mp_name,
                "test_article": mock_articles[0],
                "result": result
            },
            message=f"测试消息已发送到 {feed.mp_name}"
        )
    except HTTPException:
        raise
    except Exception as e:
        print_error(e)
        return error_response(code=500, message=str(e))
@router.get("/{task_id}/run", summary="执行单个消息任务详情")
async def run_message_task(
    task_id: str,
    isTest:bool=Query(False),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    执行单个消息任务详情
    
    参数:
        task_id: 消息任务ID
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        包含消息任务详情的成功响应，或错误响应
        
    异常:
        404: 消息任务不存在
        500: 数据库查询异常
    """
    try:
        from jobs.mps import run, get_feeds, tracker
        import time as _time
        mps={
            "count":0,
            "list":[]
        }
        tasks=run(task_id,isTest=isTest)
        if not tasks:
            raise HTTPException(status_code=404, detail="Message task not found or has been deactivated")

        # 统计本次命中的订阅号数量（真实语义：订阅号数 ≠ 新增文章数）
        mp_count = 0
        for task in tasks:
            try:
                feeds = get_feeds(task)
                mp_count += len(feeds) if feeds else 0
                mps['list'].append([getattr(f, 'id', None) for f in (feeds or [])])
            except Exception as e:
                print_error(e)

        if isTest:
            mps["count"] = 1
            mps["message"] = "测试任务执行成功"
        else:
            # 同步等待本次任务在队列中执行完毕，再汇总真实新增文章数，
            # 避免把"订阅号数量"误报为"新增文章数"
            article_total = 0
            deadline = _time.time() + 60
            while _time.time() < deadline:
                all_done = True
                pending = False
                article_total = 0
                for task in tasks:
                    st = tracker.get_task_status(task.id)
                    if not st:
                        pending = True
                        all_done = False
                        break
                    total = st.get('total', 0)
                    done = st.get('completed', 0) + st.get('failed', 0)
                    article_total += sum(r.get('article_count', 0) for r in st.get('mp_results', []))
                    if total and done < total:
                        all_done = False
                if not pending and all_done:
                    break
                _time.sleep(2)
            mps["count"] = article_total
            mps["message"] = f"已触发 {mp_count} 个订阅号同步，本次新增 {article_total} 篇文章"

        return success_response(data=mps,message=mps["message"])

    except Exception as e:
        print_error(e)
        return error_response(code=402, message=str(e))


class MessageTaskCreate(BaseModel):
    message_template: str
    web_hook_url: str
    mps_id: str=""
    name: str=""
    message_type: int=0
    cron_exp:str=""
    status: Optional[int] = 0
    headers: Optional[str] = ""
    cookies: Optional[str] = ""

@router.post("", summary="创建消息任务", status_code=status.HTTP_201_CREATED)
async def create_message_task(
    task_data: MessageTaskCreate = Body(...),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    创建新消息任务
    
    参数:
        task_data: 消息任务创建数据
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        201: 包含新创建消息任务的响应
        400: 请求数据验证失败
        500: 数据库操作异常
    """
    db=DB.get_session()
    try:
        db_task = MessageTask(
            id=str(uuid.uuid4()),
            message_template=task_data.message_template,
            web_hook_url=task_data.web_hook_url,
            cron_exp=task_data.cron_exp,
            mps_id=task_data.mps_id,
            message_type=task_data.message_type,
            name=task_data.name,
            status=task_data.status if task_data.status is not None else 0,
            headers=task_data.headers if task_data.headers is not None else "",
            cookies=task_data.cookies if task_data.cookies is not None else ""
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        return success_response(data=db_task)
    except Exception as e:
        db.rollback()
        print_error(e)
        return error_response(code=500, message=str(e))

@router.put("/{task_id}", summary="更新消息任务")
async def update_message_task(
    task_id: str,
    task_data: MessageTaskCreate = Body(...),
    current_user: dict = Depends(get_current_user_or_ak)
):
    db=DB.get_session()
    """
    更新消息任务
    
    参数:
        task_id: 要更新的消息任务ID
        task_data: 消息任务更新数据
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        包含更新后消息任务的响应
        404: 消息任务不存在
        400: 请求数据验证失败
        500: 数据库操作异常
    """
    try:
        db_task = db.query(MessageTask).filter(MessageTask.id == task_id).first()
        if not db_task:
            raise HTTPException(status_code=404, detail="Message task not found")
        
        if task_data.message_template is not None:
            db_task.message_template = task_data.message_template
        if task_data.web_hook_url is not None:
            db_task.web_hook_url = task_data.web_hook_url
        if task_data.mps_id is not None:
            db_task.mps_id = task_data.mps_id
        if task_data.status is not None:
            db_task.status = task_data.status
        if task_data.cron_exp is not None:
            db_task.cron_exp = task_data.cron_exp
        if task_data.message_type is not None:
            db_task.message_type = task_data.message_type
        if task_data.name is not None:
            db_task.name = task_data.name
        if task_data.headers is not None:
            db_task.headers = task_data.headers
        if task_data.cookies is not None:
            db_task.cookies = task_data.cookies
        db.commit()
        db.refresh(db_task)
        return success_response(data=db_task)
    except Exception as e:
        db.rollback()
        return error_response(code=500, message=str(e))
@router.put("/job/fresh",summary="重载任务")
async def fresh_message_task(
     current_user: dict = Depends(get_current_user_or_ak)
):
    """
    重载任务
    """
    from jobs.mps import reload_job
    reload_job()
    from jobs.cascade_task_dispatcher import cascade_schedule_service
    cascade_schedule_service.reload()
    return success_response(message="任务已经重载成功")
@router.delete("/{task_id}",summary="删除消息任务")
async def delete_message_task(
    task_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    删除消息任务
    
    参数:
        task_id: 要删除的消息任务ID
        db: 数据库会话
        current_user: 当前认证用户
        
    返回:
        204: 成功删除，无返回内容
        404: 消息任务不存在
        500: 数据库操作异常
    """
    db=DB.get_session()
    try:
        db_task = db.query(MessageTask).filter(MessageTask.id == task_id).first()
        if not db_task:
            raise HTTPException(status_code=404, detail="Message task not found")
        
        db.delete(db_task)
        db.commit()
        return success_response(message="Message task deleted successfully")
    except Exception as e:
        db.rollback()
        return error_response(code=500, message=str(e))