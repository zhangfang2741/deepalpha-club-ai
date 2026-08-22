# 缠论手机号/邮箱双通道认证——后端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让缠论后端支持中国大陆手机号和邮箱两条通道的验证码注册、统一账号登录、以及双通道找回密码。

**Architecture:** 复用 WordLens 已建好的验证码基础设施。先把 `app/services/vocabulary/verification_code.py` 提升为带前缀参数的共享 `CodeStore`，原模块退化成薄转发层保证 WordLens 零回归；再给主 `User` 表加 `phone` 列并把 `email` 改可空；最后在 `app/api/v1/auth/routes.py` 新增九个端点，业务逻辑放在新建的 `app/services/account/` 下。

**Tech Stack:** Python 3.13 / uv、FastAPI、SQLModel + asyncpg、Alembic、redis-py asyncio、slowapi 限流、pytest（`asyncio_mode=auto`）。

**设计文档：** `docs/superpowers/specs/2026-08-22-chan-auth-phone-email-design.md`

**这份计划不含：** iOS 客户端、Web 前端。各有独立计划，都依赖本计划先完成。

---

## 文件结构

**新建**

| 文件 | 职责 |
|------|------|
| `app/services/verification_code.py` | 共享验证码：`CodeStore(prefix)` 类 + 与前缀无关的 `Purpose`/异常/`generate_code`/`_hash_code` |
| `app/services/account/__init__.py` | 空包声明 |
| `app/services/account/codes.py` | 缠论的 `CodeStore("chan:vercode")` 实例，按渠道分发发码与校验 |
| `app/services/account/accounts.py` | 账号标识判别（手机号 or 邮箱） |
| `tests/services/test_verification_code.py` | 共享模块测试，重点是前缀隔离 |
| `tests/services/account/__init__.py` | 空 |
| `tests/services/account/test_accounts.py` | 账号判别测试 |
| `tests/api/__init__.py`、`tests/api/test_chan_auth.py` | 新端点测试 |

**改造**

| 文件 | 改动 |
|------|------|
| `app/services/vocabulary/verification_code.py` | 整体替换为转发层 |
| `app/services/email.py` | `send_email` / `_send_sync` / `_render_code_email` / `render_*` 增加品牌参数 |
| `app/core/config.py` | 新增 `CHAN_BRAND_NAME` 与四条限流条目 |
| `app/models/user.py` | 加 `phone`，`email` 改可空 |
| `app/services/database.py` | `create_user` 支持 phone，新增 `get_user_by_phone` |
| `app/schemas/auth.py` | 响应 schema 的 email 改可空、加 phone；新增九个请求 schema |
| `app/api/v1/auth/routes.py` | 新增九个端点 |
| `.env.example` | 补 `CHAN_BRAND_NAME` |
| `alembic/versions/` | 自动生成一个迁移 |

---

### Task 1: 验证码模块提升为共享 CodeStore

这是纯重构，风险集中在「不能弄坏 WordLens」。现有的
`tests/services/vocabulary/test_verification_code.py` 是回归网，**必须一行不改地继续通过**。
它引用了 `ec._hash_code` 和 `ec.settings`，所以转发层要连这两个一起 re-export。

**Files:**
- Create: `app/services/verification_code.py`
- Create: `tests/services/test_verification_code.py`
- Rewrite: `app/services/vocabulary/verification_code.py`

- [ ] **Step 1: 先跑一遍现有测试，记下基线**

Run: `uv run pytest tests/services/vocabulary/test_verification_code.py -v`
Expected: 全部 PASS（14 个用例）。记下这个数字，重构后必须一致。

- [ ] **Step 2: 写共享模块的失败测试**

创建 `tests/services/test_verification_code.py`：

```python
"""共享验证码模块测试。

vocabulary 侧的行为已由 tests/services/vocabulary/test_verification_code.py 锁住，
这里只测提升为共享模块后新增的能力：前缀隔离。两个 App 用同一个手机号时，
各自的验证码必须落在不同的 Redis key 上——否则 A 应用发的码能用来注册 B 应用。
"""

from unittest.mock import AsyncMock

import pytest

from app.services.verification_code import (
    CodeStore,
    Purpose,
    ResendTooSoonError,
    TooManyAttemptsError,
    generate_code,
)

IDENTIFIER = "+8613800138000"


def _redis() -> AsyncMock:
    r = AsyncMock()
    r.get.return_value = None
    r.exists.return_value = 0
    r.incr.return_value = 1
    return r


async def test_different_prefixes_produce_disjoint_keys():
    """同一手机号、同一用途，两个 store 的 key 不能有任何重叠。"""
    chan = CodeStore("chan:vercode")
    vocab = CodeStore("vocab:vercode")

    r1 = _redis()
    await chan.issue_code(r1, Purpose.PHONE_REGISTER, IDENTIFIER)
    chan_keys = {c.args[0] for c in r1.set.await_args_list}

    r2 = _redis()
    await vocab.issue_code(r2, Purpose.PHONE_REGISTER, IDENTIFIER)
    vocab_keys = {c.args[0] for c in r2.set.await_args_list}

    assert not (chan_keys & vocab_keys)
    assert all(k.startswith("chan:vercode:") for k in chan_keys)
    assert all(k.startswith("vocab:vercode:") for k in vocab_keys)


async def test_code_from_other_app_does_not_verify():
    """WordLens 签发的码拿到缠论来验，必须失败。"""
    chan = CodeStore("chan:vercode")
    redis = _redis()
    redis.get.return_value = None  # chan 命名空间下没有码

    assert await chan.verify_code(redis, Purpose.PHONE_REGISTER, IDENTIFIER, "123456") is False


async def test_keys_never_contain_plaintext_identifier():
    chan = CodeStore("chan:vercode")
    redis = _redis()
    await chan.issue_code(redis, Purpose.REGISTER, IDENTIFIER)

    for call in redis.set.await_args_list:
        assert IDENTIFIER not in call.args[0]


async def test_every_key_has_ttl():
    chan = CodeStore("chan:vercode")
    redis = _redis()
    await chan.issue_code(redis, Purpose.REGISTER, IDENTIFIER)

    for call in redis.set.await_args_list:
        assert call.kwargs.get("ex"), f"key {call.args[0]} 没设过期时间"


async def test_cooldown_blocks_reissue():
    chan = CodeStore("chan:vercode")
    redis = _redis()
    redis.exists.return_value = 1

    with pytest.raises(ResendTooSoonError):
        await chan.issue_code(redis, Purpose.REGISTER, IDENTIFIER)


async def test_max_attempts_invalidates_code():
    from app.core.config import settings

    chan = CodeStore("chan:vercode")
    redis = _redis()
    redis.get.return_value = chan._hash_code("123456")
    redis.incr.return_value = settings.EMAIL_CODE_MAX_ATTEMPTS

    with pytest.raises(TooManyAttemptsError):
        await chan.verify_code(redis, Purpose.REGISTER, IDENTIFIER, "000000")


def test_generate_code_is_six_digits():
    for _ in range(50):
        code = generate_code()
        assert len(code) == 6 and code.isdigit()
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/services/test_verification_code.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.verification_code'`

- [ ] **Step 4: 创建共享模块**

创建 `app/services/verification_code.py`。内容是把现有
`app/services/vocabulary/verification_code.py` 的实现搬过来，唯一的结构变化是把写死的
`_PREFIX` 换成 `CodeStore` 的实例属性。**原文件的模块 docstring 和所有函数注释原样保留**——
那些注释解释的是安全权衡（为什么存哈希、为什么 key 用哈希、为什么次数用尽立即作废），
搬家过程中丢掉就等于把设计理由丢了。

```python
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
```

- [ ] **Step 5: 跑共享模块测试**

Run: `uv run pytest tests/services/test_verification_code.py -v`
Expected: 7 个用例全 PASS

