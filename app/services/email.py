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


def _send_sync(to: str, subject: str, html: str, text: str, from_name: str) -> None:
    """同步发信。由 send_email 放进线程执行。"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8").encode()
    # formataddr 会正确处理中文发件人名的编码，手拼字符串容易发出乱码。
    msg["From"] = formataddr((str(Header(from_name, "utf-8")), settings.SMTP_USER))
    msg["To"] = to
    # 同时带纯文本和 HTML：部分邮件客户端（尤其国内的）默认不渲染 HTML，
    # 也有反垃圾策略会给纯 HTML 的邮件降权。
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    # 465 是隐式 SSL；25/80 是明文端口，连上后用 STARTTLS 升级。
    #
    # 为什么要支持 80：不少 PaaS（含 Railway）为防垃圾邮件滥用会封禁出站 25/465，
    # 且是静默丢包而不是拒绝连接，表现为一直挂到超时。阿里云邮件推送正是为此
    # 额外提供了 80 端口。凭据和协议都不变，只是走一个不会被封的端口。
    if settings.SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS
        )
    else:
        server = smtplib.SMTP(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS
        )

    with server:
        if settings.SMTP_PORT != 465:
            # 明文端口上必须升级到 TLS 再登录，否则 SMTP 密码是明文过网的。
            server.starttls()
            server.ehlo()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_USER, [to], msg.as_string())


async def send_email(
    to: str, subject: str, html: str, text: str, from_name: str | None = None
) -> None:
    """发送一封邮件。

    Raises:
        EmailNotConfiguredError: 未配置 SMTP 凭据。
        EmailSendError: 发信失败。
    """
    if not is_configured():
        raise EmailNotConfiguredError

    try:
        await asyncio.to_thread(
            _send_sync, to, subject, html, text, from_name or settings.SMTP_FROM_NAME
        )
    except Exception as exc:
        # 收件地址属于个人信息，日志里只留域名部分，够定位「某个邮箱域整体投递失败」
        # 这类问题，又不至于把用户邮箱写满日志。
        domain = to.rsplit("@", 1)[-1] if "@" in to else "unknown"
        logger.exception("email_send_failed", to_domain=domain, error=str(exc))
        raise EmailSendError from exc

    logger.info("email_sent", to_domain=to.rsplit("@", 1)[-1] if "@" in to else "unknown")


def _render_code_email(
    code: str, ttl_minutes: int, heading: str, lead: str, footer_note: str, brand: str
) -> tuple[str, str, str]:
    """渲染一封验证码邮件，返回 (主题, HTML, 纯文本)。

    刻意做得朴素：验证码类邮件带一堆图片和外链，反垃圾系统更容易判成垃圾邮件，
    而且用户其实只想找那 6 个数字。

    brand 由调用方传入而不是在这里读配置：同一套 SMTP 服务于多个 App，
    署名得跟着 App 走。
    """
    subject = f"{brand} {heading}验证码：{code}"

    text = f"{lead}\n\n验证码：{code}\n\n验证码 {ttl_minutes} 分钟内有效，请勿转发给他人。\n{footer_note}\n"

    html = f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<body style="margin:0;padding:24px;background:#f5f6f8;
             font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;">
  <div style="max-width:440px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;">
    <p style="margin:0 0 8px;font-size:16px;color:#111;">{heading}</p>
    <p style="margin:0 0 24px;font-size:14px;color:#666;line-height:1.6;">{lead}</p>
    <div style="font-size:34px;font-weight:700;letter-spacing:8px;color:#111;
                text-align:center;padding:18px;background:#f5f6f8;border-radius:8px;">
      {code}
    </div>
    <p style="margin:24px 0 0;font-size:13px;color:#888;line-height:1.6;">
      验证码 {ttl_minutes} 分钟内有效，请勿转发给他人。<br>{footer_note}
    </p>
  </div>
</body>
</html>"""

    return subject, html, text


def render_password_reset(
    code: str, ttl_minutes: int, brand: str | None = None
) -> tuple[str, str, str]:
    """渲染找回密码邮件。brand 为 None 时用默认发信名，保持既有调用方行为不变。"""
    brand = brand or settings.SMTP_FROM_NAME
    return _render_code_email(
        code,
        ttl_minutes,
        heading="重置密码",
        lead=f"你正在重置「{brand}」账号的密码，请在 App 中输入以下验证码：",
        footer_note="如果这不是你本人的操作，忽略这封邮件即可，你的密码不会有任何变化。",
        brand=brand,
    )


def render_register(
    code: str, ttl_minutes: int, brand: str | None = None
) -> tuple[str, str, str]:
    """渲染注册验证邮件。brand 为 None 时用默认发信名。"""
    brand = brand or settings.SMTP_FROM_NAME
    return _render_code_email(
        code,
        ttl_minutes,
        heading="验证邮箱",
        lead=f"你正在注册「{brand}」账号，请在 App 中输入以下验证码完成注册：",
        footer_note="如果这不是你本人的操作，忽略这封邮件即可，不会有账号被创建。",
        brand=brand,
    )
