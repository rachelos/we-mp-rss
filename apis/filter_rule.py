from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from core.auth import get_current_user_or_ak
from core.database import get_db
from core.db import DB
from core.models.filter_rule import FilterRule
from core.models.base import DATA_STATUS
from .base import success_response, error_response
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
import json

router = APIRouter(prefix="/filter-rules", tags=["过滤规则管理"])


class FilterRuleCreate(BaseModel):
    mp_id: str  # JSON字符串，存储多个公众号ID数组
    rule_name: str
    remove_ids: Optional[List[str]] = None
    remove_classes: Optional[List[str]] = None
    remove_selectors: Optional[List[str]] = None
    remove_attributes: Optional[List[dict]] = None
    remove_regex: Optional[List[str]] = None
    remove_normal_tag: Optional[int] = 0
    priority: Optional[int] = 0


class FilterRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    remove_ids: Optional[List[str]] = None
    remove_classes: Optional[List[str]] = None
    remove_selectors: Optional[List[str]] = None
    remove_attributes: Optional[List[dict]] = None
    remove_regex: Optional[List[str]] = None
    remove_normal_tag: Optional[int] = None
    status: Optional[int] = None
    priority: Optional[int] = None


@router.get("", summary="获取过滤规则列表")
async def get_filter_rules(
    mp_id: str = Query(None, description="公众号ID，不传则返回所有"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """获取过滤规则列表，支持按公众号筛选"""
    try:
        query = db.query(FilterRule)
        if mp_id:
            query = query.filter(FilterRule.mp_id == mp_id)

        total = query.count()
        rules = query.order_by(FilterRule.priority.desc(), FilterRule.created_at.desc()).limit(limit).offset(offset).all()

        rules_list = []
        for rule in rules:
            # 解析 mp_id JSON 字符串为数组
            mp_ids = []
            try:
                if rule.mp_id:
                    mp_ids = json.loads(rule.mp_id) if rule.mp_id.startswith('[') else [rule.mp_id]
            except:
                mp_ids = [rule.mp_id] if rule.mp_id else []

            rules_list.append({
                "id": rule.id,
                "mp_id": rule.mp_id,
                "mp_ids": mp_ids,
                "is_global": len(mp_ids) == 0,  # 标记是否为全局规则
                "rule_name": rule.rule_name,
                "remove_ids": rule.remove_ids or [],
                "remove_classes": rule.remove_classes or [],
                "remove_selectors": rule.remove_selectors or [],
                "remove_attributes": rule.remove_attributes or [],
                "remove_regex": rule.remove_regex or [],
                "remove_normal_tag": rule.remove_normal_tag or 0,
                "status": rule.status,
                "priority": rule.priority,
                "created_at": rule.created_at.isoformat() if rule.created_at else None,
                "updated_at": rule.updated_at.isoformat() if rule.updated_at else None
            })

        return success_response(data={
            "list": rules_list,
            "page": {
                "limit": limit,
                "offset": offset,
                "total": total
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"获取过滤规则列表错误: {str(e)}")
        # 如果表不存在，返回空列表
        if "no such table" in str(e).lower() or "filter_rules" in str(e).lower():
            return success_response(data={
                "list": [],
                "page": {"limit": limit, "offset": offset, "total": 0}
            })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message=f"获取过滤规则列表失败: {str(e)}")
        )


@router.get("/{rule_id}", summary="获取过滤规则详情")
async def get_filter_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """获取单个过滤规则详情"""
    try:
        rule = db.query(FilterRule).filter(FilterRule.id == rule_id).first()
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="过滤规则不存在")
            )

        # 解析 mp_id JSON 字符串为数组
        mp_ids = []
        try:
            if rule.mp_id:
                mp_ids = json.loads(rule.mp_id) if rule.mp_id.startswith('[') else [rule.mp_id]
        except:
            mp_ids = [rule.mp_id] if rule.mp_id else []

        return success_response(data={
            "id": rule.id,
            "mp_id": rule.mp_id,
            "mp_ids": mp_ids,
            "is_global": len(mp_ids) == 0,  # 标记是否为全局规则
            "rule_name": rule.rule_name,
            "remove_ids": rule.remove_ids or [],
            "remove_classes": rule.remove_classes or [],
            "remove_selectors": rule.remove_selectors or [],
            "remove_attributes": rule.remove_attributes or [],
            "remove_regex": rule.remove_regex or [],
            "remove_normal_tag": rule.remove_normal_tag or 0,
            "status": rule.status,
            "priority": rule.priority,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None
        })
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取过滤规则详情错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message="获取过滤规则详情失败")
        )


