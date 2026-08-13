from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, File, UploadFile, Form
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from core.auth import get_current_user_or_ak
from core.db import DB
from .base import success_response, error_response,BaseResponse
from datetime import datetime
from typing import Optional, List, Literal, Any
import os
import threading
import asyncio
import zipfile
from concurrent.futures import ThreadPoolExecutor
import io
import uuid
import base64

# 导入导出工具
from tools.mdtools.export import export_md_to_doc, process_articles

# 图片处理
from PIL import Image

router = APIRouter(prefix="/tools", tags=["工具"])

# Schema 模型定义
class ExportArticlesRequest(BaseModel):
    """导出文章请求模型"""
    mp_id: str = Field(..., description="公众号ID", example="MP_WXS_3892772220")
    doc_id: Optional[List[str]] = Field(None, description="文档ID列表，为空则导出所有文章", example=[])
    page_size: int = Field(10, description="每页数量", ge=1, le=10)
    page_count: int = Field(1, description="页数，0表示全部", ge=0, le=10000)
    add_title: bool = Field(True, description="是否添加标题")
    remove_images: bool = Field(True, description="是否移除图片")
    remove_links: bool = Field(False, description="是否移除链接")
    export_md: bool = Field(False, description="是否导出Markdown格式")
    export_docx: bool = Field(False, description="是否导出Word文档格式")
    export_json: bool = Field(False, description="是否导出JSON格式")
    export_csv: bool = Field(False, description="是否导出CSV格式")
    export_pdf: bool = Field(True, description="是否导出PDF格式")
    zip_filename: Optional[str] = Field(None, description="压缩包文件名，为空则自动生成", example="")

class ExportArticlesResponse(BaseModel):
    """导出文章响应模型"""
    record_count: int = Field(..., description="导出的文章数量")
    export_path: str = Field(..., description="导出文件路径")
    message: str = Field(..., description="导出结果消息")

class ExportFileInfo(BaseModel):
    """导出文件信息模型"""
    filename: str = Field(..., description="文件名")
    size: int = Field(..., description="文件大小（字节）")
    created_time: str = Field(..., description="创建时间（ISO格式）")
    modified_time: str = Field(..., description="修改时间（ISO格式）")

def _export_articles_worker(
    mp_id: str,
    doc_id: Optional[List[int]],
    page_size: int,
    page_count: int,
    add_title: bool,
    remove_images: bool,
    remove_links: bool,
    export_md: bool,
    export_docx: bool,
    export_json: bool,
    export_csv: bool,
    export_pdf: bool,
    zip_filename: Optional[str]
):
    """
    导出文章的工作线程函数
    """
    return export_md_to_doc(
        mp_id=mp_id,
        doc_id=doc_id,
        page_size=page_size,
        page_count=page_count,
        add_title=add_title,
        remove_images=remove_images,
        remove_links=remove_links,
        export_md=export_md,
        export_docx=export_docx,
        export_json=export_json,
        export_csv=export_csv,
        export_pdf=export_pdf,
        zip_filename=zip_filename
    )

