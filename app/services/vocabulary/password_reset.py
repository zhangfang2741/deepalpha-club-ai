"""找回密码的验证码签发与校验。

验证码存 Redis 而不是数据库：天然带 TTL、过期自动清理，也不会给
vocabulary_users 表加一堆临时字段。

安全上的几点考虑：
- 存哈希不存明文。Redis 快照、慢查询日志、运维误看都可能泄露 value，
  而验证码在有效期内等同于账号的临时钥匙。
- key 里用邮箱的哈希而不是邮箱本身，避免 `KEYS vocab:pwreset:*` 直接
  扫出一份「最近在找回密码的用户」名单。
- 错误次数用尽立即作废，不靠等它自然过期——6 位数字只有 100 万种可能，
  10 分钟内不限次数猜是能撞开的。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from redis.asyncio import Redis

from app.cache import operations as cache
from app.core.config import settings

_PREFIX = "vocab:pwreset"


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


def _slug(email: str) -> str:
    """邮箱 → 定长哈希，用作 key 的一部分，避免明文邮箱落进 Redis key。"""
    return hashlib.sha256(email.lower().encode("utf-8")).hexdigest()[:32]


def _code_key(email: str) -> str:
    return f"{_PREFIX}:code:{_slug(email)}"


def _attempts_key(email: str) -> str:
    return f"{_PREFIX}:attempts:{_slug(email)}"


def _cooldown_key(email: str) -> str:
    return f"{_PREFIX}:cooldown:{_slug(email)}"


async def issue_code(redis: Redis, email: str) -> str:
    """签发一个新验证码并写入 Redis，返回明文供发信使用。

    Raises:
        ResendTooSoonError: 距上次发送不足冷却时间。
    """
    if await cache.exists(redis, _cooldown_key(email)):
        raise ResendTooSoonError

    code = generate_code()
    ttl = settings.PASSWORD_RESET_CODE_TTL

    # 重新签发时把旧的错误计数一并覆盖，否则上一轮攒下的次数会误伤这一轮。
    await cache.set(redis, _code_key(email), _hash_code(code), expire=ttl)
    await cache.set(redis, _attempts_key(email), 0, expire=ttl)
    await cache.set(
        redis, _cooldown_key(email), 1, expire=settings.PASSWORD_RESET_RESEND_COOLDOWN
    )
    return code


async def verify_code(redis: Redis, email: str, code: str) -> bool:
    """校验验证码。正确则消费掉并返回 True；错误返回 False。

    Raises:
        TooManyAttemptsError: 错误次数达到上限，验证码已作废。
    """
    stored = await cache.get(redis, _code_key(email))
    if stored is None:
        return False

    # compare_digest 而不是 ==：避免按字符短路比较泄露前缀匹配长度。
    if hmac.compare_digest(stored, _hash_code(code)):
        await _clear(redis, email)
        return True

    attempts = await redis.incr(_attempts_key(email))
    if attempts >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
        await _clear(redis, email)
        raise TooManyAttemptsError
    return False


async def discard_code(redis: Redis, email: str) -> None:
    """作废刚签发的验证码，并解除冷却。

    发信失败时调用。冷却标记的意义是「已经给你发过一封了，别再刷」，可信没发出去
    的时候它就纯属误伤——用户会被一次临时故障锁在门外 60 秒，而且那 60 秒里
    他做什么都没用。既然没发成，就当这次请求没发生过。
    """
    await _clear(redis, email)
    await cache.delete(redis, _cooldown_key(email))


async def _clear(redis: Redis, email: str) -> None:
    """清掉验证码与计数。冷却标记保留，让它自己过期，避免被用来刷发信。"""
    await cache.delete(redis, _code_key(email))
    await cache.delete(redis, _attempts_key(email))