@router.post("", summary="创建过滤规则")
async def create_filter_rule(
    rule: FilterRuleCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """为指定公众号创建过滤规则，支持多公众号"""
    try:
        new_rule = FilterRule(
            mp_id=rule.mp_id,
            rule_name=rule.rule_name,
            remove_ids=rule.remove_ids,
            remove_classes=rule.remove_classes,
            remove_selectors=rule.remove_selectors,
            remove_attributes=rule.remove_attributes,
            remove_regex=rule.remove_regex,
            remove_normal_tag=rule.remove_normal_tag or 0,
            priority=rule.priority or 0,
            status=DATA_STATUS.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(new_rule)
        db.commit()
        db.refresh(new_rule)

        return success_response(data={
            "id": new_rule.id,
            "mp_id": new_rule.mp_id,
            "rule_name": new_rule.rule_name,
            "message": "过滤规则创建成功"
        })
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"创建过滤规则错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message="创建过滤规则失败")
        )


@router.put("/{rule_id}", summary="更新过滤规则")
async def update_filter_rule(
    rule_id: int,
    rule: FilterRuleUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """更新过滤规则"""
    try:
        existing_rule = db.query(FilterRule).filter(FilterRule.id == rule_id).first()
        if not existing_rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="过滤规则不存在")
            )

        update_data = rule.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(existing_rule, key, value)

        existing_rule.updated_at = datetime.now()
        db.commit()

        return success_response(data={
            "id": existing_rule.id,
            "message": "过滤规则更新成功"
        })
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"更新过滤规则错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message="更新过滤规则失败")
        )


@router.delete("/{rule_id}", summary="删除过滤规则")
async def delete_filter_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """删除过滤规则"""
    try:
        rule = db.query(FilterRule).filter(FilterRule.id == rule_id).first()
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(code=40401, message="过滤规则不存在")
            )

        db.delete(rule)
        db.commit()

        return success_response(data={
            "id": rule_id,
            "message": "过滤规则删除成功"
        })
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"删除过滤规则错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message="删除过滤规则失败")
        )


