"""
优化版批量文章导出。

修复原 apis/tools.py:_export_articles_worker 的几个性能问题：
1. 每篇文章都重启 Playwright 浏览器（耗时大头：~5-10s × N）。
2. 默认强制 chromium，绕过 BROWSER_TYPE=webkit 设置。
3. 同步串行处理且无任何进度上报。
4. 没有跳过无效文章（无 URL / 无 content），仍尝试渲染。

新实现：
* 复用单个 WebToPDFConverter 跨整批文章。
* 浏览器类型由 BROWSER_TYPE 环境变量或 config 决定，默认 webkit。
* 通过 progress_callback(stage, message, progress, **kw) 实时报告进度。
* 跳过无 URL / 无 content 的文章，但仍然将其计入"skipped"。
"""
from __future__ import annotations

import os
import sys
import asyncio
import json
import zipfile
import csv
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from core.common.file_tools import sanitize_filename
from core.print import print_success, print_error, print_warning


ProgressCallback = Optional[Callable[..., None]]


def _report(cb: ProgressCallback, stage: str, message: str, progress: int = 0, **kw: Any) -> None:
    if cb is None:
        return
    try:
        cb(stage=stage, message=message, progress=progress, **kw)
    except Exception:
        pass


def _normalize_browser_type() -> str:
    """选择 PDF 渲染浏览器：BROWSER_TYPE 环境变量 > 已安装的浏览器 > config。

    由于实际部署中 firefox / chromium / msedge 不一定都通过
    `playwright install` 安装过，这里探测 playwright 的浏览器缓存目录，
    优先选已安装的（webkit 总是优先 — 与上游保持一致）。
    """
    forced = os.environ.get("BROWSER_TYPE", "").strip().lower()
    if forced in ("webkit", "chromium", "firefox", "msedge"):
        return forced

    # 探测 playwright 缓存目录
    candidates = ["webkit", "chromium", "firefox", "msedge"]
    try:
        from pathlib import Path
        cache = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "ms-playwright"
        for c in candidates:
            if list(cache.glob(f"{c}-*")):
                return c
    except Exception:
        pass

    try:
        from core.config import cfg
        bt = cfg.get("gather.browser_type", "webkit")
        return str(bt or "webkit")
    except Exception:
        return "webkit"


async def _render_pdfs_in_batch(
    items: list[tuple[Any, str]],
    browser_type: str,
) -> dict[str, str]:
    """复用同一个浏览器，把 (article, target_pdf_path) 列表全部渲染。

    Returns: 映射 article.id -> 已生成的 PDF 路径（成功的）。
    """
    if not items:
        return {}
    from tools.mdtools.pdf import WebToPDFConverter

    results: dict[str, str] = {}
    async with WebToPDFConverter(
        headless=True,
        browser_type=browser_type,
        timeout=30000,
        wait_time=1500,
    ) as converter:
        for article, pdf_path in items:
            try:
                port = "8001"
                try:
                    from core.config import cfg
                    port = str(cfg.get("port", "8001"))
                except Exception:
                    pass
                url = (
                    article.url
                    if not (hasattr(article, "content") and (article.content or ""))
                    else f"http://127.0.0.1:{port}/views/print/{article.id}"
                )
                ok = await converter.convert_url_to_pdf(
                    url=url,
                    output_path=pdf_path,
                )
                if ok and os.path.exists(pdf_path):
                    results[article.id] = pdf_path
            except Exception as e:
                print_warning(f"渲染 PDF 失败 {article.id}: {e}")
    return results


def _export_articles_optimized(
    *,
    session,
    mp_id: str,
    doc_id: Optional[list],
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
    docx_path: str,
    progress_callback: ProgressCallback = None,
) -> dict[str, int]:
    """同步包装的批量导出，返回 {total, processed, skipped}。"""
    return asyncio.run(
        _export_articles_async(
            session=session,
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
            docx_path=docx_path,
            progress_callback=progress_callback,
        )
    )


