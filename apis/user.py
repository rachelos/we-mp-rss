from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from datetime import datetime
from core.auth import get_current_user_or_ak
from core.db import DB
from core.models import User as DBUser
from core.auth import pwd_context
import os
from .base import success_response, error_response
router = APIRouter(prefix="/user", tags=["用户管理"])

@router.get("", summary="获取用户信息")
async def get_user_info(current_user: dict = Depends(get_current_user_or_ak)):
    session = DB.get_session()
    try:
        user = session.query(DBUser).filter(
            DBUser.username == current_user["username"]
        ).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="用户不存在"
                )
            )
        return success_response({
            "username": user.username,
            "nickname": user.nickname if user.nickname else user.username,
            "avatar": user.avatar if user.avatar else "/static/default-avatar.png",
            "email": user.email if user.email else "",
            "role": user.role,
            "is_active": user.is_active,
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_201_CREATED,
            detail=error_response(
                code=50001,
                message="获取用户信息失败"
            )
        )

@router.get("/list", summary="获取用户列表")
async def get_user_list(
    current_user: dict = Depends(get_current_user_or_ak),
    page: int = 1,
    page_size: int = 10
):
    """获取所有用户列表（仅管理员可用）"""
    session = DB.get_session()
    try:
        # 验证当前用户是否为管理员
        if current_user["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response(
                    code=40301,
                    message="无权限执行此操作"
                )
            )

        # 查询用户总数
        total = session.query(DBUser).count()

        # 分页查询用户列表
        users = session.query(DBUser).order_by(DBUser.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        # 格式化返回数据
        user_list = []
        for user in users:
            # 解析权限
            permissions = []
            if user.permissions:
                try:
                    import json
                    permissions = json.loads(user.permissions) if isinstance(user.permissions, str) else user.permissions
                except:
                    permissions = []
            
            user_list.append({
                "id": user.id,
                "username": user.username,
                "nickname": user.nickname if user.nickname else user.username,
                "avatar": user.avatar if user.avatar else "/static/default-avatar.png",
                "email": user.email if user.email else "",
                "role": user.role,
                "is_active": user.is_active,
                "permissions": permissions,
                "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else "",
                "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M:%S") if user.updated_at else ""
            })

        return success_response({
            "total": total,
            "page": page,
            "page_size": page_size,
            "list": user_list
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code=50002,
                message=f"获取用户列表失败: {str(e)}"
            )
        )

@router.post("", summary="添加用户")
async def add_user(
    user_data: dict,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """添加新用户"""
    session = DB.get_session()
    try:
        # 验证当前用户是否为管理员
        if current_user["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response(
                    code=40301,
                    message="无权限执行此操作"
                )
            )

        # 验证输入数据
        required_fields = ["username", "password"]
        for field in required_fields:
            if field not in user_data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_response(
                        code=40001,
                        message=f"缺少必填字段: {field}"
                    )
                )

        # 检查用户名是否已存在
        existing_user = session.query(DBUser).filter(
            DBUser.username == user_data["username"]
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40002,
                    message="用户名已存在"
                )
            )

        # 创建新用户
        import json
        import uuid
        new_user = DBUser(
            id=str(uuid.uuid4()),
            username=user_data["username"],
            password_hash=pwd_context.hash(user_data["password"]),
            email=user_data.get("email", ""),
            nickname=user_data.get("nickname", ""),
            role=user_data.get("role", "user"),
            permissions=json.dumps(user_data.get("permissions", [])) if user_data.get("permissions") else "",
            is_active=user_data.get("is_active", True),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(new_user)
        session.commit()

        return success_response(message="用户添加成功")
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"用户添加失败: {str(e)}"
        )

@router.put("/password", summary="修改密码")
async def change_password(
    password_data: dict,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """修改用户密码"""
    session = DB.get_session()
    try:
        # 验证请求数据
        if "old_password" not in password_data or "new_password" not in password_data:
            from .base import error_response
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail=error_response(
                    code=40001,
                    message="需要提供旧密码和新密码"
                )
            )

        # 获取用户
        user = session.query(DBUser).filter(
            DBUser.username == current_user["username"]
        ).first()
        if not user:
            from .base import error_response
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="用户不存在"
                )
            )

        # 验证旧密码
        if not pwd_context.verify(password_data["old_password"], user.password_hash):
            from .base import error_response
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail=error_response(
                    code=40003,
                    message="旧密码不正确"
                )
            )

        # 验证新密码复杂度
        new_password = password_data["new_password"]
        if len(new_password) < 8:
            from .base import error_response
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail=error_response(
                    code=40004,
                    message="密码长度不能少于8位"
                )
            )

        # 更新密码
        user.password_hash = pwd_context.hash(new_password)
        user.updated_at = datetime.now()
        session.commit()
        session.expire(user)
        # 清除用户缓存，确保新密码立即生效
        from core.auth import clear_user_cache
        clear_user_cache(current_user["username"])

        from .base import success_response
        return success_response(message="密码修改成功")

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"密码修改失败: {str(e)}"
        )