@router.get("/mp/{mp_id}/active", summary="获取公众号的启用规则")
async def get_active_rules_for_mp(
    mp_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """获取指定公众号的所有启用的过滤规则（支持多公众号匹配和全局规则）"""
    try:
        # 获取所有启用的规则，然后在 Python 层面过滤
        rules = db.query(FilterRule).filter(
            FilterRule.status == DATA_STATUS.ACTIVE
        ).order_by(FilterRule.priority.desc()).all()

        rules_list = []
        for rule in rules:
            # 解析 mp_id JSON，检查是否包含指定的 mp_id 或者是全局规则（空数组）
            try:
                mp_ids = json.loads(rule.mp_id) if rule.mp_id and rule.mp_id.startswith('[') else ([rule.mp_id] if rule.mp_id else [])
            except:
                mp_ids = [rule.mp_id] if rule.mp_id else []

            # 匹配条件：mp_id 在列表中，或者是全局规则（空数组）
            if not mp_ids or mp_id in mp_ids:
                rules_list.append({
                    "id": rule.id,
                    "rule_name": rule.rule_name,
                    "remove_ids": rule.remove_ids or [],
                    "remove_classes": rule.remove_classes or [],
                    "remove_selectors": rule.remove_selectors or [],
                    "remove_attributes": rule.remove_attributes or [],
                    "remove_regex": rule.remove_regex or [],
                    "remove_normal_tag": rule.remove_normal_tag or 0,
                    "priority": rule.priority
                })

        return success_response(data=rules_list)
    except Exception as e:
        print(f"获取公众号过滤规则错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(code=50001, message="获取公众号过滤规则失败")
        )


def get_filter_rules_for_mp(mp_id: str) -> list:
    """
    获取指定公众号的所有启用过滤规则（供内部调用）
    返回规则列表，用于HTML过滤
    支持多公众号匹配和全局规则（空mp_id数组）
    """
    session = DB.get_session()
    try:
        rules = session.query(FilterRule).filter(
            FilterRule.status == DATA_STATUS.ACTIVE
        ).order_by(FilterRule.priority.desc()).all()

        print(f"[FilterRule] 查询到 {len(rules)} 条启用的规则")

        # 在 Python 层面过滤匹配的规则
        matched_rules = []
        for rule in rules:
            # 解析 mp_id JSON
            mp_ids = []
            try:
                if rule.mp_id:
                    # 检查是否为 JSON 数组格式
                    if rule.mp_id.strip().startswith('['):
                        mp_ids = json.loads(rule.mp_id)
                        # 确保解析结果是列表
                        if not isinstance(mp_ids, list):
                            mp_ids = [str(mp_ids)]
                    else:
                        # 非 JSON 格式，作为单个 ID 处理
                        mp_ids = [rule.mp_id]
            except Exception as e:
                print(f"[FilterRule] 解析 mp_id 失败: {rule.mp_id}, 错误: {e}")
                mp_ids = []

            # 匹配条件：mp_id 在列表中，或者是全局规则（空数组）
            is_global = len(mp_ids) == 0
            is_match = is_global or mp_id in mp_ids

            if is_match:
                print(f"[FilterRule] 匹配规则: {rule.rule_name}, mp_id={mp_id}, rule_mp_ids={mp_ids}, is_global={is_global}")
                matched_rules.append(rule)
            else:
                print(f"[FilterRule] 跳过规则: {rule.rule_name}, mp_id={mp_id}, rule_mp_ids={mp_ids}")

        print(f"[FilterRule] 为公众号 {mp_id} 找到 {len(matched_rules)} 条规则")
        return matched_rules
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"获取过滤规则失败: {str(e)}")
        return []


def apply_filter_rules(html_content: str, mp_id: str, remove_xpaths: List[str] = []) -> str:
    """
    对HTML内容应用指定公众号的过滤规则

    Args:
        html_content: 原始HTML内容
        mp_id: 公众号ID
        remove_xpaths: 额外的XPath删除规则列表

    Returns:
        过滤后的HTML内容
    """
    if not html_content:
        return html_content

    rules = get_filter_rules_for_mp(mp_id)
    if not rules:
        return html_content

    from tools.htmltools import htmltools

    print(f"[FilterRule] 开始应用过滤规则，共 {len(rules)} 条规则")
    filtered_content = html_content
    for rule in rules:
        try:
            print(f"[FilterRule] 应用规则: {rule.rule_name}")
            filtered_content = htmltools.clean_html(
                filtered_content,
                remove_ids=rule.remove_ids or [],
                remove_classes=rule.remove_classes or [],
                remove_selectors=rule.remove_selectors or [],
                remove_attributes=rule.remove_attributes or [],
                remove_regx=rule.remove_regex or [],
                remove_xpaths=remove_xpaths,
                remove_normal_tag=bool(rule.remove_normal_tag)
            )
        except Exception as e:
            print(f"应用过滤规则失败 (规则ID: {rule.id}): {str(e)}")
            continue

    return filtered_content