- [ ] **Step 6: 把 vocabulary 模块改成转发层**

整体替换 `app/services/vocabulary/verification_code.py` 为：

```python
"""WordLens 的验证码存储。

实现已提升到 app.services.verification_code 供多个 App 共用，这里只保留一个
绑定了 vocab:vercode 前缀的实例，以及与提升前完全一致的模块级函数签名——
调用方（vocabulary/auth.py）和既有测试都不需要改动，线上 Redis 里在途的
验证码 key 也不会变。
"""
from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings as settings  # noqa: F401  测试引用 ec.settings
from app.services.verification_code import (
    CodeStore,
    Purpose as Purpose,
    ResendTooSoonError as ResendTooSoonError,
    TooManyAttemptsError as TooManyAttemptsError,
    _hash_code as _hash_code,
    _slug as _slug,
    generate_code as generate_code,
)

_store = CodeStore("vocab:vercode")


async def issue_code(redis: Redis, purpose: Purpose, identifier: str) -> str:
    return await _store.issue_code(redis, purpose, identifier)


async def verify_code(redis: Redis, purpose: Purpose, identifier: str, code: str) -> bool:
    return await _store.verify_code(redis, purpose, identifier, code)


async def discard_code(redis: Redis, purpose: Purpose, identifier: str) -> None:
    await _store.discard_code(redis, purpose, identifier)


async def is_cooling_down(redis: Redis, purpose: Purpose, identifier: str) -> bool:
    return await _store.is_cooling_down(redis, purpose, identifier)


async def start_cooldown(redis: Redis, purpose: Purpose, identifier: str) -> None:
    await _store.start_cooldown(redis, purpose, identifier)


async def assert_attempts_left(redis: Redis, purpose: Purpose, identifier: str) -> None:
    await _store.assert_attempts_left(redis, purpose, identifier)


async def record_failed_attempt(redis: Redis, purpose: Purpose, identifier: str) -> None:
    await _store.record_failed_attempt(redis, purpose, identifier)


async def clear_attempts(redis: Redis, purpose: Purpose, identifier: str) -> None:
    await _store.clear_attempts(redis, purpose, identifier)
```

`as X` 的重导出写法是给 ruff 看的：显式说明这是有意的 re-export，不是没用到的 import。

- [ ] **Step 7: 跑 WordLens 回归网**

Run: `uv run pytest tests/services/vocabulary/ -v`
Expected: 全部 PASS，且 `test_verification_code.py` 的通过数与 Step 1 记下的基线一致。
特别确认 `test_keys_are_namespaced_and_do_not_leak_email` 通过——它断言 key 以
`vocab:vercode:` 开头，是前缀没被改坏的直接证据。

- [ ] **Step 8: 跑整套测试确认无连带破坏**

Run: `uv run pytest -m "not slow" -q`
Expected: 无新增失败（若有既存失败，与重构前对比确认是同一批）

- [ ] **Step 9: 格式与类型检查**

Run: `make check`
Expected: ruff 和 pyright 均无新增报错

- [ ] **Step 10: 提交**

```bash
git add app/services/verification_code.py app/services/vocabulary/verification_code.py tests/services/test_verification_code.py
git commit -m "refactor(auth): 验证码模块提升为共享 CodeStore

前缀由构造参数决定，WordLens 侧退化为转发层，key 前缀与调用方签名均不变。"
```

---

### Task 2: 邮件品牌参数化

`SMTP_FROM_NAME` 默认值是「鹦鹉背单词」，缠论用户会收到署名错误的邮件。

**Files:**
- Modify: `app/services/email.py`
- Modify: `app/core/config.py`
- Modify: `.env.example`
- Create: `tests/services/test_email_brand.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/services/test_email_brand.py`：

```python
"""邮件品牌落款测试。

两个 App 共用一套 SMTP 发信，但署名必须各是各的——缠论用户收到署名
「鹦鹉背单词」的验证码邮件会直接当成钓鱼邮件。
"""

from app.core.config import settings
from app.services import email as email_service


def test_render_register_uses_given_brand():
    subject, html, text = email_service.render_register("123456", 10, brand="DeepAlpha 缠论")

    assert "DeepAlpha 缠论" in subject
    assert "DeepAlpha 缠论" in html
    assert "DeepAlpha 缠论" in text


def test_render_password_reset_uses_given_brand():
    subject, html, text = email_service.render_password_reset(
        "123456", 10, brand="DeepAlpha 缠论"
    )

    assert "DeepAlpha 缠论" in subject
    assert "DeepAlpha 缠论" in html


def test_render_defaults_to_smtp_from_name():
    """不传 brand 时行为与改造前一致，WordLens 不受影响。"""
    subject, _, _ = email_service.render_register("123456", 10)

    assert settings.SMTP_FROM_NAME in subject


def test_chan_brand_name_has_sensible_default():
    assert settings.CHAN_BRAND_NAME == "DeepAlpha 缠论"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/services/test_email_brand.py -v`
Expected: FAIL，`render_register() got an unexpected keyword argument 'brand'`

- [ ] **Step 3: 给 config 加 CHAN_BRAND_NAME**

在 `app/core/config.py` 中 `SMTP_TIMEOUT_SECONDS` 那一行之后加：

```python
        # 缠论 App 的邮件署名。与 WordLens 共用一套 SMTP 发信，但落款必须各是各的，
        # 否则缠论用户会收到署名「鹦鹉背单词」的验证码邮件。
        # 短信侧不需要这样拆：阿里云号码认证用的是赠送签名，落款本来就不是 App 名。
        self.CHAN_BRAND_NAME = os.getenv("CHAN_BRAND_NAME", "DeepAlpha 缠论")
```

- [ ] **Step 4: 改 email.py 的四个函数**

`_render_code_email` 增加 `brand` 参数（原本是函数内部读 settings）：

```python
def _render_code_email(
    code: str, ttl_minutes: int, heading: str, lead: str, footer_note: str, brand: str
) -> tuple[str, str, str]:
```

并把函数体里的 `brand = settings.SMTP_FROM_NAME` 那一行删掉（brand 现在由参数传入）。
其余函数体不动。

`render_password_reset` 和 `render_register` 各增加 `brand: str | None = None`：

```python
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
```

`send_email` 和 `_send_sync` 增加 `from_name`，让邮件头里的发件人名也跟着变——
只改正文署名而 From 仍显示「鹦鹉背单词」，用户在收件箱列表里看到的还是错的：

```python
def _send_sync(to: str, subject: str, html: str, text: str, from_name: str) -> None:
```

并把 `_send_sync` 里的这一行：

```python
    msg["From"] = formataddr((str(Header(settings.SMTP_FROM_NAME, "utf-8")), settings.SMTP_USER))
```

改为：

```python
    msg["From"] = formataddr((str(Header(from_name, "utf-8")), settings.SMTP_USER))
```

```python
async def send_email(
    to: str, subject: str, html: str, text: str, from_name: str | None = None
) -> None:
```

并把 `send_email` 里的这一行：

```python
        await asyncio.to_thread(_send_sync, to, subject, html, text)
```

改为：

```python
        await asyncio.to_thread(_send_sync, to, subject, html, text, from_name or settings.SMTP_FROM_NAME)
```

- [ ] **Step 5: 跑测试**

Run: `uv run pytest tests/services/test_email_brand.py -v`
Expected: 4 个用例全 PASS

- [ ] **Step 6: 确认 WordLens 侧没被改坏**

Run: `uv run pytest tests/services/vocabulary/ -q`
Expected: 全部 PASS

- [ ] **Step 7: 补 .env.example**

在 `.env.example` 的 `SMTP_TIMEOUT_SECONDS=15` 之后加一行：

```
CHAN_BRAND_NAME=DeepAlpha 缠论           # 缠论 App 的邮件署名，与 WordLens 区分
```

