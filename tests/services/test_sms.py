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
        """赠送签名有好几个，阿里云不知道该用哪个，必须显式配置。"""
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_ACCESS_KEY_ID", "id")
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_ACCESS_KEY_SECRET", "secret")
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_SIGN_NAME", "")
        assert sms.is_configured() is False

    def test_configured_when_all_present(self, monkeypatch):
        for key, value in [
            ("ALIYUN_SMS_ACCESS_KEY_ID", "id"),
            ("ALIYUN_SMS_ACCESS_KEY_SECRET", "secret"),
            ("ALIYUN_SMS_SIGN_NAME", "鹦鹉背单词"),
        ]:
            monkeypatch.setattr(sms.settings, key, value)
        assert sms.is_configured() is True

    async def test_send_raises_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_ACCESS_KEY_ID", "")
        with pytest.raises(sms.SMSNotConfiguredError):
            await sms.send_verification_code("13800138000", "100001")


class TestSendParams:
    @pytest.fixture(autouse=True)
    def _creds(self, monkeypatch):
        for key, value in [
            ("ALIYUN_SMS_ACCESS_KEY_ID", "id"),
            ("ALIYUN_SMS_SIGN_NAME", "sign"),
            ("ALIYUN_SMS_REGION", "cn-hangzhou"),
        ]:
            monkeypatch.setattr(sms.settings, key, value)

    def test_template_param_is_compact_json(self):
        """必须是紧凑 JSON：json.dumps 默认的 ", " 分隔符会让签名与实际内容不一致。"""
        params = sms.build_send_params("13800138000", "86", "100001")
        assert ", " not in params["TemplateParam"]

    def test_code_placeholder_lets_aliyun_generate(self):
        """用 ##code## 占位，验证码由阿里云生成，我们不接触明文。"""
        params = sms.build_send_params("13800138000", "86", "100001")
        assert "##code##" in params["TemplateParam"]

    def test_duplicate_policy_overwrites_old_code(self):
        """默认允许多码并存，等于把爆破空间放大数倍，必须设成覆盖。"""
        assert sms.build_send_params("13800138000", "86", "100001")["DuplicatePolicy"] == "1"

    def test_uses_six_digit_code(self):
        assert sms.build_send_params("13800138000", "86", "100001")["CodeLength"] == "6"

    def test_template_variables_match_system_template(self):
        """系统模板的变量名就是 code 和 min，对不上会发出字面写着 ${code} 的短信。"""
        param = sms.build_send_params("13800138000", "86", "100001")["TemplateParam"]
        assert '"code"' in param and '"min"' in param

    def test_template_code_is_passed_through(self):
        """按用途选模板：注册用 100001、重置密码用 100003。"""
        assert sms.build_send_params("1", "86", "100003")["TemplateCode"] == "100003"

    def test_action_and_version(self):
        params = sms.build_send_params("13800138000", "86", "100001")
        assert params["Action"] == "SendSmsVerifyCode"
        assert params["Version"] == "2017-05-25"

    def test_check_params_carry_code(self):
        params = sms.build_check_params("13800138000", "123456", "86")
        assert params["Action"] == "CheckSmsVerifyCode"
        assert params["VerifyCode"] == "123456"

    def test_nonce_differs_between_calls(self):
        """Nonce 用于防重放，两次调用必须不同。"""
        a = sms.build_send_params("13800138000", "86", "100001")["SignatureNonce"]
        b = sms.build_send_params("13800138000", "86", "100001")["SignatureNonce"]
        assert a != b


