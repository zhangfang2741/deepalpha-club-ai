"""阿里云号码认证服务（PNVS）短信验证码测试。

两块重点：
1. RPC 签名。算错的线上表现是「一直 SignatureDoesNotMatch，但看不出哪里错」，
   而且拿不到凭据就没法端到端验证，只能靠单测钉住规范里几条易错规则。
2. 核验结果的判定。阿里云文档明确写了「接口调用成功不代表验证码核验成功」，
   只看 Code == "OK" 的话任何验证码都会被判通过——这是整个接入里后果最严重
   的一个坑，单独测。
"""

import pytest

from app.services import sms


class TestPercentEncode:
    """阿里云在标准 URL 编码之上有三条特殊规则，差一个字符签名就对不上。"""

    def test_space_becomes_percent_20_not_plus(self):
        assert sms._percent_encode("a b") == "a%20b"

    def test_asterisk_is_encoded(self):
        assert sms._percent_encode("*") == "%2A"

    def test_tilde_is_not_encoded(self):
        assert sms._percent_encode("~") == "~"

    def test_reserved_chars_are_encoded(self):
        assert sms._percent_encode("a/b&c=d") == "a%2Fb%26c%3Dd"


class TestSignature:
    """签名是确定性的：同样的输入必须永远得到同样的结果。"""

    PARAMS = {
        "AccessKeyId": "testid",
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": "13800138000",
        "RegionId": "cn-hangzhou",
        "SignName": "测试签名",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": "fixed-nonce",
        "SignatureVersion": "1.0",
        "TemplateCode": "SMS_123456",
        "TemplateParam": '{"code":"123456"}',
        "Timestamp": "2026-08-15T10:00:00Z",
        "Version": "2017-05-25",
    }

    def test_is_deterministic(self):
        a = sms.build_signature(self.PARAMS, "secret")
        b = sms.build_signature(self.PARAMS, "secret")
        assert a == b

    def test_depends_on_secret(self):
        assert sms.build_signature(self.PARAMS, "s1") != sms.build_signature(self.PARAMS, "s2")

    def test_param_order_does_not_matter(self):
        """规范要求按键名排序，所以传入 dict 的顺序不该影响结果。"""
        reversed_params = dict(reversed(list(self.PARAMS.items())))
        assert sms.build_signature(self.PARAMS, "secret") == sms.build_signature(
            reversed_params, "secret"
        )

    def test_any_param_change_changes_signature(self):
        base = sms.build_signature(self.PARAMS, "secret")
        changed = dict(self.PARAMS, PhoneNumbers="13900139000")
        assert sms.build_signature(changed, "secret") != base

    def test_method_participates_in_signature(self):
        assert sms.build_signature(self.PARAMS, "secret", "GET") != sms.build_signature(
            self.PARAMS, "secret", "POST"
        )

    def test_signature_is_base64(self):
        import base64

        sig = sms.build_signature(self.PARAMS, "secret")
        # 能被解码回 20 字节即为合法的 HMAC-SHA1 摘要
        assert len(base64.b64decode(sig)) == 20


class TestConfiguration:
    def test_not_configured_when_credentials_missing(self, monkeypatch):
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_ACCESS_KEY_ID", "")
        assert sms.is_configured() is False

    def test_not_configured_when_sign_name_missing(self, monkeypatch):
        """签名和模板必须先过审，缺任何一个都发不出短信。"""
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_ACCESS_KEY_ID", "id")
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_ACCESS_KEY_SECRET", "secret")
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_SIGN_NAME", "")
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_TEMPLATE_CODE", "SMS_1")
        assert sms.is_configured() is False

    def test_configured_when_all_present(self, monkeypatch):
        for key, value in [
            ("ALIYUN_SMS_ACCESS_KEY_ID", "id"),
            ("ALIYUN_SMS_ACCESS_KEY_SECRET", "secret"),
            ("ALIYUN_SMS_SIGN_NAME", "鹦鹉背单词"),
            ("ALIYUN_SMS_TEMPLATE_CODE", "SMS_1"),
        ]:
            monkeypatch.setattr(sms.settings, key, value)
        assert sms.is_configured() is True

    async def test_send_raises_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_ACCESS_KEY_ID", "")
        with pytest.raises(sms.SMSNotConfiguredError):
            await sms.send_verification_code("13800138000", "123456")