@router.post("/export/articles", summary="导出文章（异步任务）")
async def export_articles(
    request: ExportArticlesRequest,
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    异步导出文章，立即返回 job_id，通过 job_id 查询进度或订阅 SSE。

    用法示例：
    ```
    POST /api/v1/wx/tools/export/articles
    Authorization: Bearer {token}

    # 轮询
    GET /api/v1/wx/tools/export/status?job_id=<job_id>

    # SSE
    GET /api/v1/wx/tools/export/progress?job_id=<job_id>
    ```
    """
    try:
        # 已有同名导出任务则拒绝，避免并发执行
        for thread in threading.enumerate():
            if thread.name == f"export_articles_{request.mp_id}":
                return error_response(400, "该公众号的导出任务已在处理中，请勿重复点击")

        docx_path = f"./data/docs/{request.mp_id}/"
        if request.zip_filename:
            zip_file_path = f"{docx_path}{request.zip_filename}"
        else:
            zip_file_path = f"{docx_path}exported_articles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

        # 注册后台任务并立即返回 job_id
        from core.export_job import get_export_job_manager
        user_id = current_user.get("sub") or current_user.get("username") or current_user.get("id") or "unknown"
        active_fmts = [
            name for name, enabled in (
                ("md", request.export_md), ("docx", request.export_docx),
                ("json", request.export_json), ("csv", request.export_csv),
                ("pdf", request.export_pdf),
            ) if enabled
        ]
        manager = get_export_job_manager()
        job = manager.create_job(
            user_id=str(user_id),
            mp_id=request.mp_id,
            fmt_summary="+".join(active_fmts) or "none",
        )
        manager.update(job.job_id, stage="queued", message="任务已入队", progress=0,
                       output_path=zip_file_path)

        def _run() -> None:
            """后台线程：调用优化版 exporter 并打包。"""
            try:
                from core.exporter import _export_articles_optimized
                from core.db import DB
                session = DB.get_session()

                def progress_cb(stage: str, message: str, progress: int, **kw: Any) -> None:
                    manager.update(job.job_id, stage=stage, message=message, progress=progress, **kw)

                # 1) 渲染各类格式文件
                result = _export_articles_optimized(
                    session=session,
                    mp_id=request.mp_id,
                    doc_id=request.doc_id,
                    page_size=request.page_size,
                    page_count=request.page_count,
                    add_title=request.add_title,
                    remove_images=request.remove_images,
                    remove_links=request.remove_links,
                    export_md=request.export_md,
                    export_docx=request.export_docx,
                    export_json=request.export_json,
                    export_csv=request.export_csv,
                    export_pdf=request.export_pdf,
                    docx_path=docx_path,
                    progress_callback=progress_cb,
                )
                processed = result.get("processed", 0)
                skipped = result.get("skipped", 0)

                # 2) 打包 zip + 删除源文件
                if processed > 0:
                    manager.update(job.job_id, stage="packaging", message="正在打包…", progress=92)
                    try:
                        final_zip = zip_file_path
                        if not final_zip.endswith(".zip"):
                            final_zip += ".zip"
                        if os.path.exists(final_zip):
                            os.remove(final_zip)
                        with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                            for root, _, files in os.walk(docx_path):
                                for f in files:
                                    if f.endswith(".zip"):
                                        continue
                                    fp = os.path.join(root, f)
                                    arc = os.path.relpath(fp, docx_path)
                                    zf.write(fp, arc)
                                    try:
                                        os.remove(fp)
                                    except Exception as e:
                                        print_error(f"删除文件失败 {fp}: {e}")
                        manager.finish(
                            job.job_id, ok=True,
                            message=f"导出完成：共 {processed} 篇（跳过 {skipped} 篇）",
                            output_path=final_zip,
                        )
                    except Exception as e:
                        manager.finish(job.job_id, ok=False, message=f"打包失败: {e}")
                else:
                    manager.finish(
                        job.job_id, ok=False,
                        message=f"没有可导出的文章（跳过 {skipped} 篇）",
                    )

            except Exception as e:
                manager.finish(job.job_id, ok=False, message=f"后台导出异常: {e}")

        threading.Thread(target=_run, name=f"export_articles_{request.mp_id}", daemon=True).start()

        # 返回时不要泄露服务器绝对路径，只给文件名（下载 API 会基于 mp_id 拼接）
        return success_response({
            "job_id": job.job_id,
            "export_path": os.path.basename(zip_file_path),
            "mp_id": request.mp_id,
            "message": "导出任务已启动，请通过 job_id 查询进度或订阅 SSE",
        }, "导出任务已启动")

    except ValueError as e:
        return error_response(400, str(e))
    except Exception as e:
        return error_response(500, f"导出失败: {str(e)}")


@router.get("/export/status", summary="查询文章导出任务状态")
async def export_status(
    job_id: str,
    current_user: dict = Depends(get_current_user_or_ak),
):
    """根据 job_id 返回当前阶段、消息、进度、总数、已处理数、跳过数。仅 job 所有者可访问。"""
    from core.export_job import get_export_job_manager
    job = get_export_job_manager().get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40404, message=f"找不到导出任务 {job_id}"),
        )
    caller_id = str(
        current_user.get("sub")
        or current_user.get("username")
        or current_user.get("id")
        or ""
    )
    if job.user_id != caller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(code=40303, message="无权访问该导出任务"),
        )
    return success_response(job.to_dict(), "ok")


@router.get("/export/progress", summary="SSE 实时推送文章导出进度")
async def export_progress(
    job_id: str,
    current_user: dict = Depends(get_current_user_or_ak),
):
    """Server-Sent Events 流式推送，仅 job 所有者可订阅。

    事件格式（每行 JSON）：
    ```
    data: {"job_id":"abc...","stage":"rendering_pdfs","message":"...","progress":40,"total_records":25,"processed_records":8,"skipped_records":2,"ok":null,"started_at":...,"finished_at":null}
    ```
    """
    from core.export_job import get_export_job_manager
    from fastapi.responses import StreamingResponse
    import asyncio
    import json as json_lib

    job = get_export_job_manager().get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40404, message=f"找不到导出任务 {job_id}"),
        )
    caller_id = str(
        current_user.get("sub")
        or current_user.get("username")
        or current_user.get("id")
        or ""
    )
    if job.user_id != caller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(code=40303, message="无权订阅该导出任务进度"),
        )

    async def event_stream():
        try:
            manager = get_export_job_manager()
            q = await manager.subscribe(job_id)
        except KeyError:
            yield "event: error\ndata: {\"message\":\"job not found\"}\n\n"
            return
        try:
            while True:
                try:
                    snap = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
                    continue
                yield f"data: {json_lib.dumps(snap, ensure_ascii=False)}\n\n"
                if snap.get("finished_at") is not None:
                    break
        finally:
            try:
                get_export_job_manager().unsubscribe(job_id, q)
            except Exception:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@router.get("/export/download", summary="下载导出文件")
async def download_export_file(
    filename: str = Query(..., description="文件名"),
    mp_id: Optional[str] = Query(None, description="公众号ID"),
    delete_after_download: bool = Query(False, description="下载后删除文件"),
    # current_user: dict = Depends(get_current_user)
):
    """
    下载导出的文件
    """
    try:
        # 定义基础目录
        base_dir = os.path.abspath("./data/docs")

        # 构建并规范化路径
        if mp_id:
            target_path = os.path.join(base_dir, mp_id, filename)
        else:
            # 如果没有mp_id，可能是在根目录下或者是旧逻辑，视需求而定
            # 这里为了安全起见，依然限制在 base_dir 下
             target_path = os.path.join(base_dir, filename)

        # 安全加固：使用realpath解析符号链接
        safe_path = os.path.realpath(os.path.normpath(target_path))
        real_base = os.path.realpath(base_dir)

        # 检查是否尝试跳出基础目录（更严格的检查）
        if not safe_path.startswith(real_base + os.sep) and safe_path != real_base:
            return error_response(403, "非法的文件路径请求")

        if not os.path.exists(safe_path):
             # 避免泄露文件存在信息，或者直接报404
            raise HTTPException(status_code=404, detail="文件不存在")

        # 再次确认是文件而不是目录
        if not os.path.isfile(safe_path):
             raise HTTPException(status_code=404, detail="文件不存在")

        def cleanup_file():
            """后台任务：删除临时文件"""
            try:
                if os.path.exists(safe_path) and delete_after_download:
                    os.remove(safe_path)
            except Exception:
                pass

        return FileResponse(
            path=safe_path,
            filename=filename,
            background=BackgroundTask(cleanup_file)
        )

    except HTTPException:
        raise
    except Exception as e:
        return error_response(500, f"下载失败: {str(e)}")

@router.get("/export/list", summary="获取导出文件列表", response_model=BaseResponse)
async def list_export_files(
    mp_id: Optional[str] = Query(None, description="公众号ID"),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    获取指定公众号的导出文件列表
    """
    try:
        from .ver import API_VERSION
        safe_root = os.path.abspath(os.path.normpath("./data/docs"))
        # Ensure mp_id is not None or empty
       
        export_path = os.path.abspath(os.path.join(safe_root, mp_id))
        # Validate that export_path is within safe_root
        if not export_path.startswith(safe_root):
            return success_response([])
        if not os.path.exists(export_path):
            return success_response([])
        # Check directory permissions
        if not os.access(export_path, os.R_OK):
            return error_response(403, "无权限访问该目录")
        files = []
        for root, _, filenames in os.walk(export_path):
            # Ensure root is also within safe_root, in case of symlinks or traversal
            root_norm = os.path.abspath(root)
            if not root_norm.startswith(safe_root):
                continue
            for filename in filenames:
                if filename.endswith('.zip'):
                    file_path = os.path.join(root, filename)
                    try:
                        file_stat = os.stat(file_path)
                        file_path = os.path.relpath(file_path, export_path)
                        files.append({
                        "filename": filename,
                        "size": file_stat.st_size,
                        "created_time": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                        "modified_time": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                        "path": file_path,
                        "download_url": f"{API_VERSION}/tools/export/download?mp_id={mp_id}&filename={file_path}"  # 下载链接
                    })
                    except PermissionError:
                        continue
               
        
        # 按修改时间倒序排列
        files.sort(key=lambda x: x["modified_time"], reverse=True)
        
        return success_response(files)
        
    except Exception as e:
        return error_response(500, f"获取文件列表失败: {str(e)}")

# 删除文件请求模型
class DeleteFileRequest(BaseModel):
    """删除文件请求模型"""
    filename: str = Field(..., description="文件名", example="exported_articles_20241021_143000.zip")
    mp_id: str = Field(..., description="公众号ID", example="MP_WXS_3892772220")

@router.delete("/export/delete", summary="删除导出文件", response_model=BaseResponse)
async def delete_export_file(
    request: DeleteFileRequest = Body(...),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    删除指定的导出文件
    """
    try:
        # 参数验证
        if not request.filename :
            return error_response(400, "文件名和公众号ID不能为空")
        
        # 构建文件路径并做路径归一化及安全检测
        base_path = os.path.realpath(f"./data/docs/{request.mp_id}/")
        unsafe_path = os.path.join(base_path, request.filename)
        safe_path = os.path.realpath(os.path.normpath(unsafe_path))
        
        # 安全检查：确保文件在指定目录内，防止路径遍历攻击
        if not safe_path.startswith(base_path):
            return error_response(403, "无权限删除该文件")
        
        # 只允许删除.zip文件
        if not request.filename.endswith('.zip'):
            return error_response(400, "只能删除.zip格式的导出文件")
        
        # 检查文件是否存在
        if not os.path.exists(safe_path):
            return error_response(404, "文件不存在")
        
        # 删除文件
        os.remove(safe_path)
        
        return success_response({
            "filename": request.filename,
            "message": "文件删除成功"
        })
        
    except PermissionError:
        return error_response(403, "没有权限删除该文件")
    except ValueError as e:
        return error_response(422, f"请求参数验证失败: {str(e)}")
    except Exception as e:
        return error_response(500, f"删除文件失败: {str(e)}")

# 兼容性接口：支持查询参数方式删除
@router.delete("/export/delete-by-query", summary="删除导出文件(查询参数)", response_model=BaseResponse)
async def delete_export_file_by_query(
    filename: str = Query(..., description="文件名"),
    mp_id: str = Query(..., description="公众号ID"),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    删除指定的导出文件（通过查询参数）
    """
    # 创建请求对象并调用主删除函数
    request = DeleteFileRequest(filename=filename, mp_id=mp_id)
    return await delete_export_file(request, current_user)


# ==================== 图片裁剪功能 ====================

# 裁剪方式枚举
CropMode = Literal[
    "center", "top", "bottom", "left", "right",
    "top-left", "top-right", "bottom-left", "bottom-right"
]

class ImageCropRequest(BaseModel):
    """图片裁剪请求模型（用于URL或base64输入）"""
    image_url: Optional[str] = Field(None, description="图片URL地址")
    image_base64: Optional[str] = Field(None, description="Base64编码的图片数据")
    aspect_ratio: Optional[str] = Field(None, description="目标比例，如 '16:9', '4:3', '1:1' 或自定义 '800:600'")
    width: Optional[int] = Field(None, description="目标宽度（像素），与aspect_ratio二选一")
    height: Optional[int] = Field(None, description="目标高度（像素），与aspect_ratio二选一")
    mode: CropMode = Field("center", description="裁剪方式：center(居中), top(顶部), bottom(底部), left(左侧), right(右侧), top-left, top-right, bottom-left, bottom-right")
    output_format: str = Field("png", description="输出格式：png, jpeg, webp")
    return_base64: bool = Field(False, description="是否返回base64编码，默认返回文件下载")

class ImageCropResponse(BaseModel):
    """图片裁剪响应模型"""
    width: int = Field(..., description="裁剪后宽度")
    height: int = Field(..., description="裁剪后高度")
    original_width: int = Field(..., description="原始宽度")
    original_height: int = Field(..., description="原始高度")
    format: str = Field(..., description="输出格式")
    file_url: Optional[str] = Field(None, description="文件下载地址")
    base64: Optional[str] = Field(None, description="Base64编码的图片数据")


def calculate_crop_box(
    original_width: int,
    original_height: int,
    target_ratio: float,
    mode: str
) -> tuple:
    """
    计算裁剪区域
    
    Args:
        original_width: 原图宽度
        original_height: 原图高度
        target_ratio: 目标宽高比 (width/height)
        mode: 裁剪方式
        
    Returns:
        (left, top, right, bottom) 裁剪区域
    """
    original_ratio = original_width / original_height
    
    if original_ratio > target_ratio:
        # 原图更宽，需要裁剪宽度
        new_width = int(original_height * target_ratio)
        new_height = original_height
        
        # 根据模式确定水平位置
        if mode in ["left", "top-left", "bottom-left"]:
            left = 0
        elif mode in ["right", "top-right", "bottom-right"]:
            left = original_width - new_width
        else:  # center, top, bottom
            left = (original_width - new_width) // 2
        
        right = left + new_width
        top = 0
        bottom = original_height
        
    else:
        # 原图更高，需要裁剪高度
        new_width = original_width
        new_height = int(original_width / target_ratio)
        
        # 根据模式确定垂直位置
        if mode in ["top", "top-left", "top-right"]:
            top = 0
        elif mode in ["bottom", "bottom-left", "bottom-right"]:
            top = original_height - new_height
        else:  # center, left, right
            top = (original_height - new_height) // 2
        
        bottom = top + new_height
        left = 0
        right = original_width
    
    return (left, top, right, bottom)


def process_image_crop(
    image_data: bytes,
    aspect_ratio: Optional[str],
    target_width: Optional[int],
    target_height: Optional[int],
    mode: str,
    output_format: str
) -> tuple:
    """
    处理图片裁剪
    
    Returns:
        (cropped_image_bytes, original_size, new_size)
    """
    # 打开图片
    img = Image.open(io.BytesIO(image_data))
    original_width, original_height = img.size
    
    # 如果是RGBA模式且输出格式不支持透明，转换为RGB
    if img.mode == "RGBA" and output_format.lower() in ["jpeg", "jpg"]:
        # 创建白色背景
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3] if len(img.split()) == 4 else None)
        img = background
    elif img.mode != "RGB" and img.mode != "RGBA":
        img = img.convert("RGB")
    
    # 计算目标比例
    if aspect_ratio:
        # 解析比例字符串
        parts = aspect_ratio.split(":")
        if len(parts) != 2:
            raise ValueError(f"无效的比例格式: {aspect_ratio}，正确格式如 '16:9'")
        ratio_width, ratio_height = float(parts[0]), float(parts[1])
        target_ratio = ratio_width / ratio_height
    elif target_width and target_height:
        target_ratio = target_width / target_height
    elif target_width:
        # 只指定宽度，按原图比例
        target_ratio = target_width / (target_width * original_height / original_width)
    elif target_height:
        # 只指定高度，按原图比例
        target_ratio = (target_height * original_width / original_height) / target_height
    else:
        # 不裁剪，直接返回原图
        output_buffer = io.BytesIO()
        save_format = "JPEG" if output_format.lower() in ["jpeg", "jpg"] else output_format.upper()
        img.save(output_buffer, format=save_format)
        return output_buffer.getvalue(), (original_width, original_height), (original_width, original_height)
    
    # 计算裁剪区域
    crop_box = calculate_crop_box(original_width, original_height, target_ratio, mode)
    
    # 执行裁剪
    cropped_img = img.crop(crop_box)
    new_width, new_height = cropped_img.size
    
    # 如果指定了精确尺寸，进行缩放
    if target_width and target_height:
        cropped_img = cropped_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        new_width, new_height = target_width, target_height
    
    # 输出到字节流
    output_buffer = io.BytesIO()
    save_format = "JPEG" if output_format.lower() in ["jpeg", "jpg"] else output_format.upper()
    
    if save_format == "JPEG":
        cropped_img.save(output_buffer, format=save_format, quality=95)
    else:
        cropped_img.save(output_buffer, format=save_format)
    
    return output_buffer.getvalue(), (original_width, original_height), (new_width, new_height)


