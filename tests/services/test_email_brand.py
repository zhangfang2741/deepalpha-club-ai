"""邮件品牌落款测试。

两个 App 共用一套 SMTP 发信，但署名必须各是各的——缠论用户收到署名
「鹦鹉背单词」的验证码邮件会直接当成钓鱼邮件。
"""

from app.core.config import settings
from app.services import email as email_service


def test_render_register_uses_given_brand():
    """注册邮件的主题、HTML、纯文本三处都要用传入的品牌名。"""
    subject, html, text = email_service.render_register("123456", 10, brand="DeepAlpha 缠论")

    assert "DeepAlpha 缠论" in subject
    assert "DeepAlpha 缠论" in html
    assert "DeepAlpha 缠论" in text


def test_render_password_reset_uses_given_brand():
    """找回密码邮件同样要用传入的品牌名。"""
    subject, html, _ = email_service.render_password_reset("123456", 10, brand="DeepAlpha 缠论")

    assert "DeepAlpha 缠论" in subject
    assert "DeepAlpha 缠论" in html


def test_render_defaults_to_smtp_from_name():
    """不传 brand 时行为与改造前一致，WordLens 不受影响。"""
    subject, _, _ = email_service.render_register("123456", 10)

    assert settings.SMTP_FROM_NAME in subject


def test_chan_brand_name_has_sensible_default():
    """缠论品牌名的默认值。"""
    assert settings.CHAN_BRAND_NAME == "DeepAlpha 缠论"