class TestSendParams:
    @pytest.fixture(autouse=True)
    def _creds(self, monkeypatch):
        for key, value in [
            ("ALIYUN_SMS_ACCESS_KEY_ID", "id"),
            ("ALIYUN_SMS_SIGN_NAME", "sign"),
            ("ALIYUN_SMS_TEMPLATE_CODE", "SMS_1"),
            ("ALIYUN_SMS_REGION", "cn-hangzhou"),
        ]:
            monkeypatch.setattr(sms.settings, key, value)

    def test_template_param_is_compact_json(self):
        """必须是紧凑 JSON：json.dumps 默认的 ", " 分隔符会让签名与实际内容不一致。"""
        params = sms.build_send_params("13800138000", "86")
        assert ", " not in params["TemplateParam"]

    def test_code_placeholder_lets_aliyun_generate(self):
        """用 ##code## 占位，验证码由阿里云生成，我们不接触明文。"""
        params = sms.build_send_params("13800138000", "86")
        assert "##code##" in params["TemplateParam"]

    def test_duplicate_policy_overwrites_old_code(self):
        """默认允许多码并存，等于把爆破空间放大数倍，必须设成覆盖。"""
        assert sms.build_send_params("13800138000", "86")["DuplicatePolicy"] == "1"

    def test_uses_six_digit_code(self):
        assert sms.build_send_params("13800138000", "86")["CodeLength"] == "6"

    def test_action_and_version(self):
        params = sms.build_send_params("13800138000", "86")
        assert params["Action"] == "SendSmsVerifyCode"
        assert params["Version"] == "2017-05-25"

    def test_check_params_carry_code(self):
        params = sms.build_check_params("13800138000", "123456", "86")
        assert params["Action"] == "CheckSmsVerifyCode"
        assert params["VerifyCode"] == "123456"

    def test_nonce_differs_between_calls(self):
        """Nonce 用于防重放，两次调用必须不同。"""
        a = sms.build_send_params("13800138000", "86")["SignatureNonce"]
        b = sms.build_send_params("13800138000", "86")["SignatureNonce"]
        assert a != b


class TestCheckResult:
    """核验结果只认 Model.VerifyResult，不能只看 Code。"""

    @pytest.fixture(autouse=True)
    def _creds(self, monkeypatch):
        for key, value in [
            ("ALIYUN_SMS_ACCESS_KEY_ID", "id"),
            ("ALIYUN_SMS_ACCESS_KEY_SECRET", "secret"),
            ("ALIYUN_SMS_SIGN_NAME", "sign"),
            ("ALIYUN_SMS_TEMPLATE_CODE", "SMS_1"),
        ]:
            monkeypatch.setattr(sms.settings, key, value)

    async def _check_with(self, monkeypatch, body: dict) -> bool:
        async def fake_call(params):
            return body

        monkeypatch.setattr(sms, "_call", fake_call)
        return await sms.check_verification_code("13800138000", "123456")

    async def test_pass_means_success(self, monkeypatch):
        assert await self._check_with(
            monkeypatch, {"Code": "OK", "Model": {"VerifyResult": "PASS"}}
        ) is True

    async def test_unknown_means_failure(self, monkeypatch):
        """Code 是 OK 但 VerifyResult 不是 PASS —— 必须判为失败。"""
        assert await self._check_with(
            monkeypatch, {"Code": "OK", "Model": {"VerifyResult": "UNKNOWN"}}
        ) is False

    async def test_missing_model_means_failure(self, monkeypatch):
        """响应缺 Model 时不能默认放行。"""
        assert await self._check_with(monkeypatch, {"Code": "OK"}) is False

    async def test_api_error_raises_not_returns_false(self, monkeypatch):
        """请求本身失败要区别于「验证码不对」，否则会误扣用户的错误次数。"""
        with pytest.raises(sms.SMSSendError):
            await self._check_with(monkeypatch, {"Code": "InvalidAccessKeyId"})
