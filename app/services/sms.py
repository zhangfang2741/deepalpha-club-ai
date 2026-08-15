"""短信验证码（阿里云号码认证服务 PNVS / Dypnsapi）。

用的是「短信认证服务」而不是通用短信服务（dysmsapi），差别很实质：
- 免自建签名和模板的审核，用系统提供的签名模板，开通即可用；
- **验证码由阿里云生成、保管和核验**，我们不接触明文，也不自己存。

因此手机号这条链路和邮箱不同：邮箱是「本地生成码 → 存 Redis 哈希 → 本地比对」，
手机号是「调 SendSmsVerifyCode → 调 CheckSmsVerifyCode」，两次 API 调用。
Redis 这边只保留一个错误次数计数器（见下方 verify_code 的说明）。

签名算法仍是阿里云通用的 RPC v1.0，与 dysmsapi 完全一致，所以 build_signature
可以复用。用标准库自己实现而不引 aliyun SDK，理由同 app/services/email.py
用 smtplib：只需要两个接口，签名算法公开且稳定。
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
    """未配置阿里云短信认证凭据。"""


class SMSSendError(Exception):
    """短信发送失败。"""


class SMSResendTooSoonError(Exception):
    """阿里云侧判定重发过于频繁。"""


def is_configured() -> bool:
    """凭据与签名/模板是否齐全。

    签名和模板虽然免申请，但仍要在控制台选定后填进来——阿里云需要知道
    用哪一套系统模板发信。
    """
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


def _common_params(action: str) -> dict[str, str]:
    """RPC 公共参数。"""
    return {
        "AccessKeyId": settings.ALIYUN_SMS_ACCESS_KEY_ID,
        "Action": action,
        "Format": "JSON",
        "RegionId": settings.ALIYUN_SMS_REGION,
        "SignatureMethod": "HMAC-SHA1",
        # Nonce 防重放，必须每次不同
        "SignatureNonce": str(uuid.uuid4()),
        "SignatureVersion": "1.0",
        "Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Version": "2017-05-25",
    }


def _apply_scheme(params: dict[str, str]) -> None:
    """带上认证方案名。

    发码和核验必须用同一个 SchemeName，否则阿里云找不到对应的验证码记录，
    核验会一直返回 UNKNOWN。留空时不传该参数，走阿里云的「默认方案」。
    """
    if settings.ALIYUN_SMS_SCHEME_NAME:
        params["SchemeName"] = settings.ALIYUN_SMS_SCHEME_NAME


def build_send_params(phone: str, country_code: str) -> dict[str, str]:
    """组装 SendSmsVerifyCode 的参数（不含 Signature）。"""
    params = _common_params("SendSmsVerifyCode")
    params.update(
        {
            "PhoneNumber": phone,
            "CountryCode": country_code,
            "SignName": settings.ALIYUN_SMS_SIGN_NAME,
            "TemplateCode": settings.ALIYUN_SMS_TEMPLATE_CODE,
            # ##code## 是占位符，让阿里云按 CodeLength/CodeType 自动生成验证码
            # 并填进模板。我们全程不接触明文验证码。
            "TemplateParam": json.dumps(
                {"code": "##code##", "min": str(settings.EMAIL_CODE_TTL // 60)},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "CodeLength": "6",
            "ValidTime": str(settings.EMAIL_CODE_TTL),
            "Interval": str(settings.EMAIL_CODE_RESEND_COOLDOWN),
            # 1 = 新码覆盖旧码。默认允许多个码同时有效，那意味着用户连点三次
            # 之后三个码都能用，等于把爆破空间放大了三倍。
            "DuplicatePolicy": "1",
        }
    )
    _apply_scheme(params)
    return params


def build_check_params(phone: str, code: str, country_code: str) -> dict[str, str]:
    """组装 CheckSmsVerifyCode 的参数（不含 Signature）。"""
    params = _common_params("CheckSmsVerifyCode")
    params.update(
        {
            "PhoneNumber": phone,
            "VerifyCode": code,
            "CountryCode": country_code,
        }
    )
    _apply_scheme(params)
    return params


async def _call(params: dict[str, str]) -> dict:
    """签名并调用阿里云接口，返回解析后的响应体。"""
    params["Signature"] = build_signature(params, settings.ALIYUN_SMS_ACCESS_KEY_SECRET)
    try:
        async with httpx.AsyncClient(timeout=settings.SMS_TIMEOUT_SECONDS) as client:
            resp = await client.get(settings.ALIYUN_SMS_ENDPOINT, params=params)
        return resp.json()
    except Exception as exc:
        logger.exception("sms_request_failed", action=params.get("Action"), error=str(exc))
        raise SMSSendError from exc


async def send_verification_code(phone: str, country_code: str = "86") -> None:
    """让阿里云生成并发送一条验证码短信。

    Raises:
        SMSNotConfiguredError: 未配置凭据。
        SMSResendTooSoonError: 阿里云侧判定重发过于频繁。
        SMSSendError: 其它失败。
    """
    if not is_configured():
        raise SMSNotConfiguredError

    body = await _call(build_send_params(phone, country_code))

    if body.get("Code") != "OK":
        code = str(body.get("Code", ""))
        # 手机号属于个人信息，日志里只留后四位。
        logger.error(
            "sms_send_rejected",
            code=code,
            message=body.get("Message"),
            phone_suffix=phone[-4:],
        )
        # 阿里云对「发得太频繁」有专门的错误码，转成独立异常让上层给出
        # 「请稍后再试」而不是笼统的「发送失败」。
        if "FREQUENCY" in code.upper() or "LIMIT" in code.upper():
            raise SMSResendTooSoonError(body.get("Message") or code)
        raise SMSSendError(body.get("Message") or code)

    logger.info("sms_sent", phone_suffix=phone[-4:])


async def check_verification_code(phone: str, code: str, country_code: str = "86") -> bool:
    """向阿里云核验验证码，正确返回 True。

    ⚠️ 阿里云文档明确写了「接口调用成功不代表短信验证码核验成功」：请求本身
    成功时 Code 也是 OK，真正的结果在 Model.VerifyResult 里（PASS 才算通过）。
    只看 Code 的话任何验证码都能过——这是这个接口最容易写错的地方。

    Raises:
        SMSNotConfiguredError: 未配置凭据。
        SMSSendError: 请求失败（区别于「验证码不对」）。
    """
    if not is_configured():
        raise SMSNotConfiguredError

    body = await _call(build_check_params(phone, code, country_code))

    if body.get("Code") != "OK":
        logger.error(
            "sms_check_failed",
            code=body.get("Code"),
            message=body.get("Message"),
            phone_suffix=phone[-4:],
        )
        raise SMSSendError(body.get("Message") or body.get("Code"))

    result = (body.get("Model") or {}).get("VerifyResult")
    return result == "PASS"


__all__ = [
    "SMSNotConfiguredError",
    "SMSResendTooSoonError",
    "SMSSendError",
    "build_check_params",
    "build_send_params",
    "build_signature",
    "check_verification_code",
    "is_configured",
    "send_verification_code",
]