async def _export_articles_async(
    *,
    session,
    mp_id: str,
    doc_id: Optional[list],
    page_size: int,
    page_count: int,
    add_title: bool,
    remove_images: bool,
    remove_links: bool,
    export_md: bool,
    export_json: bool,
    export_csv: bool,
    export_pdf: bool,
    export_docx: bool,
    docx_path: str,
    progress_callback: ProgressCallback = None,
) -> dict[str, int]:
    """异步批量导出。"""
    from core.models import Article

    # 1. 计数
    _report(progress_callback, "counting", "正在统计文章数…", 0)
    base_q = session.query(Article).filter(
        Article.content != None,  # noqa: E711
        Article.status == 1,
    )
    if mp_id:
        base_q = base_q.where(Article.mp_id.in_(mp_id.split(",")))
    if doc_id:
        base_q = base_q.where(Article.id.in_(doc_id))
    base_q = base_q.order_by(Article.publish_time.desc(), Article.id.desc())

    # 限制 page_count（0 表示全部）
    if page_count and page_count > 0:
        base_q = base_q.limit(page_size * page_count)

    all_articles = base_q.all()
    total = len(all_articles)
    _report(
        progress_callback, "counting",
        f"找到 {total} 篇文章", 5,
        total_records=total,
    )

    if total == 0:
        return {"total": 0, "processed": 0, "skipped": 0}

    # 2. 跳过无效
    valid_articles = []
    skipped = 0
    for art in all_articles:
        if not (hasattr(art, "content") and (art.content or "")):
            skipped += 1
            continue
        if not (art.url or ""):
            skipped += 1
            continue
        valid_articles.append(art)

    _report(
        progress_callback, "preparing",
        f"将处理 {len(valid_articles)} 篇，跳过 {skipped} 篇", 10,
        skipped_records=skipped,
    )

    # 3. 准备输出目录、文件名
    os.makedirs(docx_path, exist_ok=True)
    article_paths = []
    for art in valid_articles:
        name = (
            datetime.fromtimestamp(art.publish_time, tz=timezone.utc).strftime("%Y%m%d")
            + "_" + art.title
        )
        safe = sanitize_filename(name)
        article_paths.append((art, safe))

    # 4. 渲染 PDF（如果需要）—— 复用单个浏览器
    pdf_paths: dict[str, str] = {}
    if export_pdf or export_docx:
        browser_type = _normalize_browser_type()
        _report(
            progress_callback, "rendering_pdfs",
            f"使用 {browser_type} 浏览器渲染 {len(valid_articles)} 个 PDF…", 15,
        )
        items = [(art, os.path.join(docx_path, f"{safe}.pdf")) for art, safe in article_paths]
        pdf_paths = await _render_pdfs_in_batch(items, browser_type)
        print_success(f"PDF 渲染完成：{len(pdf_paths)}/{len(items)}")

    # 5. 其它格式（MD/JSON/CSV 全部同步处理 + DOCX 转换）
    processed = 0
    csv_file = None
    csv_writer = None
    if export_csv:
        csv_file = open(os.path.join(docx_path, "articles.csv"), "w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["标题", "链接", "发布时间"])

    try:
        for idx, (art, safe) in enumerate(article_paths):
            base_progress = 30 + int(60 * idx / max(1, len(article_paths)))
            _report(
                progress_callback, "writing_files",
                f"处理 {idx + 1}/{len(article_paths)}: {art.title[:30]}", base_progress,
                processed_records=processed,
            )

            # Markdown
            if export_md and art.content:
                try:
                    from tools.mdtools.html2doc import html_to_markdown_file
                    md_path = os.path.join(docx_path, f"{safe}.md")
                    cfg_local = {
                        "remove_images": remove_images,
                        "remove_links": remove_links,
                    }
                    document_title = art.title if add_title else None
                    html_to_markdown_file(art.content, md_path, document_title, cfg_local)
                except Exception as e:
                    print_warning(f"Markdown 失败 {art.id}: {e}")

            # DOCX（PDF -> DOCX）
            if export_docx and art.id in pdf_paths:
                try:
                    from tools.mdtools.pdf_extractor import pdf_to_docx
                    pdf_path = pdf_paths[art.id]
                    docx_path_full = os.path.join(docx_path, f"{safe}.docx")
                    pdf_to_docx(pdf_path, docx_path_full)
                except Exception as e:
                    print_warning(f"DOCX 失败 {art.id}: {e}")

            # JSON
            if export_json:
                try:
                    json_path = os.path.join(docx_path, f"{safe}.json")
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump({
                            "id": art.id,
                            "url": art.url,
                            "title": art.title,
                            "pic_url": art.pic_url,
                            "description": art.description,
                            "status": art.status,
                            "publish_time": art.publish_time,
                        }, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print_warning(f"JSON 失败 {art.id}: {e}")

            # CSV
            if export_csv and csv_writer:
                try:
                    csv_writer.writerow([
                        art.title,
                        art.url,
                        datetime.fromtimestamp(art.publish_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    ])
                except Exception as e:
                    print_warning(f"CSV 失败 {art.id}: {e}")

            processed += 1

    finally:
        if csv_file:
            csv_file.close()

    return {
        "total": total,
        "processed": processed,
        "skipped": skipped,
        "pdf_rendered": len(pdf_paths),
    }