@router.put("", summary="修改用户资料")
async def update_user_info(
    update_data: dict,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """修改用户基本信息(不包括密码)"""
    session = DB.get_session()
    try:
        # 获取目标用户
        target_username = update_data.get("username", current_user["username"])
        user = session.query(DBUser).filter(
            DBUser.username == target_username
        ).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="用户不存在"
                )
            )

        # 检查权限：只有管理员或用户自己可以修改信息
        if current_user["role"] != "admin" and current_user["username"] != target_username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response(
                    code=40301,
                    message="无权限修改其他用户信息"
                )
            )

        # 不允许通过此接口修改密码
        if "password" in update_data:
            raise HTTPException(
                status_code=status.HTTP_200_OK,
                detail=error_response(
                    code=40002,
                    message="请使用专门的密码修改接口"
                )
            )

        # 更新用户信息
        if "is_active" in update_data:
            user.is_active = bool(update_data["is_active"])
        if "email" in update_data:
            user.email = update_data["email"]
        if "role" in update_data and current_user["role"] == "admin":
            user.role = update_data["role"]

        user.updated_at = datetime.now()
        session.commit()
        return success_response(message="更新成功")
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"更新失败: {str(e)}"
        )

@router.put("/{user_id}", summary="更新用户信息")
async def update_user_by_id(
    user_id: str,
    update_data: dict,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """管理员更新指定用户信息"""
    session = DB.get_session()
    try:
        # 验证当前用户是否为管理员
        if current_user["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response(
                    code=40301,
                    message="无权限执行此操作"
                )
            )

        # 获取目标用户
        user = session.query(DBUser).filter(DBUser.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="用户不存在"
                )
            )

        # 更新用户信息
        import json
        if "nickname" in update_data:
            user.nickname = update_data["nickname"]
        if "email" in update_data:
            user.email = update_data["email"]
        if "role" in update_data:
            user.role = update_data["role"]
        if "permissions" in update_data:
            user.permissions = json.dumps(update_data["permissions"]) if update_data["permissions"] else ""
        if "is_active" in update_data:
            user.is_active = bool(update_data["is_active"])

        user.updated_at = datetime.now()
        session.commit()
        return success_response(message="更新成功")
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"更新失败: {str(e)}"
        )

@router.delete("/{user_id}", summary="删除用户")
async def delete_user_by_id(
    user_id: str,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """管理员删除指定用户"""
    session = DB.get_session()
    try:
        # 验证当前用户是否为管理员
        if current_user["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response(
                    code=40301,
                    message="无权限执行此操作"
                )
            )

        # 获取目标用户
        user = session.query(DBUser).filter(DBUser.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="用户不存在"
                )
            )

        # 不允许删除自己
        if user.username == current_user["username"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40001,
                    message="不能删除自己的账号"
                )
            )

        # 删除用户
        session.delete(user)
        session.commit()
        return success_response(message="删除成功")
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"删除失败: {str(e)}"
        )

@router.post("/{user_id}/reset-password", summary="重置用户密码")
async def reset_user_password(
    user_id: str,
    password_data: dict,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """管理员重置指定用户密码"""
    session = DB.get_session()
    try:
        # 验证当前用户是否为管理员
        if current_user["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response(
                    code=40301,
                    message="无权限执行此操作"
                )
            )

        # 获取目标用户
        user = session.query(DBUser).filter(DBUser.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(
                    code=40401,
                    message="用户不存在"
                )
            )

        # 验证新密码
        new_password = password_data.get("new_password")
        if not new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40001,
                    message="请提供新密码"
                )
            )

        if len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40004,
                    message="密码长度不能少于8位"
                )
            )

        # 更新密码
        user.password_hash = pwd_context.hash(new_password)
        user.updated_at = datetime.now()
        session.commit()
        
        # 清除用户缓存
        from core.auth import clear_user_cache
        clear_user_cache(user.username)
        
        return success_response(message="密码重置成功")
    except HTTPException as e:
        raise e
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"密码重置失败: {str(e)}"
        )

@router.post("/avatar", summary="上传用户头像")
async def upload_avatar(
    file: UploadFile = File(...),
    # file: typing.Optional[UploadFile] = None,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """处理用户头像上传"""
    try:
        avatar_path="files/avatars"
        # 确保头像目录存在
        os.makedirs(avatar_path, exist_ok=True)
        from core.res.avatar import avatar_dir
        # 保存文件
        file_path = f"{avatar_dir}/{current_user['username']}.jpg"
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        
        # 更新用户头像字段
        session = DB.get_session()
        try:
            user = session.query(DBUser).filter(
                DBUser.username == current_user["username"]
            ).first()
            if user:
                user.avatar = f"/{avatar_path}/{current_user['username']}.jpg"
                session.commit()
        except Exception as e:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail=f"更新用户头像失败: {str(e)}"
            )

        from .base import success_response
        return success_response(data={"avatar": f"/{avatar_path}/{current_user['username']}.jpg"})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"头像上传失败: {str(e)}"
        )
@router.post("/upload", summary="上传文件")
async def upload_file(
    file: UploadFile = File(...),
    type: str = "tags",
    current_user: dict = Depends(get_current_user_or_ak)
):
    """处理用户文件上传"""
    try:
        # 验证 type 参数的安全性
        if not type.isalnum() or type in ["", ".."]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    code=40003,
                    message="无效的文件类型"
                )
            )
        file_url_path=f"files/{type}/"
        from core.res.avatar import files_dir
        upload_path = f"{files_dir}/{type}/"
        # 确保上传目录存在
        os.makedirs(upload_path, exist_ok=True)

        # 生成唯一的文件名
        file_name = f"{current_user['username']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
        file_path = f"{upload_path}/{file_name}"

        # 保存文件
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        return success_response(data={"url": f"/{file_url_path}/{file_name}"})
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"文件上传失败: {str(e)}"
        )
