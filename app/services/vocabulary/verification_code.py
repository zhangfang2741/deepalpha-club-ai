"""验证码的签发与校验：邮箱和手机号、注册和找回密码，四种组合共用一套。

各场景对验证码的要求完全一样（一次性、限时、防爆破、防轰炸），只有用途和
送达渠道不同，所以用 Purpose 区分命名空间而不是复制多份实现。命名空间隔离
也顺带堵掉一类漏洞：拿注册时收到的验证码去重置别人的密码。

identifier 是邮箱或 E.164 手机号。模块本身不关心它是什么，只把它当成一个
不透明的字符串来哈希、比对——发信/发短信由调用方按渠道自己选。

验证码存 Redis 而不是数据库：天然带 TTL、过期自动清理。注册场景下更是关键——
用户还没建号，本来就没有地方存这个中间状态。

安全上的几点考虑：
- 存哈希不存明文。Redis 快照、慢查询日志、运维误看都可能泄露 value，
  而验证码在有效期内等同于账号的临时钥匙。
- key 里用标识符的哈希而不是本身，避免 `KEYS vocab:vercode:*` 直接扫出一份
  「最近在注册/找回密码的用户」名单——手机号泄露比邮箱更敏感。
- 错误次数用尽立即作废，不靠等它自然过期——6 位数字只有 100 万种可能，
  10 分钟内不限次数猜是能撞开的。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from enum import Enum

from redis.asyncio import Redis

from app.cache import operations as cache
from app.core.config import settings

_PREFIX = "vocab:vercode"


class Purpose(str, Enum):
    """验证码用途。不同用途的验证码互不通用。"""

    REGISTER = "register"
    PASSWORD_RESET = "pwreset"
    PHONE_REGISTER = "phone_register"
    PHONE_PASSWORD_RESET = "phone_pwreset"


class ResendTooSoonError(Exception):
    """距上次发送还在冷却期内。"""


class TooManyAttemptsError(Exception):
    """错误次数用尽，验证码已作废。"""


def generate_code() -> str:
    """生成 6 位数字验证码。

    用 secrets 而不是 random：random 是可预测的 Mersenne Twister，
    观察到若干输出就能推出后续值，用来做安全凭据不合适。
    """
    return f"{secrets.randbelow(1_000_000):06d}"


def _hash_code(code: str) -> str:
    """验证码哈希。加 JWT 密钥当盐，防止彩虹表直接反查 6 位数字。"""
    return hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"), code.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _slug(identifier: str) -> str:
    """标识符 → 定长哈希，用作 key 的一部分，避免明文邮箱/手机号落进 Redis key。"""
    return hashlib.sha256(identifier.lower().encode("utf-8")).hexdigest()[:32]


def _code_key(purpose: Purpose, identifier: str) -> str:
    return f"{_PREFIX}:{purpose.value}:code:{_slug(identifier)}"


def _attempts_key(purpose: Purpose, identifier: str) -> str:
    return f"{_PREFIX}:{purpose.value}:attempts:{_slug(identifier)}"


def _cooldown_key(purpose: Purpose, identifier: str) -> str:
    return f"{_PREFIX}:{purpose.value}:cooldown:{_slug(identifier)}"


async def issue_code(redis: Redis, purpose: Purpose, identifier: str) -> str:
    """签发一个新验证码并写入 Redis，返回明文供发信使用。

    Raises:
        ResendTooSoonError: 距上次发送不足冷却时间。
    """
    if await cache.exists(redis, _cooldown_key(purpose, identifier)):
        raise ResendTooSoonError

    code = generate_code()
    ttl = settings.EMAIL_CODE_TTL

    # 重新签发时把旧的错误计数一并覆盖，否则上一轮攒下的次数会误伤这一轮。
    await cache.set(redis, _code_key(purpose, identifier), _hash_code(code), expire=ttl)
    await cache.set(redis, _attempts_key(purpose, identifier), 0, expire=ttl)
    await cache.set(
        redis,
        _cooldown_key(purpose, identifier),
        1,
        expire=settings.EMAIL_CODE_RESEND_COOLDOWN,
    )
    return code


async def verify_code(redis: Redis, purpose: Purpose, identifier: str, code: str) -> bool:
    """校验验证码。正确则消费掉并返回 True；错误返回 False。

    Raises:
        TooManyAttemptsError: 错误次数达到上限，验证码已作废。
    """
    stored = await cache.get(redis, _code_key(purpose, identifier))
    if stored is None:
        return False

    # compare_digest 而不是 ==：避免按字符短路比较泄露前缀匹配长度。
    if hmac.compare_digest(stored, _hash_code(code)):
        await _clear(redis, purpose, identifier)
        return True

    attempts = await redis.incr(_attempts_key(purpose, identifier))
    if attempts >= settings.EMAIL_CODE_MAX_ATTEMPTS:
        await _clear(redis, purpose, identifier)
        raise TooManyAttemptsError
    return False


async def discard_code(redis: Redis, purpose: Purpose, identifier: str) -> None:
    """作废刚签发的验证码，并解除冷却。

    发信失败时调用。冷却标记的意义是「已经给你发过一封了，别再刷」，可信没发出去
    的时候它就纯属误伤——用户会被一次临时故障锁在门外 60 秒，而且那 60 秒里
    他做什么都没用。既然没发成，就当这次请求没发生过。
    """
    await _clear(redis, purpose, identifier)
    await cache.delete(redis, _cooldown_key(purpose, identifier))


async def _clear(redis: Redis, purpose: Purpose, identifier: str) -> None:
    """清掉验证码与计数。冷却标记保留，让它自己过期，避免被用来刷发信。"""
    await cache.delete(redis, _code_key(purpose, identifier))
    await cache.delete(redis, _attempts_key(purpose, identifier))
