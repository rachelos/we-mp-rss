#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 更新 API 接口
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional, List
import logging
import os
from tools.github_updater import GitHubUpdater
from core.security import require_web_updater

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["GitHub更新"],
                   dependencies=[Depends(require_web_updater)])


class UpdateRequest(BaseModel):
    """更新请求模型"""
    branch: Optional[str] = None
    backup: bool = True
    path: Optional[str] = None


class RollbackRequest(BaseModel):
    """回滚请求模型"""
    commit_hash: str
    path: Optional[str] = None


class UpdateResponse(BaseModel):
    """更新响应模型"""
    success: bool
    message: str
    backup_created: Optional[bool] = None
    backup_path: Optional[str] = None
    updated_files: Optional[List[str]] = None
    error: Optional[str] = None


class StatusResponse(BaseModel):
    """状态响应模型"""
    is_git_repo: bool
    current_branch: Optional[str] = None
    has_changes: bool
    remote_url: Optional[str] = None
    last_commit: Optional[str] = None
    ahead_commits: int = 0
    behind_commits: int = 0
    error: Optional[str] = None


class CommitInfo(BaseModel):
    """提交信息模型"""
    hash: str
    message: str
    author: str
    date: str


@router.get("/status", response_model=StatusResponse, summary="检查 Git 仓库状态")
async def check_git_status(path: Optional[str] = None):
    """
    检查当前 Git 仓库的状态
    
    - **path**: 可选的仓库路径，默认为项目根目录
    
    返回仓库的详细状态信息，包括当前分支、是否有未提交更改、与远程的差异等
    """
    try:
        updater = GitHubUpdater(path)
        status = updater.check_git_status()
        return status
    except Exception as e:
        logger.error(f"检查 Git 状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"检查状态失败: {str(e)}")


@router.post("/update", response_model=UpdateResponse, summary="从 GitHub 更新代码")
async def update_from_github(
    request: UpdateRequest,
    background_tasks: BackgroundTasks
):
    """
    从 GitHub 仓库更新代码
    
    - **branch**: 目标分支，默认为当前分支
    - **backup**: 是否在更新前创建备份，默认为 True
    - **path**: 可选的仓库路径，默认为项目根目录
    
    更新过程包括：
    1. 检查仓库状态
    2. 创建备份（可选）
    3. 获取远程更新
    4. 执行代码更新
    """
    try:
        updater = GitHubUpdater(request.path)
        
        # 检查状态
        status = updater.check_git_status()
        if not status['is_git_repo']:
            raise HTTPException(status_code=400, detail="当前目录不是 Git 仓库")
        
        if status['has_changes']:
            raise HTTPException(
                status_code=400, 
                detail="存在未提交的更改，请先提交或暂存后再更新"
            )
        
        # 执行更新
        result = updater.update_from_github(
            branch=request.branch,
            backup=request.backup
        )
        
        if not result['success']:
            raise HTTPException(status_code=400, detail=result.get('error', '更新失败'))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GitHub 更新失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新过程中发生错误: {str(e)}")


@router.get("/commits", response_model=List[CommitInfo], summary="获取提交历史")
async def get_commit_history(
    limit: int = 10,
    path: Optional[str] = None
):
    """
    获取提交历史记录
    
    - **limit**: 返回的提交数量，默认为 10
    - **path**: 可选的仓库路径，默认为项目根目录
    
    返回最近的提交记录，包括提交哈希、消息、作者和日期
    """
    try:
        if limit > 100:
            raise HTTPException(status_code=400, detail="提交数量不能超过 100")
        
        updater = GitHubUpdater(path)
        commits = updater.get_commit_history(limit)
        return commits
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取提交历史失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取提交历史失败: {str(e)}")


@router.post("/rollback", summary="回滚到指定提交")
async def rollback_to_commit(request: RollbackRequest):
    """
    回滚代码到指定的提交
    
    - **commit_hash**: 目标提交的完整哈希值
    - **path**: 可选的仓库路径，默认为项目根目录
    
    **警告**: 此操作会永久丢失当前提交之后的更改，请谨慎使用
    """
    try:
        updater = GitHubUpdater(request.path)
        
        # 验证提交哈希是否存在
        commits = updater.get_commit_history(100)
        commit_exists = any(commit['hash'].startswith(request.commit_hash) for commit in commits)
        
        if not commit_exists:
            raise HTTPException(status_code=404, detail="指定的提交不存在")
        
        # 执行回滚
        result = updater.rollback_to_commit(request.commit_hash)
        
        if not result['success']:
            raise HTTPException(status_code=400, detail=result.get('error', '回滚失败'))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"回滚失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"回滚过程中发生错误: {str(e)}")


@router.get("/branches", summary="获取所有分支")
async def get_branches(path: Optional[str] = None):
    """
    获取仓库的所有分支列表
    
    - **path**: 可选的仓库路径，默认为项目根目录
    
    返回本地和远程分支的列表
    """
    try:
        updater = GitHubUpdater(path)
        
        # 获取本地分支
        success, local_branches, _ = updater._run_git_command(['branch', '--format=%(refname:short)'])
        if not success:
            raise HTTPException(status_code=500, detail="获取本地分支失败")
        
        # 获取远程分支
        success, remote_branches, _ = updater._run_git_command(['branch', '-r', '--format=%(refname:short)'])
        if not success:
            raise HTTPException(status_code=500, detail="获取远程分支失败")
        
        return {
            "local": [b.strip() for b in local_branches.split('\n') if b.strip()],
            "remote": [b.strip() for b in remote_branches.split('\n') if b.strip()]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取分支列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取分支列表失败: {str(e)}")
