"""配置层：统一从项目根 .env 读取，任何模块都不直接读 os.environ。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw.strip()) if raw and raw.strip() else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw.strip()) if raw and raw.strip() else default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # 运行环境
    app_env: str
    log_level: str
    log_dir: str
    data_dir: str

    # 模型
    model: str
    temperature: float
    max_tokens: int | None
    deepseek_api_key: str
    openai_api_key: str
    anthropic_api_key: str

    # 火山方舟
    volc_api_key: str
    volc_base_url: str

    # 数据库
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_db: str
    mysql_uri_raw: str
    mysql_pool_size: int
    mysql_connect_timeout: int

    # SQL 只读策略
    sql_read_only: bool
    sql_max_rows: int
    sql_max_chars: int
    sql_sample_rows: int
    sql_statement_timeout_ms: int

    # 存储
    checkpoint_db: str

    # LangSmith
    langsmith_tracing: bool
    langsmith_api_key: str
    langsmith_project: str
    langsmith_endpoint: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=_str("APP_ENV", "dev"),
            log_level=_str("LOG_LEVEL", "INFO").upper(),
            log_dir=_str("LOG_DIR", "./logs"),
            data_dir=_str("DATA_DIR", "./data"),
            model=_str("MODEL", "deepseek:deepseek-chat"),
            temperature=_float("MODEL_TEMPERATURE", 0.0),
            max_tokens=_int("MODEL_MAX_TOKENS", 0) or None,
            deepseek_api_key=_str("DEEPSEEK_API_KEY"),
            openai_api_key=_str("OPENAI_API_KEY"),
            anthropic_api_key=_str("ANTHROPIC_API_KEY"),
            volc_api_key=_str("VOLC_API_KEY") or _str("VOLCENGINE_API_KEY") or _str("ARK_API_KEY"),
            volc_base_url=(
                _str("VOLC_BASE_URL")
                or _str("VOLCENGINE_BASE_URL")
                or "https://ark.cn-beijing.volces.com/api/v3"
            ),
            mysql_host=_str("MYSQL_HOST", "127.0.0.1"),
            mysql_port=_int("MYSQL_PORT", 3306),
            mysql_user=_str("MYSQL_USER", "ettj_ro"),
            mysql_password=_str("MYSQL_PASSWORD"),
            mysql_db=_str("MYSQL_DB"),
            mysql_uri_raw=_str("MYSQL_URI"),
            mysql_pool_size=_int("MYSQL_POOL_SIZE", 5),
            mysql_connect_timeout=_int("MYSQL_CONNECT_TIMEOUT", 10),
            sql_read_only=_bool("SQL_READ_ONLY", True),
            sql_max_rows=_int("SQL_MAX_ROWS", 100),
            sql_max_chars=_int("SQL_MAX_CHARS", 12000),
            sql_sample_rows=_int("SQL_SAMPLE_ROWS", 3),
            sql_statement_timeout_ms=_int("SQL_STATEMENT_TIMEOUT_MS", 15000),
            checkpoint_db=_str("CHECKPOINT_DB", "./data/checkpoints.sqlite"),
            langsmith_tracing=_bool("LANGSMITH_TRACING", False),
            langsmith_api_key=_str("LANGSMITH_API_KEY"),
            langsmith_project=_str("LANGSMITH_PROJECT", "ETTJ"),
            langsmith_endpoint=_str("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        )

    # ------------------------------------------------------------- 路径
    def resolve(self, relative: str) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    @property
    def checkpoint_path(self) -> Path:
        return self.resolve(self.checkpoint_db)

    # ------------------------------------------------------------- 连接串
    def mysql_url(self) -> "URL":
        """用 URL 对象而不是字符串，密码里的 @ : / 等字符不会被拼坏。"""
        from sqlalchemy.engine import URL, make_url

        if self.mysql_uri_raw:
            return make_url(self.mysql_uri_raw)
        return URL.create(
            "mysql+pymysql",
            username=self.mysql_user,
            password=self.mysql_password,
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_db,
            query={"charset": "utf8mb4"},
        )

    def mask_mysql(self) -> str:
        """给日志用的脱敏描述，不含密码。"""
        target = self.mysql_db or "(未指定库)"
        return f"{self.mysql_user}@{self.mysql_host}:{self.mysql_port}/{target}"

    # ------------------------------------------------------------- 校验
    def missing_required(self) -> list[str]:
        """启动前检查必填项，返回缺失的环境变量名。"""
        missing: list[str] = []
        if not self.mysql_uri_raw:
            if not self.mysql_db:
                missing.append("MYSQL_DB")
            if not self.mysql_user:
                missing.append("MYSQL_USER")
        provider = self.model.split(":", 1)[0].lower()
        if provider in {"volcengine", "volc", "ark", "doubao", "volces"}:
            provider = "volcengine"
        key_map = {
            "deepseek": ("DEEPSEEK_API_KEY", self.deepseek_api_key),
            "openai": ("OPENAI_API_KEY", self.openai_api_key),
            "anthropic": ("ANTHROPIC_API_KEY", self.anthropic_api_key),
            "volcengine": ("VOLC_API_KEY", self.volc_api_key),
        }
        if provider in key_map:
            name, value = key_map[provider]
            if not value:
                missing.append(name)
        return missing


settings = Settings.from_env()