class TestCheckResult:
    """核验结果只认 Model.VerifyResult，不能只看 Code。"""

    @pytest.fixture(autouse=True)
    def _creds(self, monkeypatch):
        for key, value in [
            ("ALIYUN_SMS_ACCESS_KEY_ID", "id"),
            ("ALIYUN_SMS_ACCESS_KEY_SECRET", "secret"),
            ("ALIYUN_SMS_SIGN_NAME", "sign"),
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


class TestGetMobileOneTap:
    """一键登录：token 换号码。只看 GetMobileResultDTO.Mobile，别的都算失败。"""

    @pytest.fixture(autouse=True)
    def _creds(self, monkeypatch):
        for key, value in [
            ("ALIYUN_SMS_ACCESS_KEY_ID", "id"),
            ("ALIYUN_SMS_ACCESS_KEY_SECRET", "secret"),
        ]:
            monkeypatch.setattr(sms.settings, key, value)

    async def _get_mobile_with(self, monkeypatch, body: dict) -> str:
        async def fake_call(params):
            return body

        monkeypatch.setattr(sms, "_call", fake_call)
        return await sms.get_mobile_by_token("tok")

    async def test_returns_mobile_on_success(self, monkeypatch):
        mobile = await self._get_mobile_with(
            monkeypatch, {"Code": "OK", "GetMobileResultDTO": {"Mobile": "13800138000"}}
        )
        assert mobile == "13800138000"

    async def test_missing_mobile_raises_token_error(self, monkeypatch):
        """Code=OK 但没号码，绝不能凭空建号，按 token 失效处理。"""
        with pytest.raises(sms.OneTapTokenError):
            await self._get_mobile_with(monkeypatch, {"Code": "OK"})

    async def test_isv_error_is_token_error(self, monkeypatch):
        """凭证过期/非法是业务失败，走回退，返回 401。"""
        with pytest.raises(sms.OneTapTokenError):
            await self._get_mobile_with(monkeypatch, {"Code": "isv.INVALID_ACCESS_TOKEN"})

    async def test_auth_error_is_system_failure(self, monkeypatch):
        """鉴权/系统错误不能伪装成 token 失效，否则配置问题被永远掩盖。"""
        with pytest.raises(sms.SMSSendError):
            await self._get_mobile_with(monkeypatch, {"Code": "InvalidAccessKeyId"})

    async def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_ACCESS_KEY_ID", "")
        with pytest.raises(sms.SMSNotConfiguredError):
            await sms.get_mobile_by_token("tok")

    def test_get_mobile_params_carry_token_and_action(self):
        params = sms.build_get_mobile_params("tok123")
        assert params["Action"] == "GetMobile"
        assert params["AccessToken"] == "tok123"


class TestSchemeName:
    """发码和核验必须带同一个方案名，否则核验永远返回 UNKNOWN。"""

    def test_scheme_included_in_both_when_configured(self, monkeypatch):
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_SCHEME_NAME", "wordlens")
        assert sms.build_send_params("13800138000", "86", "100001")["SchemeName"] == "wordlens"
        assert sms.build_check_params("13800138000", "1", "86")["SchemeName"] == "wordlens"

    def test_scheme_omitted_when_blank(self, monkeypatch):
        """留空时不传该参数，让阿里云用默认方案；传空串会被判成非法方案名。"""
        monkeypatch.setattr(sms.settings, "ALIYUN_SMS_SCHEME_NAME", "")
        assert "SchemeName" not in sms.build_send_params("13800138000", "86", "100001")
        assert "SchemeName" not in sms.build_check_params("13800138000", "1", "86")


class TestCheckErrorClassification:
    """区分「验证码不对」和「系统故障」。

    两者对用户的含义完全不同：前者该提示「验证码错误」让他重输，后者该提示
    「稍后再试」。混为一谈的话，输错验证码的用户会看到「请稍后再试」，
    再试一百次也没用——问题出在他输错了。
    """

    @pytest.fixture(autouse=True)
    def _creds(self, monkeypatch):
        for key, value in [
            ("ALIYUN_SMS_ACCESS_KEY_ID", "id"),
            ("ALIYUN_SMS_ACCESS_KEY_SECRET", "secret"),
            ("ALIYUN_SMS_SIGN_NAME", "sign"),
        ]:
            monkeypatch.setattr(sms.settings, key, value)

    async def _check(self, monkeypatch, body: dict):
        async def fake_call(params):
            return body

        monkeypatch.setattr(sms, "_call", fake_call)
        return await sms.check_verification_code("13800138000", "123456")

    async def test_isv_error_is_treated_as_wrong_code(self, monkeypatch):
        """带 isv. 前缀的是阿里云业务层失败，对用户就是「验证码错误」。"""
        with pytest.raises(sms.SMSCodeInvalidError):
            await self._check(monkeypatch, {"Code": "isv.SMS_VERIFY_CODE_NOT_EXIST"})

    async def test_auth_error_is_treated_as_system_failure(self, monkeypatch):
        """鉴权/配置错误不能伪装成「验证码错误」，否则配置问题会被永远掩盖。"""
        with pytest.raises(sms.SMSSendError):
            await self._check(monkeypatch, {"Code": "InvalidAccessKeyId"})

    async def test_signature_error_is_system_failure(self, monkeypatch):
        with pytest.raises(sms.SMSSendError):
            await self._check(monkeypatch, {"Code": "SignatureDoesNotMatch"})
