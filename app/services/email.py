"""邮件发送（阿里云邮件推送的 SMTP 接入）。

用标准库 smtplib 而不是阿里云 SDK：目前只需要发验证码这一种简单邮件，
为此拉进一整套云厂商 SDK 不划算，而且 SMTP 是通用协议，将来换供应商
（SendGrid / Resend / 自建 Postfix）只改环境变量就行，不用动代码。

smtplib 是阻塞的，统一用 asyncio.to_thread 包一层，避免堵住事件循环——
和仓库里 database_service 的调用方式保持一致。
"""
from __future__ import annotations

import asyncio
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from app.core.config import settings
from app.core.logging import logger


class EmailNotConfiguredError(Exception):
    """未配置 SMTP 凭据。"""


class EmailSendError(Exception):
    """发信失败。"""


def is_configured() -> bool:
    """SMTP 凭据是否齐全。"""
    return bool(settings.SMTP_USER and settings.SMTP_PASSWORD)


def _send_sync(to: str, subject: str, html: str, text: str) -> None:
    """同步发信。由 send_email 放进线程执行。"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8").encode()
    # formataddr 会正确处理中文发件人名的编码，手拼字符串容易发出乱码。
    msg["From"] = formataddr((str(Header(settings.SMTP_FROM_NAME, "utf-8")), settings.SMTP_USER))
    msg["To"] = to
    # 同时带纯文本和 HTML：部分邮件客户端（尤其国内的）默认不渲染 HTML，
    # 也有反垃圾策略会给纯 HTML 的邮件降权。
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL(
        settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS
    ) as server:
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_USER, [to], msg.as_string())


async def send_email(to: str, subject: str, html: str, text: str) -> None:
    """发送一封邮件。

    Raises:
        EmailNotConfiguredError: 未配置 SMTP 凭据。
        EmailSendError: 发信失败。
    """
    if not is_configured():
        raise EmailNotConfiguredError

    try:
        await asyncio.to_thread(_send_sync, to, subject, html, text)
    except Exception as exc:
        # 收件地址属于个人信息，日志里只留域名部分，够定位「某个邮箱域整体投递失败」
        # 这类问题，又不至于把用户邮箱写满日志。
        domain = to.rsplit("@", 1)[-1] if "@" in to else "unknown"
        logger.exception("email_send_failed", to_domain=domain, error=str(exc))
        raise EmailSendError from exc

    logger.info("email_sent", to_domain=to.rsplit("@", 1)[-1] if "@" in to else "unknown")


def render_password_reset(code: str, ttl_minutes: int) -> tuple[str, str, str]:
    """渲染找回密码邮件，返回 (主题, HTML, 纯文本)。

    刻意做得朴素：验证码类邮件带一堆图片和外链，反垃圾系统更容易判成垃圾邮件，
    而且用户其实只想找那 6 个数字。
    """
    subject = f"{settings.SMTP_FROM_NAME} 密码重置验证码：{code}"

    text = (
        f"你正在重置「{settings.SMTP_FROM_NAME}」账号的密码。\n\n"
        f"验证码：{code}\n\n"
        f"验证码 {ttl_minutes} 分钟内有效，请勿转发给他人。\n"
        f"如果这不是你本人的操作，忽略这封邮件即可，你的密码不会有任何变化。\n"
    )

    html = f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<body style="margin:0;padding:24px;background:#f5f6f8;
             font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;">
  <div style="max-width:440px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;">
    <p style="margin:0 0 8px;font-size:16px;color:#111;">重置密码</p>
    <p style="margin:0 0 24px;font-size:14px;color:#666;line-height:1.6;">
      你正在重置「{settings.SMTP_FROM_NAME}」账号的密码，请在 App 中输入以下验证码：
    </p>
    <div style="font-size:34px;font-weight:700;letter-spacing:8px;color:#111;
                text-align:center;padding:18px;background:#f5f6f8;border-radius:8px;">
      {code}
    </div>
    <p style="margin:24px 0 0;font-size:13px;color:#888;line-height:1.6;">
      验证码 {ttl_minutes} 分钟内有效，请勿转发给他人。<br>
      如果这不是你本人的操作，忽略这封邮件即可，你的密码不会有任何变化。
    </p>
  </div>
</body>
</html>"""

    return subject, html, text
