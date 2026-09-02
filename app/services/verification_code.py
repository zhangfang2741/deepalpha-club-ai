"""验证码的签发与校验：邮箱和手机号、注册和找回密码，四种组合共用一套。

各场景对验证码的要求完全一样（一次性、限时、防爆破、防轰炸），只有用途和
送达渠道不同，所以用 Purpose 区分命名空间而不是复制多份实现。命名空间隔离
也顺带堵掉一类漏洞：拿注册时收到的验证码去重置别人的密码。

key 前缀由 CodeStore 持有而不是写死，因为同一套逻辑要服务多个 App（WordLens
用 vocab:vercode，缠论用 chan:vercode）。前缀隔离保证同一个手机号在两个 App
里的验证码物理上不可能撞上。

identifier 是邮箱或 E.164 手机号。模块本身不关心它是什么，只把它当成一个
不透明的字符串来哈希、比对——发信/发短信由调用方按渠道自己选。

验证码存 Redis 而不是数据库：天然带 TTL、过期自动清理。注册场景下更是关键——
用户还没建号，本来就没有地方存这个中间状态。

安全上的几点考虑：
- 存哈希不存明文。Redis 快照、慢查询日志、运维误看都可能泄露 value，
  而验证码在有效期内等同于账号的临时钥匙。
- key 里用标识符的哈希而不是本身，避免 `KEYS *:vercode:*` 直接扫出一份
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


class DailySendLimitError(Exception):
    """单个号码当日发送次数已达上限（成本闸）。"""


class GlobalSendLimitError(Exception):
    """全站当日短信总量已达预算上限（熔断，服务端侧问题）。"""


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


class CodeStore:
    """一个 App 的验证码存储。prefix 决定 Redis 命名空间。"""

    def __init__(self, prefix: str) -> None:
        """构造一个绑定了 key 前缀的存储。前缀用来隔离不同 App 的验证码。"""
        self._prefix = prefix

    # 挂到实例上，方便测试和转发层直接引用，语义与模块级函数完全一致。
    _hash_code = staticmethod(_hash_code)
    _slug = staticmethod(_slug)

    def _code_key(self, purpose: Purpose, identifier: str) -> str:
        return f"{self._prefix}:{purpose.value}:code:{_slug(identifier)}"

    def _attempts_key(self, purpose: Purpose, identifier: str) -> str:
        return f"{self._prefix}:{purpose.value}:attempts:{_slug(identifier)}"

    def _cooldown_key(self, purpose: Purpose, identifier: str) -> str:
        return f"{self._prefix}:{purpose.value}:cooldown:{_slug(identifier)}"

    async def issue_code(self, redis: Redis, purpose: Purpose, identifier: str) -> str:
        """签发一个新验证码并写入 Redis，返回明文供发信使用。

        Raises:
            ResendTooSoonError: 距上次发送不足冷却时间。
        """
        if await cache.exists(redis, self._cooldown_key(purpose, identifier)):
            raise ResendTooSoonError

        code = generate_code()
        ttl = settings.EMAIL_CODE_TTL

        # 重新签发时把旧的错误计数一并覆盖，否则上一轮攒下的次数会误伤这一轮。
        await cache.set(redis, self._code_key(purpose, identifier), _hash_code(code), expire=ttl)
        await cache.set(redis, self._attempts_key(purpose, identifier), 0, expire=ttl)
        await cache.set(
            redis,
            self._cooldown_key(purpose, identifier),
            1,
            expire=settings.EMAIL_CODE_RESEND_COOLDOWN,
        )
        return code

    async def verify_code(
        self, redis: Redis, purpose: Purpose, identifier: str, code: str
    ) -> bool:
        """校验验证码。正确则消费掉并返回 True；错误返回 False。

        Raises:
            TooManyAttemptsError: 错误次数达到上限，验证码已作废。
        """
        stored = await cache.get(redis, self._code_key(purpose, identifier))
        if stored is None:
            return False

        # compare_digest 而不是 ==：避免按字符短路比较泄露前缀匹配长度。
        if hmac.compare_digest(stored, _hash_code(code)):
            await self._clear(redis, purpose, identifier)
            return True

        attempts = await redis.incr(self._attempts_key(purpose, identifier))
        if attempts >= settings.EMAIL_CODE_MAX_ATTEMPTS:
            await self._clear(redis, purpose, identifier)
            raise TooManyAttemptsError
        return False

    async def discard_code(self, redis: Redis, purpose: Purpose, identifier: str) -> None:
        """作废刚签发的验证码，并解除冷却。

        发信失败时调用。冷却标记的意义是「已经给你发过一封了，别再刷」，可信没发出去
        的时候它就纯属误伤——用户会被一次临时故障锁在门外 60 秒，而且那 60 秒里
        他做什么都没用。既然没发成，就当这次请求没发生过。
        """
        await self._clear(redis, purpose, identifier)
        await cache.delete(redis, self._cooldown_key(purpose, identifier))

    async def _clear(self, redis: Redis, purpose: Purpose, identifier: str) -> None:
        """清掉验证码与计数。冷却标记保留，让它自己过期，避免被用来刷发信。"""
        await cache.delete(redis, self._code_key(purpose, identifier))
        await cache.delete(redis, self._attempts_key(purpose, identifier))

    # -----------------------------------------------------------------------
    # 「码由外部服务保管」模式下的辅助方法
    #
    # 阿里云号码认证服务自己生成、保管和核验短信验证码，我们拿不到明文，
    # 上面那套 issue_code / verify_code 用不上。但有两件事仍然必须自己做：
    #   1. 冷却：省掉一次注定被拒的 API 调用（按次计费），并给出清楚的中文提示；
    #   2. 错误次数：阿里云不暴露「错几次就作废」，而 6 位数字只有 100 万种可能，
    #      有效期内不限次数猜是能撞开的，每次猜还只是一次廉价的 API 调用。
    # -----------------------------------------------------------------------

    async def is_cooling_down(self, redis: Redis, purpose: Purpose, identifier: str) -> bool:
        """距上次发送是否还在冷却期内。"""
        return await cache.exists(redis, self._cooldown_key(purpose, identifier))

    async def start_cooldown(self, redis: Redis, purpose: Purpose, identifier: str) -> None:
        """标记「刚发过一次」，并重置错误计数。

        重置计数是必要的：上一轮攒下的错误次数不该算到新验证码头上，否则用户
        重新获取验证码后可能一次都还没输就被判「错误次数过多」。
        """
        await cache.set(
            redis,
            self._cooldown_key(purpose, identifier),
            1,
            expire=settings.EMAIL_CODE_RESEND_COOLDOWN,
        )
        await cache.set(
            redis, self._attempts_key(purpose, identifier), 0, expire=settings.EMAIL_CODE_TTL
        )

    async def assert_attempts_left(
        self, redis: Redis, purpose: Purpose, identifier: str
    ) -> None:
        """错误次数已用尽时抛 TooManyAttemptsError。"""
        raw = await cache.get(redis, self._attempts_key(purpose, identifier))
        if raw is not None and int(raw) >= settings.EMAIL_CODE_MAX_ATTEMPTS:
            raise TooManyAttemptsError

    async def record_failed_attempt(
        self, redis: Redis, purpose: Purpose, identifier: str
    ) -> None:
        """记一次校验失败。"""
        key = self._attempts_key(purpose, identifier)
        await redis.incr(key)
        # incr 对不存在的 key 会新建且不带 TTL，补一个过期时间，避免留下永不过期的 key。
        await redis.expire(key, settings.EMAIL_CODE_TTL)

    async def clear_attempts(self, redis: Redis, purpose: Purpose, identifier: str) -> None:
        """校验通过后清掉计数。"""
        await cache.delete(redis, self._attempts_key(purpose, identifier))

    # -----------------------------------------------------------------------
    # 短信成本闸：按天限量。
    #
    # 60 秒冷却只挡「连点重发」；这两道闸挡的是把账单刷爆的两种方式——同一个号
    # 一天被发几十条，以及换 IP 轰炸大量不同号码（短信 pumping）。计数按天，
    # 跨注册/找回密码所有短信用途合并统计：对成本来说，是发给谁、为什么发都一样花钱。
    # -----------------------------------------------------------------------

    def _daily_send_key(self, identifier: str) -> str:
        # 不含 purpose：单号上限跨所有短信用途合并计。
        return f"{self._prefix}:sms_daily:{_slug(identifier)}"

    def _global_daily_key(self) -> str:
        # 按 UTC 自然日分桶，key 自带日期，天然随天滚动。
        from datetime import datetime, timezone

        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"{self._prefix}:sms_global:{day}"

    async def assert_sms_budget(self, redis: Redis, identifier: str) -> None:
        """发短信前检查单号当日上限与全站当日预算，超限抛异常。

        Raises:
            DailySendLimitError: 该号码当日发送已达上限。
            GlobalSendLimitError: 全站当日短信总量已达预算上限。
        """
        raw = await cache.get(redis, self._daily_send_key(identifier))
        if raw is not None and int(raw) >= settings.SMS_PER_PHONE_DAILY_LIMIT:
            raise DailySendLimitError

        raw_global = await cache.get(redis, self._global_daily_key())
        if raw_global is not None and int(raw_global) >= settings.SMS_GLOBAL_DAILY_LIMIT:
            raise GlobalSendLimitError

    async def record_sms_sent(self, redis: Redis, identifier: str) -> None:
        """发送成功后各计一条（单号计数 + 全站计数）。

        只在真正发出去后调用——和冷却一样，没发成就不该占用配额。检查在发送前、
        计数在发送后，并发下可能轻微超出上限，但对成本控制来说完全够用，不值得为此
        上 Lua 脚本。
        """
        # 单号计数：滚动 24 小时。
        phone_key = self._daily_send_key(identifier)
        await redis.incr(phone_key)
        await redis.expire(phone_key, 86400)

        # 全站计数：按自然日 key，留 48 小时 TTL 让隔日的桶自动清理。
        global_key = self._global_daily_key()
        await redis.incr(global_key)
        await redis.expire(global_key, 172800)
