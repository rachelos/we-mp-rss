"""微信读书 Cookie 定时自动续期（调度在项目/容器内，浏览器动作走宿主机代理）。

设计（用户需求：每 2 小时一次，未过期续期、已过期什么都不做）：
- 调度：挂在项目全局 scheduler 上（main.py 启动时注册，reload_job 重载时保留），
  每 2 小时执行一次，不依赖消息任务是否开启；
- 检查：读取 wx.lic 的 cookie 并做真实接口验证；
  - 有效 → 调宿主机代理 /renew 做无头续期（headless_only、不弹窗、抓最新 cookie 写回）；
  - 无效/已过期 → 静默跳过，绝不触发弹窗/扫码（登录仍由用户手动完成）。
"""

import os
import json
import urllib.request


def _agent_base_url() -> str:
    url = (os.environ.get("WEREAD_REFRESH_AGENT_URL")
           or "http://host.docker.internal:9876").strip()
    if url.endswith("/refresh"):
        url = url[: -len("/refresh")]
    return url.rstrip("/")


def renew_weread_cookie():
    """每 2 小时执行一次：cookie 有效则续期，无效则跳过。"""
    try:
        from core.weread_cookie_refresh import _load_weread_data, _verify_cookie
        _doc, data = _load_weread_data()
        cookie = (data.get("cookie") or "").strip()
    except Exception as e:
        print(f"[weread-renew] 读取 cookie 失败: {e}")
        return

    if not cookie:
        print("[weread-renew] 未配置 cookie，跳过自动续期")
        return

    # 已过期 → 什么都不做（等用户手动登录），绝不开窗
    if not _verify_cookie(cookie):
        print("[weread-renew] cookie 已过期/无效，跳过自动续期（等待手动登录）")
        return

    # 未过期 → 请宿主机做无头续期（headless_only，不弹窗）
    try:
        req = urllib.request.Request(
            _agent_base_url() + "/renew",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        print(f"[weread-renew] 续期结果: ok={payload.get('ok')}, {payload.get('message')}")
    except Exception as e:
        print(f"[weread-renew] 调用宿主续期代理失败: {e}")


def start_weread_renew():
    """注册每 2 小时执行一次的续期任务（挂在全局 scheduler 上）。"""
    from core.print import print_success
    from jobs.mps import scheduler

    scheduler.add_cron_job(
        renew_weread_cookie,
        cron_expr="0 */2 * * *",  # 每 2 小时整点
        job_id="weread_cookie_renew",
        tag="微信读书Cookie自动续期",
    )
    print_success("已开启微信读书 Cookie 每 2 小时自动续期（有效则续期，过期则跳过）")


if __name__ == "__main__":
    renew_weread_cookie()