- [ ] **Step 8: 提交**

```bash
git add app/services/email.py app/core/config.py .env.example tests/services/test_email_brand.py
git commit -m "feat(auth): 邮件品牌落款参数化，缠论与 WordLens 分开署名"
```

---

### Task 3: User 模型加 phone、email 改可空

**Files:**
- Modify: `app/models/user.py`
- Modify: `app/services/database.py`
- Modify: `app/schemas/auth.py`
- Create: `alembic/versions/<自动生成>.py`
- Create: `tests/services/account/__init__.py`

- [ ] **Step 1: 改模型**

`app/models/user.py` 里把 email 那一行改掉并加 phone：

```python
    id: int = Field(default=None, primary_key=True)
    # email 与 phone 都可空，但应用层保证至少有一个：手机号注册的用户没有邮箱，
    # 反之亦然。Postgres 的 unique 约束允许多行 NULL，两列同时可空唯一是安全的。
    email: Optional[str] = Field(default=None, unique=True, index=True)
    phone: Optional[str] = Field(default=None, unique=True, index=True, max_length=20)
    hashed_password: str
```

同时更新类 docstring 的 Attributes 段，补上 phone、并把 email 描述为「可空唯一」。

- [ ] **Step 2: 生成迁移**

Run: `uv run alembic revision --autogenerate -m "user 表增加 phone 列，email 改可空"`
Expected: 在 `alembic/versions/` 下生成一个新文件

- [ ] **Step 3: 检查生成的迁移内容**

打开新生成的文件，确认 `upgrade()` 里有且只有这三样：
- `op.add_column('users', sa.Column('phone', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True))`
- `op.create_index(op.f('ix_users_phone'), 'users', ['phone'], unique=True)`
- `op.alter_column('users', 'email', existing_type=..., nullable=True)`

如果 autogenerate 顺带产出了与本次无关的表变更（其它模型的漂移），把那些行删掉——
本次迁移只应包含 users 表的这三处。

- [ ] **Step 4: 应用迁移**

Run: `make migrate`
Expected: `Running upgrade ... -> <新版本号>`，无报错

- [ ] **Step 5: 给 DatabaseService 加 phone 支持**

`app/services/database.py` 的 `create_user` 改签名（email 变可空、末尾追加 phone，
现有位置参数调用方不受影响）：

```python
    def create_user(
        self,
        email: str | None,
        password: str,
        username: str | None = None,
        phone: str | None = None,
    ) -> User:
        """Create a new user.

        Args:
            email: User's email address（手机号注册时为 None）
            password: Hashed password
            username: Optional display name
            phone: E.164 格式手机号（邮箱注册时为 None）

        Returns:
            User: The created user
        """
        with Session(self.engine) as session:
            user = User(
                email=email, hashed_password=password, username=username, phone=phone
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            # 邮箱和手机号都属于个人信息，日志里只记 id，不记标识符本身。
            logger.info("user_created", user_id=user.id)
            return user
```

在 `get_user_by_email` 之后加：

```python
    def get_user_by_phone(self, phone: str) -> Optional[User]:
        """Get a user by phone (E.164).

        Args:
            phone: E.164 格式手机号

        Returns:
            Optional[User]: The user if found, None otherwise
        """
        with Session(self.engine) as session:
            statement = select(User).where(User.phone == phone)
            user = session.exec(statement).first()
            return user
```

- [ ] **Step 6: 改响应 schema**

`app/schemas/auth.py` 里 `UserProfileResponse` 和 `UserResponse` 的 email 改可空并加 phone：

```python
class UserProfileResponse(BaseResponse):
    id: int = Field(..., description="User's ID")
    email: str | None = Field(default=None, description="User's email address")
    phone: str | None = Field(default=None, description="User's phone in E.164")
    username: str | None = Field(default=None, description="User's display name")
    created_at: datetime = Field(..., description="Account creation timestamp")
```

`UserResponse` 同样把 `email: str` 改为 `email: str | None = Field(default=None, ...)`
并加一行 `phone: str | None = Field(default=None, description="User's phone in E.164")`。

- [ ] **Step 7: 让现有端点填上 phone**

`app/api/v1/auth/routes.py` 里 `get_current_user_profile` 和 `update_user_profile`
构造 `UserProfileResponse` 的地方，各补一个 `phone=user.phone` 参数；
`register_user` 构造 `UserResponse` 的地方补 `phone=user.phone`。

- [ ] **Step 8: 建测试包目录**

```bash
mkdir -p tests/services/account && touch tests/services/account/__init__.py
```

- [ ] **Step 9: 跑测试与检查**

Run: `uv run pytest -m "not slow" -q && make check`
Expected: 无新增失败，pyright 无新增报错

- [ ] **Step 10: 提交**

```bash
git add app/models/user.py app/services/database.py app/schemas/auth.py app/api/v1/auth/routes.py alembic/versions/ tests/services/account/__init__.py
git commit -m "feat(auth): User 表增加 phone 列，email 改为可空"
```

---

### Task 4: 账号判别服务

**Files:**
- Create: `app/services/account/__init__.py`
- Create: `app/services/account/accounts.py`
- Create: `tests/services/account/test_accounts.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/services/account/test_accounts.py`：

```python
"""统一登录的账号判别测试。

登录框只有一个，用户可能输手机号也可能输邮箱，服务端得自己认出来。
判别错了的后果是查错表，用户会看到「账号或密码错误」而不知道为什么。
"""

import pytest

from app.services.account.accounts import AccountKind, resolve_account


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("13800138000", "+8613800138000"),
        ("+8613800138000", "+8613800138000"),
        ("138 0013 8000", "+8613800138000"),
        ("138-0013-8000", "+8613800138000"),
        ("８６１３８００１３８０００", "+8613800138000"),  # 全角输入
    ],
)
def test_recognizes_phone_and_normalizes(raw, expected):
    kind, value = resolve_account(raw)
    assert kind is AccountKind.PHONE
    assert value == expected


@pytest.mark.parametrize(
    "raw",
    ["someone@example.com", "Someone@Example.COM", "  someone@example.com  "],
)
def test_recognizes_email_and_normalizes(raw):
    kind, value = resolve_account(raw)
    assert kind is AccountKind.EMAIL
    assert value == "someone@example.com"


@pytest.mark.parametrize("raw", ["", "   ", "12345", "not-an-account", "12345678901234567890"])
def test_rejects_garbage(raw):
    with pytest.raises(ValueError):
        resolve_account(raw)


def test_digits_that_are_not_valid_cn_mobile_are_rejected():
    """11 位但号段非法（1 后面不是 3-9），不该被当成手机号也不该当成邮箱。"""
    with pytest.raises(ValueError):
        resolve_account("12800138000")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/services/account/test_accounts.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.services.account'`

- [ ] **Step 3: 建包**

```bash
mkdir -p app/services/account && touch app/services/account/__init__.py
```

- [ ] **Step 4: 实现 accounts.py**

创建 `app/services/account/accounts.py`：

```python
"""统一登录的账号标识判别。

登录框只有一个输入框，用户输手机号还是邮箱由服务端认。判别顺序是「先试手机号，
不成再当邮箱」而不是反过来：手机号的格式约束严格得多（中国大陆 11 位、号段固定），
误判概率极低；邮箱格式则宽松，`13800138000` 之类的输入不该先被邮箱校验拦下。
"""
from __future__ import annotations

from enum import Enum

from app.utils.phone import InvalidPhoneError, normalize_phone
from app.utils.sanitization import sanitize_email


class AccountKind(str, Enum):
    """账号标识的类型。"""

    PHONE = "phone"
    EMAIL = "email"


def resolve_account(raw: str) -> tuple[AccountKind, str]:
    """判别账号是手机号还是邮箱，并归一化。

    Returns:
        (类型, 归一化后的值)。手机号是 E.164，邮箱是小写去空白。

    Raises:
        ValueError: 两种格式都不满足。
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("请输入手机号或邮箱")

    try:
        return AccountKind.PHONE, normalize_phone(text)
    except InvalidPhoneError:
        pass

    # 纯数字走到这里说明它不是合法手机号，当邮箱处理只会给出更让人困惑的报错。
    if text.replace("+", "").isdigit():
        raise ValueError("手机号格式不正确")

    try:
        return AccountKind.EMAIL, sanitize_email(text)
    except ValueError as exc:
        raise ValueError("请输入正确的手机号或邮箱") from exc
```

