from __future__ import annotations

import pytest
from pydantic import ValidationError

from kb_service.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


MINIMAL_SECRET = "test-secret-key-0123456789"  # ≥16 位，pydantic 的 min_length 要求


def test_defaults(monkeypatch):
    """喂饱必需字段后，其余全取代码默认值。"""
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setenv("SECRET_KEY", MINIMAL_SECRET)  # ← 补这一行：把必填项喂饱
    s = Settings(_env_file=None)
    assert s.log_level == "INFO"
    assert s.env == "dev"  # 顺手多验两个默认值，反正免费


def test_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", MINIMAL_SECRET)  # ← 同样要补
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings(_env_file=None)
    assert s.log_level == "DEBUG"


def test_env_file_provides_value(tmp_path, monkeypatch):
    """验证 .env 文件能提供值（且优先级高于代码默认值）。"""
    env_file = tmp_path / ".env"
    env_file.write_text(f"SECRET_KEY={MINIMAL_SECRET}\nLOG_LEVEL=DEBUG")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    s = Settings(_env_file=env_file)
    assert s.log_level == "DEBUG"


def test_env_var_beats_env_file(tmp_path, monkeypatch):
    """验证 环境变量 > .env 文件。"""
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    env_file = tmp_path / ".env"
    env_file.write_text(f"SECRET_KEY={MINIMAL_SECRET}\nLOG_LEVEL=DEBUG")
    s = Settings(_env_file=env_file)
    assert s.log_level == "INFO"


def test_secret_key_too_short_raises(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "123")
    with pytest.raises(ValidationError, match="at least 16 characters"):
        Settings(_env_file=None)


def test_get_settings_cached(monkeypatch):
    """get_settings() 的 lru_cache：环境变了拿的还是旧对象；cache_clear 后才见新值。"""
    monkeypatch.setenv("SECRET_KEY", MINIMAL_SECRET)
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    s1 = get_settings()  # ← 第一次调用：读环境，进缓存

    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s2 = get_settings()  # ← 第二次调用：命中缓存
    assert s1 is s2  # ← 同一个对象（判身份，对象不是字符串）
    assert s2.log_level == "INFO"  # ← 还是旧值：缓存挡住了新环境

    get_settings.cache_clear()  # ← 官方清理口
    s3 = get_settings()  # ← 第三次：重新读环境
    assert s3.log_level == "DEBUG"  # ← 新值可见
    assert s3 is not s1  # ← 清过缓存，是新对象了
