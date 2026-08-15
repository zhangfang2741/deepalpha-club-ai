"""短信发送（阿里云短信服务 SendSms）。

用标准库自己算 RPC 签名，不引入 aliyun-python-sdk-core：
- 只需要 SendSms 这一个接口，为它拉进一整套 SDK（及其对 python-dateutil、
  jmespath 等的传递依赖）不划算；
- 签名算法是公开且稳定的 RPC v1.0 规范，用 hmac + urllib 三十行就能实现；
- 和 app/services/email.py 用 smtplib 而不是阿里云 SDK 是同一个取舍。

⚠️ 与邮件不同，短信在国内是强监管业务：签名（SignName）和模板（TemplateCode）
都必须先在控制台申请并通过审核才能使用，审核不通过时接口会返回业务错误码而不是
HTTP 错误。凭据留空时视为未配置，调用方应据此降级。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.parse
import uuid
from datetime import UTC, datetime

import httpx

from app.core.config import settings
from app.core.logging import logger


class SMSNotConfiguredError(Exception):
    """未配置阿里云短信凭据。"""


class SMSSendError(Exception):
    """短信发送失败。"""


def is_configured() -> bool:
    """短信凭据与签名/模板是否齐全。"""
    return bool(
        settings.ALIYUN_SMS_ACCESS_KEY_ID
        and settings.ALIYUN_SMS_ACCESS_KEY_SECRET
        and settings.ALIYUN_SMS_SIGN_NAME
        and settings.ALIYUN_SMS_TEMPLATE_CODE
    )


def _percent_encode(value: str) -> str:
    """阿里云 RPC 签名要求的 URL 编码。

    在标准 quote 之上做三处修正：加号要编码成 %20、星号编码成 %2A、
    而 %7E 要还原成波浪号。这是签名算法明文规定的，差一个字符签名就对不上。
    """
    encoded = urllib.parse.quote(value, safe="")
    return encoded.replace("+", "%20").replace("*", "%2A").replace("%7E", "~")


def build_signature(params: dict[str, str], secret: str, method: str = "GET") -> str:
    """按阿里云 RPC v1.0 规范计算签名。

    规范要求：参数按键名字典序排序 → 逐对百分号编码后用 & 连接 → 组装成
    `METHOD&%2F&<编码后的查询串>` → 用 `secret + "&"` 作为密钥算 HMAC-SHA1 →
    Base64。密钥末尾那个 & 不是笔误，是规范的一部分，漏掉会一直签名失败。
    """
    canonical = "&".join(
        f"{_percent_encode(k)}={_percent_encode(params[k])}" for k in sorted(params)
    )
    string_to_sign = f"{method}&{_percent_encode('/')}&{_percent_encode(canonical)}"
    digest = hmac.new(
        f"{secret}&".encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _build_params(phone: str, template_param: dict[str, str]) -> dict[str, str]:
    """组装 SendSms 的公共参数与业务参数（不含 Signature）。"""
    return {
        # 公共参数
        "AccessKeyId": settings.ALIYUN_SMS_ACCESS_KEY_ID,
        "Action": "SendSms",
        "Format": "JSON",
        "RegionId": settings.ALIYUN_SMS_REGION,
        "SignatureMethod": "HMAC-SHA1",
        # Nonce 防重放，必须每次不同
        "SignatureNonce": str(uuid.uuid4()),
        "SignatureVersion": "1.0",
        "Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2017-05-25",
        # 业务参数
        "PhoneNumbers": phone,
        "SignName": settings.ALIYUN_SMS_SIGN_NAME,
        "TemplateCode": settings.ALIYUN_SMS_TEMPLATE_CODE,
        # 模板变量必须是紧凑 JSON：阿里云按字符串原样参与签名，
        # json.dumps 默认的 ", " 分隔符会让签名与实际发送内容不一致。
        "TemplateParam": json.dumps(template_param, ensure_ascii=False, separators=(",", ":")),
    }


async def send_verification_code(phone: str, code: str) -> None:
    """给手机号发送验证码短信。

    Args:
        phone: E.164 或国内 11 位手机号。国际号码阿里云要求 00 开头的格式，
            由调用方在 to_aliyun_format 里转换。
        code: 6 位验证码，会填进模板的 ${code} 变量。

    Raises:
        SMSNotConfiguredError: 未配置凭据/签名/模板。
        SMSSendError: 网络异常或阿里云返回业务错误。
    """
    if not is_configured():
        raise SMSNotConfiguredError

    params = _build_params(phone, {"code": code})
    params["Signature"] = build_signature(params, settings.ALIYUN_SMS_ACCESS_KEY_SECRET)

    try:
        async with httpx.AsyncClient(timeout=settings.SMS_TIMEOUT_SECONDS) as client:
            resp = await client.get(settings.ALIYUN_SMS_ENDPOINT, params=params)
        body = resp.json()
    except Exception as exc:
        logger.exception("sms_send_request_failed", error=str(exc))
        raise SMSSendError from exc

    # 阿里云对业务失败也返回 HTTP 200，必须看 Code 字段。
    if body.get("Code") != "OK":
        # 手机号属于个人信息，日志里只留后四位，够定位「某号段整体失败」
        # 这类问题，又不至于把用户手机号写满日志。
        logger.error(
            "sms_send_rejected",
            code=body.get("Code"),
            message=body.get("Message"),
            phone_suffix=phone[-4:],
        )
        raise SMSSendError(body.get("Message") or body.get("Code"))

    logger.info("sms_sent", phone_suffix=phone[-4:])


__all__ = [
    "SMSNotConfiguredError",
    "SMSSendError",
    "build_signature",
    "is_configured",
    "send_verification_code",
]