@router.post("/image/crop", summary="图片裁剪")
async def crop_image(
    file: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None),
    image_base64: Optional[str] = Form(None),
    aspect_ratio: Optional[str] = Form(None),
    width: Optional[int] = Form(None),
    height: Optional[int] = Form(None),
    mode: CropMode = Form("center"),
    output_format: str = Form("png"),
    return_base64: bool = Form(False),
    current_user: dict = Depends(get_current_user_or_ak)
):
    """
    图片裁剪接口
    
    支持三种图片输入方式（优先级从高到低）：
    1. file: 上传文件
    2. image_url: 图片URL地址
    3. image_base64: Base64编码的图片
    
    裁剪参数：
    - aspect_ratio: 目标比例，如 '16:9', '4:3', '1:1' 或自定义 '800:600'
    - width/height: 目标尺寸（可选，同时指定会缩放到精确尺寸）
    - mode: 裁剪方式
      - center: 居中裁剪
      - top: 顶部裁剪
      - bottom: 底部裁剪
      - left: 左侧裁剪
      - right: 右侧裁剪
      - top-left: 左上角裁剪
      - top-right: 右上角裁剪
      - bottom-left: 左下角裁剪
      - bottom-right: 右下角裁剪
    - output_format: 输出格式 (png/jpeg/webp)
    - return_base64: 是否返回base64，默认返回文件下载
    """
    try:
        import httpx
        
        # 获取图片数据
        image_data = None
        
        if file:
            # 从上传文件获取
            image_data = await file.read()
        elif image_url:
            # 从URL下载
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(image_url)
                if response.status_code != 200:
                    return error_response(400, f"下载图片失败: HTTP {response.status_code}")
                image_data = response.content
        elif image_base64:
            # 从base64解码
            # 移除可能的data:image/xxx;base64,前缀
            if "," in image_base64:
                image_base64 = image_base64.split(",")[1]
            image_data = base64.b64decode(image_base64)
        else:
            return error_response(400, "请提供图片：上传文件(file)、图片URL(image_url)或Base64数据(image_base64)")
        
        # 执行裁剪
        cropped_data, original_size, new_size = process_image_crop(
            image_data=image_data,
            aspect_ratio=aspect_ratio,
            target_width=width,
            target_height=height,
            mode=mode,
            output_format=output_format
        )
        
        # 返回结果
        if return_base64:
            # 返回base64
            base64_data = base64.b64encode(cropped_data).decode("utf-8")
            mime_type = f"image/{output_format.lower()}"
            return success_response({
                "width": new_size[0],
                "height": new_size[1],
                "original_width": original_size[0],
                "original_height": original_size[1],
                "format": output_format,
                "base64": f"data:{mime_type};base64,{base64_data}"
            })
        else:
            # 保存到临时文件并返回下载链接
            temp_dir = "./data/temp/cropped"
            os.makedirs(temp_dir, exist_ok=True)
            
            filename = f"cropped_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{output_format}"
            file_path = os.path.join(temp_dir, filename)
            
            with open(file_path, "wb") as f:
                f.write(cropped_data)
            
            return success_response({
                "width": new_size[0],
                "height": new_size[1],
                "original_width": original_size[0],
                "original_height": original_size[1],
                "format": output_format,
                "file_url": f"/api/v1/tools/image/download/{filename}",
                "filename": filename
            })
            
    except ValueError as e:
        return error_response(400, str(e))
    except Exception as e:
        return error_response(500, f"图片裁剪失败: {str(e)}")