- [ ] **Step 5: 跑测试**

Run: `uv run pytest tests/services/account/test_accounts.py -v`
Expected: 全部 PASS

（`sanitize_email` 已经会 `.lower()` 并 strip，见 `app/utils/sanitization.py:53`，
所以大小写和首尾空白的用例不需要在 `resolve_account` 里额外处理。）

- [ ] **Step 6: 提交**

```bash
git add app/services/account/ tests/services/account/test_accounts.py
git commit -m "feat(auth): 新增账号标识判别服务，区分手机号与邮箱"
```

---

### Task 5: 缠论验证码发送服务

**Files:**
- Create: `app/services/account/codes.py`
- Create: `tests/services/account/test_codes.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/services/account/test_codes.py`：

```python
"""缠论验证码收发测试。

重点锁两件事：
1. 缠论的验证码落在 chan: 前缀下，与 WordLens 物理隔离
2. 发送失败时冷却必须回滚——否则一次配置故障会把用户锁在门外 60 秒
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services import email as email_service
from app.services.account import codes
from app.services.verification_code import Purpose

EMAIL = "someone@example.com"
PHONE = "+8613800138000"


def _redis() -> AsyncMock:
    r = AsyncMock()
    r.get.return_value = None
    r.exists.return_value = 0
    r.incr.return_value = 1
    return r


async def test_email_code_uses_chan_prefix():
    redis = _redis()
    with patch.object(email_service, "send_email", AsyncMock()):
        await codes.send_email_code(redis, Purpose.REGISTER, EMAIL, email_service.render_register)

    keys = {c.args[0] for c in redis.set.await_args_list}
    assert keys and all(k.startswith("chan:vercode:") for k in keys)


async def test_email_code_is_sent_with_chan_brand():
    redis = _redis()
    send = AsyncMock()
    with patch.object(email_service, "send_email", send):
        await codes.send_email_code(redis, Purpose.REGISTER, EMAIL, email_service.render_register)

    assert send.await_count == 1
    subject = send.await_args.args[1]
    assert "DeepAlpha 缠论" in subject


async def test_cooldown_rolled_back_when_send_fails():
    """回归用例：邮件没发出去就不能留着冷却锁。"""
    redis = _redis()
    with patch.object(email_service, "send_email", AsyncMock(side_effect=email_service.EmailSendError)):
        with pytest.raises(codes.CodeDeliveryError):
            await codes.send_email_code(
                redis, Purpose.REGISTER, EMAIL, email_service.render_register
            )

    deleted = {c.args[0] for c in redis.delete.await_args_list}
    assert any("cooldown" in k for k in deleted), "发信失败后没有解除冷却"


async def test_email_not_configured_raises_unavailable():
    redis = _redis()
    with patch.object(
        email_service, "send_email", AsyncMock(side_effect=email_service.EmailNotConfiguredError)
    ):
        with pytest.raises(codes.CodeChannelUnavailableError):
            await codes.send_email_code(
                redis, Purpose.REGISTER, EMAIL, email_service.render_register
            )
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/services/account/test_codes.py -v`
Expected: FAIL，`cannot import name 'codes'`

- [ ] **Step 3: 实现 codes.py**

创建 `app/services/account/codes.py`：

```python
"""缠论 App 的验证码收发。

按渠道分工：邮箱的码由本地 CodeStore 生成保管（存哈希），经 SMTP 送达；
手机的码由阿里云号码认证服务生成保管核验，本地只留冷却和错误计数。
这个不对称是外部服务的形态决定的，不是设计选择——阿里云不把明文交给我们。

抛的是本模块自己的异常而不是 HTTPException：服务层不该知道 HTTP 状态码，
路由层负责翻译。
"""
from __future__ import annotations

from collections.abc import Callable

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import logger
from app.services import email as email_service
from app.services import sms as sms_service
from app.services.verification_code import (
    CodeStore,
    Purpose,
    ResendTooSoonError,
    TooManyAttemptsError,
)
from app.utils.phone import to_aliyun_format

# 与 WordLens 的 vocab:vercode 物理隔离：同一个手机号在两个 App 里各有各的码。
store = CodeStore("chan:vercode")


class CodeDeliveryError(Exception):
    """验证码没能送达（发送失败）。"""


class CodeChannelUnavailableError(Exception):
    """渠道未配置，服务端问题。"""


class CodeRejectedError(Exception):
    """验证码错误或已过期。"""


# 用途 → 阿里云系统模板。注册用「登录/注册」模板，重置密码用「重置密码」模板。
_SMS_TEMPLATES = {
    Purpose.PHONE_REGISTER: lambda: settings.ALIYUN_SMS_TEMPLATE_REGISTER,
    Purpose.PHONE_PASSWORD_RESET: lambda: settings.ALIYUN_SMS_TEMPLATE_PASSWORD_RESET,
}


async def send_email_code(
    redis: Redis,
    purpose: Purpose,
    email: str,
    render: Callable[[str, int, str], tuple[str, str, str]],
) -> None:
    """签发验证码并发邮件。

    Raises:
        ResendTooSoonError: 还在冷却期。
        CodeChannelUnavailableError: SMTP 未配置。
        CodeDeliveryError: 发信失败。
    """
    code = await store.issue_code(redis, purpose, email)

    subject, html, text = render(code, settings.EMAIL_CODE_TTL // 60, settings.CHAN_BRAND_NAME)
    try:
        await email_service.send_email(
            email, subject, html, text, from_name=settings.CHAN_BRAND_NAME
        )
    except email_service.EmailNotConfiguredError:
        # 没发出去就不能留着冷却锁，否则用户被一次配置问题锁在门外 60 秒。
        await store.discard_code(redis, purpose, email)
        logger.error("chan_email_code_not_configured", purpose=purpose.value)
        raise CodeChannelUnavailableError from None
    except email_service.EmailSendError:
        await store.discard_code(redis, purpose, email)
        raise CodeDeliveryError from None


async def verify_email_code(redis: Redis, purpose: Purpose, email: str, code: str) -> None:
    """校验邮箱验证码。

    Raises:
        TooManyAttemptsError: 错误次数用尽。
        CodeRejectedError: 验证码错误或已过期。
    """
    if not await store.verify_code(redis, purpose, email, code):
        raise CodeRejectedError


async def send_sms_code(redis: Redis, purpose: Purpose, phone: str) -> None:
    """让阿里云发一条验证码短信。

    Raises:
        ResendTooSoonError: 还在冷却期。
        CodeChannelUnavailableError: 短信未配置。
        CodeDeliveryError: 发送失败。
    """
    if await store.is_cooling_down(redis, purpose, phone):
        raise ResendTooSoonError

    try:
        await sms_service.send_verification_code(
            to_aliyun_format(phone), _SMS_TEMPLATES[purpose]()
        )
    except sms_service.SMSNotConfiguredError:
        logger.error("chan_sms_not_configured", purpose=purpose.value)
        raise CodeChannelUnavailableError from None
    except sms_service.SMSResendTooSoonError:
        raise ResendTooSoonError from None
    except sms_service.SMSSendError:
        raise CodeDeliveryError from None

    # 发成功才上冷却，发失败还锁着用户会把临时故障变成 60 秒干等。
    await store.start_cooldown(redis, purpose, phone)


async def verify_sms_code(redis: Redis, purpose: Purpose, phone: str, code: str) -> None:
    """核验短信验证码。

    Raises:
        TooManyAttemptsError: 错误次数用尽。
        CodeChannelUnavailableError: 短信未配置。
        CodeDeliveryError: 校验调用失败。
        CodeRejectedError: 验证码错误或已过期。
    """
    # 阿里云不暴露「错几次就作废」，本地补一个计数器：6 位数字只有 100 万种可能。
    await store.assert_attempts_left(redis, purpose, phone)

    try:
        passed = await sms_service.check_verification_code(to_aliyun_format(phone), code)
    except sms_service.SMSNotConfiguredError:
        raise CodeChannelUnavailableError from None
    except sms_service.SMSCodeInvalidError:
        # 码不存在/已过期，与「码不对」走同一路径：对用户来说没有区别。
        passed = False
    except sms_service.SMSSendError:
        raise CodeDeliveryError from None

    if not passed:
        await store.record_failed_attempt(redis, purpose, phone)
        raise CodeRejectedError

    await store.clear_attempts(redis, purpose, phone)


__all__ = [
    "CodeChannelUnavailableError",
    "CodeDeliveryError",
    "CodeRejectedError",
    "Purpose",
    "ResendTooSoonError",
    "TooManyAttemptsError",
    "send_email_code",
    "send_sms_code",
    "store",
    "verify_email_code",
    "verify_sms_code",
]
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/services/account/test_codes.py -v`
Expected: 4 个用例全 PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/account/codes.py tests/services/account/test_codes.py
git commit -m "feat(auth): 缠论验证码收发服务，邮箱走 SMTP 手机走阿里云"
```

---

### Task 6: 请求 schema 与限流配置

**Files:**
- Modify: `app/schemas/auth.py`
- Modify: `app/core/config.py`

- [ ] **Step 1: 加请求 schema**

在 `app/schemas/auth.py` 末尾追加（`SecretStr` 和 `EmailStr` 已在文件顶部导入，
若 pyright 报未导入则补进现有的 pydantic import 行）：

```python
# ---------------------------------------------------------------------------
# 双通道注册/登录/找回密码
#
# 密码下限跟随主站既有的 validate_password_strength（8–64 位，含大小写、数字、
# 特殊字符），比 WordLens 那套 6 位下限严格，不要照抄 vocabulary 的 min_length。
# ---------------------------------------------------------------------------


