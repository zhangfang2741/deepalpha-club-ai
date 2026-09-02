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


class SMSCodeInvalidError(Exception):
    """验证码不存在、已过期或不匹配（业务层面的失败，不是系统故障）。"""


def is_configured() -> bool:
    """凭据与签名/模板是否齐全。

    模板 CODE 有内置默认值（系统赠送模板），签名必须显式配置——赠送签名有好几个，
    阿里云不知道该用哪一个。
    """
    return bool(
        settings.ALIYUN_SMS_ACCESS_KEY_ID
        and settings.ALIYUN_SMS_ACCESS_KEY_SECRET
        and settings.ALIYUN_SMS_SIGN_NAME
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


def build_send_params(phone: str, country_code: str, template_code: str) -> dict[str, str]:
    """组装 SendSmsVerifyCode 的参数（不含 Signature）。"""
    params = _common_params("SendSmsVerifyCode")
    params.update(
        {
            "PhoneNumber": phone,
            "CountryCode": country_code,
            "SignName": settings.ALIYUN_SMS_SIGN_NAME,
            "TemplateCode": template_code,
            # 系统模板的两个变量就叫 code 和 min（「您的验证码为${code}。以上
            # 验证码${min}分钟内有效」）。##code## 是占位符，让阿里云按
            # CodeLength 自动生成验证码填进去，我们全程不接触明文。
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


async def send_verification_code(
    phone: str, template_code: str, country_code: str = "86"
) -> None:
    """让阿里云生成并发送一条验证码短信。

    Args:
        phone: 阿里云格式的手机号（国内 11 位裸号 / 国际 00 开头）。
        template_code: 按用途选定的系统模板，见 settings.ALIYUN_SMS_TEMPLATE_*。
        country_code: 国家码。

    Raises:
        SMSNotConfiguredError: 未配置凭据。
        SMSResendTooSoonError: 阿里云侧判定重发过于频繁。
        SMSSendError: 其它失败。
    """
    if not is_configured():
        raise SMSNotConfiguredError

    body = await _call(build_send_params(phone, country_code, template_code))

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
        SMSCodeInvalidError: 验证码不存在/已过期（业务失败）。
        SMSSendError: 系统故障（鉴权失败、网络异常等）。
    """
    if not is_configured():
        raise SMSNotConfiguredError

    body = await _call(build_check_params(phone, code, country_code))

    if body.get("Code") != "OK":
        err = str(body.get("Code", ""))
        logger.warning(
            "sms_check_rejected",
            code=err,
            message=body.get("Message"),
            phone_suffix=phone[-4:],
        )
        # 阿里云用 isv. 前缀区分「业务层面的失败」和「系统/鉴权错误」。
        # 验证码不存在、已过期、不匹配都属于前者，对用户来说就是「验证码错误」，
        # 该返回 400；把它和 InvalidAccessKeyId 这类混为一谈会让用户看到
        # 「请稍后再试」——他再试一百次也没用，问题出在他输错了。
        if err.startswith("isv."):
            raise SMSCodeInvalidError(err)
        raise SMSSendError(body.get("Message") or err)

    result = (body.get("Model") or {}).get("VerifyResult")
    return result == "PASS"


__all__ = [
    "SMSCodeInvalidError",
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