@router.get("/image/download/{filename}", summary="下载裁剪后的图片")
async def download_cropped_image(
    filename: str,
    delete_after_download: bool = Query(True, description="下载后删除临时文件")
):
    """
    下载裁剪后的图片
    """
    try:
        temp_dir = os.path.abspath("./data/temp/cropped")
        safe_path = os.path.abspath(os.path.join(temp_dir, filename))
        
        # 安全检查
        if not safe_path.startswith(temp_dir):
            return error_response(403, "非法的文件路径请求")
        
        if not os.path.exists(safe_path):
            raise HTTPException(status_code=404, detail="文件不存在或已过期")
        
        def cleanup_file():
            try:
                if os.path.exists(safe_path) and delete_after_download:
                    os.remove(safe_path)
            except Exception:
                pass
        
        # 确定MIME类型
        ext = filename.rsplit(".", 1)[-1].lower()
        mime_map = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp"
        }
        media_type = mime_map.get(ext, "application/octet-stream")
        
        return FileResponse(
            path=safe_path,
            filename=filename,
            media_type=media_type,
            background=BackgroundTask(cleanup_file)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        return error_response(500, f"下载失败: {str(e)}")


@router.get("/image/proxy", summary="代理下载远程图片")
async def proxy_remote_image(
    url: str = Query(..., description="图片URL地址"),
    aspect_ratio: Optional[str] = Query(None, description="目标比例，如 '16:9', '4:3', '1:1'"),
    width: Optional[int] = Query(None, description="目标宽度"),
    height: Optional[int] = Query(None, description="目标高度"),
    mode: CropMode = Query("center", description="裁剪方式"),
    output_format: str = Query("png", description="输出格式：png, jpeg, webp")
):
    """
    代理下载远程图片，支持裁剪
    
    - url: 图片URL地址（需要URL编码）
    - aspect_ratio: 目标比例，如 '16:9'
    - width/height: 目标尺寸
    - mode: 裁剪方式 (center/top/bottom/left/right/top-left/top-right/bottom-left/bottom-right)
    - output_format: 输出格式
    """
    try:
        import httpx
        
        # 下载图片
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return error_response(400, f"下载图片失败: HTTP {response.status_code}")
            image_data = response.content
        
        # 判断是否需要裁剪
        if aspect_ratio or (width and height):
            # 执行裁剪
            cropped_data, original_size, new_size = process_image_crop(
                image_data=image_data,
                aspect_ratio=aspect_ratio,
                target_width=width,
                target_height=height,
                mode=mode,
                output_format=output_format
            )
        else:
            # 不裁剪，直接返回原图
            cropped_data = image_data
            try:
                img = Image.open(io.BytesIO(image_data))
                original_size = img.size
                new_size = img.size
                # 尝试从图片或URL推断格式
                img_format = img.format.lower() if img.format else "png"
                if img_format in ["jpeg", "jpg", "png", "webp"]:
                    output_format = img_format if img_format != "jpg" else "jpeg"
            except Exception:
                original_size = (0, 0)
                new_size = (0, 0)
        
        # 确定MIME类型
        mime_map = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp"
        }
        media_type = mime_map.get(output_format.lower(), "image/png")
        
        # 从URL提取文件名
        from urllib.parse import urlparse, unquote
        parsed_url = urlparse(url)
        path = unquote(parsed_url.path)
        original_filename = os.path.basename(path) if path else "image"
        if "." not in original_filename:
            original_filename = f"{original_filename}.{output_format}"
        else:
            # 替换扩展名
            original_filename = f"{os.path.splitext(original_filename)[0]}.{output_format}"
        
        return Response(
            content=cropped_data,
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{original_filename}"',
                "X-Original-Width": str(original_size[0]),
                "X-Original-Height": str(original_size[1]),
                "X-New-Width": str(new_size[0]),
                "X-New-Height": str(new_size[1])
            }
        )
        
    except ValueError as e:
        return error_response(400, str(e))
    except Exception as e:
        return error_response(500, f"图片处理失败: {str(e)}")