class EmailCodeRequest(BaseModel):
    """请求给邮箱发验证码（注册或找回密码）。"""

    email: EmailStr


class EmailRegisterRequest(BaseModel):
    """邮箱 + 验证码注册。"""

    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    password: SecretStr = Field(..., min_length=8, max_length=64)
    username: str | None = Field(default=None, max_length=50)


class EmailPasswordResetConfirm(BaseModel):
    """凭邮箱验证码设置新密码。"""

    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: SecretStr = Field(..., min_length=8, max_length=64)


class PhoneCodeRequest(BaseModel):
    """请求给手机号发验证码。号码在服务端归一化，前端不必自己处理格式。"""

    phone: str = Field(..., min_length=6, max_length=24)


class PhoneRegisterRequest(BaseModel):
    """手机号 + 验证码注册。"""

    phone: str = Field(..., min_length=6, max_length=24)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    password: SecretStr = Field(..., min_length=8, max_length=64)
    username: str | None = Field(default=None, max_length=50)


class PhonePasswordResetConfirm(BaseModel):
    """凭手机验证码设置新密码。"""

    phone: str = Field(..., min_length=6, max_length=24)
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: SecretStr = Field(..., min_length=8, max_length=64)


class AccountLoginRequest(BaseModel):
    """统一登录：account 可以是手机号或邮箱，由服务端判别。"""

    account: str = Field(..., min_length=3, max_length=255)
    password: SecretStr
```

- [ ] **Step 2: 加限流条目**

设计文档里列的是四条（注册发码、手机发码、找回密码发码、找回密码校验），这里合并成三条：
注册和找回密码的邮箱发码额度相同、共用一条即可，两个通道的校验也共用一条。以本计划为准。

在 `app/core/config.py` 的 `default_endpoints` 字典里，
`"vocabulary_password_reset_confirm": ["20 per hour"],` 之后加：

```python
            # 缠论：发码要花钱且会打扰用户，按 IP 卡死，额度与 WordLens 同类端点对齐
            "chan_email_request_code": ["5 per hour"],
            "chan_phone_request_code": ["5 per hour"],
            # 校验侧防的是换着账号大批量撞码；单账号的错误次数由 Redis 计数管
            "chan_code_verify": ["20 per hour"],
```

- [ ] **Step 3: 确认配置生效**

Run: `uv run python -c "from app.core.config import settings; print(settings.RATE_LIMIT_ENDPOINTS['chan_email_request_code'], settings.CHAN_BRAND_NAME)"`
Expected: `['5 per hour'] DeepAlpha 缠论`

- [ ] **Step 4: 提交**

```bash
git add app/schemas/auth.py app/core/config.py
git commit -m "feat(auth): 双通道认证的请求 schema 与限流配置"
```

---

### Task 7: 邮箱通道路由

**Files:**
- Modify: `app/api/v1/auth/routes.py`
- Create: `tests/api/__init__.py`
- Create: `tests/api/test_chan_auth.py`

- [ ] **Step 1: 建测试包并写失败测试**

```bash
mkdir -p tests/api && touch tests/api/__init__.py
```

创建 `tests/api/test_chan_auth.py`：

```python
"""缠论双通道认证端点测试。

SMTP 和阿里云都 mock 掉：本地没有凭据，而且测试不该真的发信发短信。
数据库层也 mock——这里测的是路由的编排逻辑（判别、验码、报错翻译），
不是 SQL。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.account import codes

EMAIL = "newuser@example.com"
PHONE_RAW = "13800138000"
PHONE_E164 = "+8613800138000"
STRONG_PASSWORD = "Abcd1234!"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def no_existing_user():
    """数据库里查不到任何用户。"""
    with patch(
        "app.api.v1.auth.routes.database_service.get_user_by_email", MagicMock(return_value=None)
    ), patch(
        "app.api.v1.auth.routes.database_service.get_user_by_phone", MagicMock(return_value=None)
    ):
        yield


def test_request_email_code_sends_code(client, no_existing_user):
    with patch.object(codes, "send_email_code", AsyncMock()) as send:
        resp = client.post("/api/v1/auth/register/request-code", json={"email": EMAIL})

    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    assert send.await_count == 1


def test_request_email_code_rejects_registered_email(client):
    existing = MagicMock(id=1, email=EMAIL)
    with patch(
        "app.api.v1.auth.routes.database_service.get_user_by_email",
        MagicMock(return_value=existing),
    ):
        resp = client.post("/api/v1/auth/register/request-code", json={"email": EMAIL})

    assert resp.status_code == 400


def test_request_email_code_returns_503_when_smtp_missing(client, no_existing_user):
    with patch.object(
        codes, "send_email_code", AsyncMock(side_effect=codes.CodeChannelUnavailableError)
    ):
        resp = client.post("/api/v1/auth/register/request-code", json={"email": EMAIL})

    assert resp.status_code == 503


def test_email_register_rejects_wrong_code(client, no_existing_user):
    with patch.object(
        codes, "verify_email_code", AsyncMock(side_effect=codes.CodeRejectedError)
    ):
        resp = client.post(
            "/api/v1/auth/register/verify",
            json={"email": EMAIL, "code": "000000", "password": STRONG_PASSWORD},
        )

    assert resp.status_code == 400


def test_email_register_creates_user_on_valid_code(client, no_existing_user):
    created = MagicMock(id=42, email=EMAIL, phone=None, username=None)
    with patch.object(codes, "verify_email_code", AsyncMock()), patch(
        "app.api.v1.auth.routes.database_service.create_user", MagicMock(return_value=created)
    ):
        resp = client.post(
            "/api/v1/auth/register/verify",
            json={"email": EMAIL, "code": "123456", "password": STRONG_PASSWORD},
        )

    assert resp.status_code == 200
    assert resp.json()["token"]["access_token"]


def test_email_register_rejects_weak_password(client, no_existing_user):
    resp = client.post(
        "/api/v1/auth/register/verify",
        json={"email": EMAIL, "code": "123456", "password": "weak"},
    )

    assert resp.status_code == 422


def test_password_reset_request_hides_whether_email_exists(client):
    """未注册的邮箱也返回成功，避免接口变成账号探测器。"""
    with patch(
        "app.api.v1.auth.routes.database_service.get_user_by_email", MagicMock(return_value=None)
    ), patch.object(codes, "send_email_code", AsyncMock()) as send:
        resp = client.post("/api/v1/auth/password-reset/request", json={"email": EMAIL})

    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    assert send.await_count == 0, "不该给未注册邮箱真的发信"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/api/test_chan_auth.py -v`
Expected: FAIL，全部 404（端点还不存在）

- [ ] **Step 3: 加导入**

在 `app/api/v1/auth/routes.py` 的 import 区域补：

```python
from redis.asyncio import Redis

from app.cache.client import get_redis
from app.schemas.auth import (
    AccountLoginRequest,
    EmailCodeRequest,
    EmailPasswordResetConfirm,
    EmailRegisterRequest,
    PhoneCodeRequest,
    PhonePasswordResetConfirm,
    PhoneRegisterRequest,
)
from app.services import email as email_service
from app.services.account import codes
from app.services.account.accounts import AccountKind, resolve_account
from app.services.verification_code import (
    Purpose,
    ResendTooSoonError,
    TooManyAttemptsError,
)
from app.utils.phone import InvalidPhoneError, normalize_phone
```

（`AccountKind`、`resolve_account`、`AccountLoginRequest`、Phone 系列在 Task 8、9 用到，
一次性导入，避免反复改 import 块。）

- [ ] **Step 4: 加共用的异常翻译辅助函数**

在 `app/api/v1/auth/routes.py` 的 `router = APIRouter()` 之后加：

```python
def _raise_for_delivery(exc: Exception) -> None:
    """把 codes 层的异常翻译成 HTTP 响应。

    服务层不认识 HTTP 状态码，翻译集中在这里一处，避免九个端点各写一遍
    try/except 金字塔。
    """
    if isinstance(exc, ResendTooSoonError):
        raise HTTPException(
            status_code=429,
            detail=f"验证码已发送，请 {settings.EMAIL_CODE_RESEND_COOLDOWN} 秒后再试",
        ) from None
    if isinstance(exc, codes.CodeChannelUnavailableError):
        raise HTTPException(status_code=503, detail="验证码服务暂不可用，请稍后再试") from None
    if isinstance(exc, codes.CodeDeliveryError):
        raise HTTPException(status_code=502, detail="验证码发送失败，请稍后再试") from None
    if isinstance(exc, TooManyAttemptsError):
        raise HTTPException(status_code=429, detail="验证码错误次数过多，请重新获取") from None
    if isinstance(exc, codes.CodeRejectedError):
        raise HTTPException(status_code=400, detail="验证码错误或已过期") from None
    raise exc


def _normalized_phone(raw: str) -> str:
    """归一化手机号，失败时转成 422。"""
    try:
        return normalize_phone(raw)
    except InvalidPhoneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

- [ ] **Step 5: 加邮箱通道的四个端点**

在 `app/api/v1/auth/routes.py` 末尾追加：

```python
# ---------------------------------------------------------------------------
# 邮箱通道：验证码注册 + 找回密码
#
# 与文件上方那个 legacy 的 POST /register（无验证码）并存。legacy 端点保留是
# 因为已上架的旧版 App 仍在调用，待版本淘汰后再移除。新端点因此只能叫
# /register/verify——/register 这个路径被占了。
# ---------------------------------------------------------------------------


@router.post("/register/request-code")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_email_request_code"][0])
async def request_email_register_code(
    request: Request,
    payload: EmailCodeRequest,
    redis: Redis = Depends(get_redis),
):
    """给待注册的邮箱发验证码。

    对「邮箱已注册」明确报错而不含糊：/register/verify 本身就必须在邮箱重复时
    报错，枚举面本来就存在，在这一步含糊只会让用户白等一封永远不会来的邮件。
    """
    try:
        email = sanitize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = await asyncio.to_thread(database_service.get_user_by_email, email)
    if existing:
        raise HTTPException(status_code=400, detail="该邮箱已被注册，请直接登录")

    try:
        await codes.send_email_code(
            redis, Purpose.REGISTER, email, email_service.render_register
        )
    except Exception as exc:
        _raise_for_delivery(exc)

    logger.info("chan_register_code_sent")
    return {"sent": True}


@router.post("/register/verify", response_model=UserResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["register"][0])
async def register_with_email_code(
    request: Request,
    payload: EmailRegisterRequest,
    redis: Redis = Depends(get_redis),
):
    """校验邮箱验证码并创建账号。

    先验码再建号：邮箱填错时根本不该产生账号。
    """
    try:
        email = sanitize_email(payload.email)
        password = payload.password.get_secret_value()
        validate_password_strength(password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await codes.verify_email_code(redis, Purpose.REGISTER, email, payload.code)
    except Exception as exc:
        _raise_for_delivery(exc)

    existing = await asyncio.to_thread(database_service.get_user_by_email, email)
    if existing:
        raise HTTPException(status_code=400, detail="该邮箱已被注册")

    username = sanitize_string(payload.username) if payload.username else None
    hashed = await asyncio.to_thread(User.hash_password, password)
    user = await asyncio.to_thread(
        database_service.create_user, email, hashed, username, None
    )

    token = create_access_token(str(user.id))
    logger.info("chan_user_registered_by_email", user_id=user.id)
    return UserResponse(
        id=user.id, email=user.email, phone=user.phone, username=user.username, token=token
    )


@router.post("/password-reset/request")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_email_request_code"][0])
async def request_email_password_reset(
    request: Request,
    payload: EmailCodeRequest,
    redis: Redis = Depends(get_redis),
):
    """给邮箱发找回密码验证码。

    无论邮箱是否注册过都返回成功，避免这个接口变成「查某个邮箱有没有在本站
    注册」的探测器。与注册发码那条的取舍不同：注册流程后面必然会因重复而
    报错，这里没有这个约束。
    """
    try:
        email = sanitize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = await asyncio.to_thread(database_service.get_user_by_email, email)
    if existing:
        try:
            await codes.send_email_code(
                redis, Purpose.PASSWORD_RESET, email, email_service.render_password_reset
            )
        except Exception as exc:
            _raise_for_delivery(exc)
        logger.info("chan_password_reset_code_sent")
    else:
        logger.info("chan_password_reset_requested_for_unknown_email")

    return {"sent": True}


@router.post("/password-reset/confirm")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_code_verify"][0])
async def confirm_email_password_reset(
    request: Request,
    payload: EmailPasswordResetConfirm,
    redis: Redis = Depends(get_redis),
):
    """校验邮箱验证码并设置新密码。"""
    try:
        email = sanitize_email(payload.email)
        new_password = payload.new_password.get_secret_value()
        validate_password_strength(new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await codes.verify_email_code(redis, Purpose.PASSWORD_RESET, email, payload.code)
    except Exception as exc:
        _raise_for_delivery(exc)

    user = await asyncio.to_thread(database_service.get_user_by_email, email)
    if user is None:
        # 走到这里说明码验过了但账号没了（并发删号）。不透露具体原因。
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    hashed = await asyncio.to_thread(User.hash_password, new_password)
    # 复用既有的 update_user，change_password 端点走的也是它，不要另加一个改密方法。
    await asyncio.to_thread(
        database_service.update_user, user_id=user.id, hashed_password=hashed
    )
    logger.info("chan_password_reset_done", user_id=user.id)
    return {"reset": True}
```

- [ ] **Step 6: 跑测试**

Run: `uv run pytest tests/api/test_chan_auth.py -v`
Expected: 7 个用例全 PASS

- [ ] **Step 7: 提交**

```bash
git add app/api/v1/auth/routes.py tests/api/
git commit -m "feat(auth): 邮箱验证码注册与找回密码端点"
```

---

### Task 8: 手机通道路由

**Files:**
- Modify: `app/api/v1/auth/routes.py`
- Modify: `tests/api/test_chan_auth.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/api/test_chan_auth.py` 末尾追加：

```python
# ---------- 手机通道 ----------


def test_request_phone_code_normalizes_number(client, no_existing_user):
    with patch.object(codes, "send_sms_code", AsyncMock()) as send:
        resp = client.post(
            "/api/v1/auth/phone/register/request-code", json={"phone": PHONE_RAW}
        )

    assert resp.status_code == 200
    assert send.await_args.args[2] == PHONE_E164, "手机号没有归一化成 E.164"


def test_request_phone_code_rejects_bad_number(client, no_existing_user):
    resp = client.post(
        "/api/v1/auth/phone/register/request-code", json={"phone": "12800138000"}
    )

    assert resp.status_code == 422


def test_request_phone_code_rejects_registered_number(client):
    existing = MagicMock(id=1, phone=PHONE_E164)
    with patch(
        "app.api.v1.auth.routes.database_service.get_user_by_phone",
        MagicMock(return_value=existing),
    ):
        resp = client.post(
            "/api/v1/auth/phone/register/request-code", json={"phone": PHONE_RAW}
        )

    assert resp.status_code == 400


def test_phone_register_creates_user_with_null_email(client, no_existing_user):
    """手机号注册的用户没有邮箱，email 必须能是 None。"""
    created = MagicMock(id=43, email=None, phone=PHONE_E164, username=None)
    with patch.object(codes, "verify_sms_code", AsyncMock()), patch(
        "app.api.v1.auth.routes.database_service.create_user", MagicMock(return_value=created)
    ) as create:
        resp = client.post(
            "/api/v1/auth/phone/register",
            json={"phone": PHONE_RAW, "code": "123456", "password": STRONG_PASSWORD},
        )

    assert resp.status_code == 200
    assert resp.json()["email"] is None
    assert resp.json()["phone"] == PHONE_E164
    assert create.call_args.args[0] is None, "email 应为 None"
    assert create.call_args.args[3] == PHONE_E164, "phone 没传进去"


def test_phone_register_rejects_exhausted_attempts(client, no_existing_user):
    from app.services.verification_code import TooManyAttemptsError

    with patch.object(codes, "verify_sms_code", AsyncMock(side_effect=TooManyAttemptsError)):
        resp = client.post(
            "/api/v1/auth/phone/register",
            json={"phone": PHONE_RAW, "code": "000000", "password": STRONG_PASSWORD},
        )

    assert resp.status_code == 429


def test_phone_password_reset_request_hides_whether_phone_exists(client, no_existing_user):
    with patch.object(codes, "send_sms_code", AsyncMock()) as send:
        resp = client.post(
            "/api/v1/auth/phone/password-reset/request", json={"phone": PHONE_RAW}
        )

    assert resp.status_code == 200
    assert send.await_count == 0, "不该给未注册手机号真的发短信"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/api/test_chan_auth.py -v -k phone`
Expected: FAIL，404

- [ ] **Step 3: 加手机通道的四个端点**

在 `app/api/v1/auth/routes.py` 末尾追加：

```python
# ---------------------------------------------------------------------------
# 手机通道：与邮箱那套完全平行。
#
# 唯一的实质差别是验证码由阿里云生成保管核验，我们拿不到明文——这个不对称由
# 外部服务的形态决定，已经封装在 services/account/codes.py 里，路由层无感。
# ---------------------------------------------------------------------------


@router.post("/phone/register/request-code")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_phone_request_code"][0])
async def request_phone_register_code(
    request: Request,
    payload: PhoneCodeRequest,
    redis: Redis = Depends(get_redis),
):
    """给待注册的手机号发验证码。"""
    phone = _normalized_phone(payload.phone)

    existing = await asyncio.to_thread(database_service.get_user_by_phone, phone)
    if existing:
        raise HTTPException(status_code=400, detail="该手机号已被注册，请直接登录")

    try:
        await codes.send_sms_code(redis, Purpose.PHONE_REGISTER, phone)
    except Exception as exc:
        _raise_for_delivery(exc)

    logger.info("chan_phone_register_code_sent")
    return {"sent": True}


@router.post("/phone/register", response_model=UserResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["register"][0])
async def register_with_phone_code(
    request: Request,
    payload: PhoneRegisterRequest,
    redis: Redis = Depends(get_redis),
):
    """校验短信验证码并创建账号。手机号注册的用户 email 为 None。"""
    phone = _normalized_phone(payload.phone)
    try:
        password = payload.password.get_secret_value()
        validate_password_strength(password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await codes.verify_sms_code(redis, Purpose.PHONE_REGISTER, phone, payload.code)
    except Exception as exc:
        _raise_for_delivery(exc)

    existing = await asyncio.to_thread(database_service.get_user_by_phone, phone)
    if existing:
        raise HTTPException(status_code=400, detail="该手机号已被注册")

    username = sanitize_string(payload.username) if payload.username else None
    hashed = await asyncio.to_thread(User.hash_password, password)
    user = await asyncio.to_thread(
        database_service.create_user, None, hashed, username, phone
    )

    token = create_access_token(str(user.id))
    logger.info("chan_user_registered_by_phone", user_id=user.id)
    return UserResponse(
        id=user.id, email=user.email, phone=user.phone, username=user.username, token=token
    )


@router.post("/phone/password-reset/request")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_phone_request_code"][0])
async def request_phone_password_reset(
    request: Request,
    payload: PhoneCodeRequest,
    redis: Redis = Depends(get_redis),
):
    """给手机号发找回密码验证码。号码是否注册过都返回成功，避免账号探测。"""
    phone = _normalized_phone(payload.phone)

    existing = await asyncio.to_thread(database_service.get_user_by_phone, phone)
    if existing:
        try:
            await codes.send_sms_code(redis, Purpose.PHONE_PASSWORD_RESET, phone)
        except Exception as exc:
            _raise_for_delivery(exc)
        logger.info("chan_phone_password_reset_code_sent")
    else:
        logger.info("chan_phone_password_reset_requested_for_unknown_phone")

    return {"sent": True}


@router.post("/phone/password-reset/confirm")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chan_code_verify"][0])
async def confirm_phone_password_reset(
    request: Request,
    payload: PhonePasswordResetConfirm,
    redis: Redis = Depends(get_redis),
):
    """校验短信验证码并设置新密码。"""
    phone = _normalized_phone(payload.phone)
    try:
        new_password = payload.new_password.get_secret_value()
        validate_password_strength(new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await codes.verify_sms_code(redis, Purpose.PHONE_PASSWORD_RESET, phone, payload.code)
    except Exception as exc:
        _raise_for_delivery(exc)

    user = await asyncio.to_thread(database_service.get_user_by_phone, phone)
    if user is None:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    hashed = await asyncio.to_thread(User.hash_password, new_password)
    # 复用既有的 update_user，change_password 端点走的也是它，不要另加一个改密方法。
    await asyncio.to_thread(
        database_service.update_user, user_id=user.id, hashed_password=hashed
    )
    logger.info("chan_phone_password_reset_done", user_id=user.id)
    return {"reset": True}
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/api/test_chan_auth.py -v`
Expected: 13 个用例全 PASS

- [ ] **Step 5: 提交**

```bash
git add app/api/v1/auth/routes.py tests/api/test_chan_auth.py
git commit -m "feat(auth): 手机号验证码注册与找回密码端点"
```

---

### Task 9: 统一登录端点

**Files:**
- Modify: `app/api/v1/auth/routes.py`
- Modify: `tests/api/test_chan_auth.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/api/test_chan_auth.py` 末尾追加：

```python
# ---------- 统一登录 ----------


def test_login_by_email(client):
    user = MagicMock(id=1, email=EMAIL, phone=None)
    user.verify_password.return_value = True
    with patch(
        "app.api.v1.auth.routes.database_service.get_user_by_email",
        MagicMock(return_value=user),
    ):
        resp = client.post(
            "/api/v1/auth/login/account", json={"account": EMAIL, "password": STRONG_PASSWORD}
        )

    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_by_phone_looks_up_normalized_number(client):
    user = MagicMock(id=2, email=None, phone=PHONE_E164)
    user.verify_password.return_value = True
    lookup = MagicMock(return_value=user)
    with patch("app.api.v1.auth.routes.database_service.get_user_by_phone", lookup):
        resp = client.post(
            "/api/v1/auth/login/account",
            json={"account": PHONE_RAW, "password": STRONG_PASSWORD},
        )

    assert resp.status_code == 200
    assert lookup.call_args.args[0] == PHONE_E164


def test_login_with_unknown_account_returns_401(client, no_existing_user):
    resp = client.post(
        "/api/v1/auth/login/account", json={"account": EMAIL, "password": STRONG_PASSWORD}
    )

    assert resp.status_code == 401


def test_login_with_wrong_password_returns_401(client):
    user = MagicMock(id=1, email=EMAIL, phone=None)
    user.verify_password.return_value = False
    with patch(
        "app.api.v1.auth.routes.database_service.get_user_by_email",
        MagicMock(return_value=user),
    ):
        resp = client.post(
            "/api/v1/auth/login/account", json={"account": EMAIL, "password": "Wrong123!"}
        )

    assert resp.status_code == 401


def test_login_error_does_not_distinguish_unknown_account_from_bad_password(client):
    """两种失败必须返回一模一样的响应，否则接口能被用来枚举账号。"""
    user = MagicMock(id=1, email=EMAIL, phone=None)
    user.verify_password.return_value = False
    with patch(
        "app.api.v1.auth.routes.database_service.get_user_by_email",
        MagicMock(return_value=user),
    ):
        bad_pw = client.post(
            "/api/v1/auth/login/account", json={"account": EMAIL, "password": "Wrong123!"}
        )
    with patch(
        "app.api.v1.auth.routes.database_service.get_user_by_email",
        MagicMock(return_value=None),
    ):
        unknown = client.post(
            "/api/v1/auth/login/account", json={"account": EMAIL, "password": "Wrong123!"}
        )

    assert bad_pw.status_code == unknown.status_code
    assert bad_pw.json() == unknown.json()


def test_login_rejects_garbage_account(client):
    resp = client.post(
        "/api/v1/auth/login/account",
        json={"account": "not-an-account", "password": STRONG_PASSWORD},
    )

    assert resp.status_code == 422
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/api/test_chan_auth.py -v -k login`
Expected: FAIL，404

- [ ] **Step 3: 实现端点**

在 `app/api/v1/auth/routes.py` 末尾追加：

```python
# ---------------------------------------------------------------------------
# 统一登录
#
# 与文件上方那个 Form 形态的 POST /login 并存。不改那一个而是新增，是因为它的
# 字段名是 email、内容类型是 form-urlencoded，已上架的旧版 App 和 Web 都在用；
# 同一路径同一方法也没法挂两个签名。
# ---------------------------------------------------------------------------


@router.post("/login/account", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["login"][0])
async def login_by_account(request: Request, payload: AccountLoginRequest):
    """手机号或邮箱 + 密码登录，类型由服务端判别。"""
    try:
        kind, value = resolve_account(payload.account)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if kind is AccountKind.PHONE:
        user = await asyncio.to_thread(database_service.get_user_by_phone, value)
    else:
        user = await asyncio.to_thread(database_service.get_user_by_email, value)

    # 「账号不存在」和「密码错误」必须返回完全相同的响应，否则这个接口就是
    # 一个账号枚举器。密码校验也照常跑一次，避免用响应时间区分两者。
    password = payload.password.get_secret_value()
    if user is None or not await asyncio.to_thread(user.verify_password, password):
        logger.warning("chan_login_failed", kind=kind.value)
        raise HTTPException(
            status_code=401,
            detail={"message": "账号或密码错误", "code": "INVALID_CREDENTIALS"},
        )

    token = create_access_token(str(user.id))
    logger.info("chan_login_successful", user_id=user.id, kind=kind.value)
    return TokenResponse(
        access_token=token.access_token,
        token_type=token.token_type,
        expires_at=token.expires_at,
    )
```

注意 `test_login_error_does_not_distinguish...` 会锁住这个行为：如果实现里
对「账号不存在」提前 return 了不同的 detail，测试会失败。

- [ ] **Step 4: 跑全部端点测试**

Run: `uv run pytest tests/api/test_chan_auth.py -v`
Expected: 19 个用例全 PASS

- [ ] **Step 5: 提交**

```bash
git add app/api/v1/auth/routes.py tests/api/test_chan_auth.py
git commit -m "feat(auth): 统一登录端点，手机号与邮箱自动判别"
```

---

### Task 10: 全量验收

- [ ] **Step 1: 跑整套测试**

Run: `uv run pytest -m "not slow" -q`
Expected: 无失败。特别确认 `tests/services/vocabulary/` 全绿——WordLens 是本次
唯一被动到的既有功能。

- [ ] **Step 2: ruff + pyright**

Run: `make check`
Expected: 无报错

- [ ] **Step 3: 启动服务并核对路由表**

Run: `make dev`，另开一个终端跑：

```bash
curl -s localhost:8000/openapi.json | python3 -c "
import json,sys
paths = json.load(sys.stdin)['paths']
for p in sorted(k for k in paths if k.startswith('/api/v1/auth')):
    print(p, sorted(paths[p].keys()))
"
```

Expected: 输出里包含这九条新路径：

```
/api/v1/auth/login/account
/api/v1/auth/password-reset/confirm
/api/v1/auth/password-reset/request
/api/v1/auth/phone/password-reset/confirm
/api/v1/auth/phone/password-reset/request
/api/v1/auth/phone/register
/api/v1/auth/phone/register/request-code
/api/v1/auth/register/request-code
/api/v1/auth/register/verify
```

且 legacy 的 `/api/v1/auth/register` 和 `/api/v1/auth/login` 仍在。

- [ ] **Step 4: 手工验一次错误路径**

服务仍在跑，执行：

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/api/v1/auth/phone/register/request-code \
  -H 'Content-Type: application/json' -d '{"phone":"12800138000"}'
```

Expected: `422`（号段非法）

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/api/v1/auth/phone/register/request-code \
  -H 'Content-Type: application/json' -d '{"phone":"13800138000"}'
```

Expected: `503`（本地没配阿里云凭据，这正是预期——不是 500）

- [ ] **Step 5: 提交收尾**

```bash
git add -A
git commit -m "chore(auth): 双通道认证后端验收通过"
```

---

## 后续计划

- `docs/superpowers/plans/2026-08-22-chan-auth-ios.md`（待写）：iOS 客户端
- `docs/superpowers/plans/2026-08-22-chan-auth-web.md`（待写）：Web 前端

两者都依赖本计划先完成并合入。
