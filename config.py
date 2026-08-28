"""
全局配置加载：app.env 为通用配置，{platform}.env 为平台专属配置
"""
from pathlib import Path

from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent
CONFIGS_DIR = BASE_DIR / "configs"
DATA_DIR = BASE_DIR / "data"
COMMANDS_DIR = DATA_DIR / "commands"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR = BASE_DIR / "logs"

PLATFORMS = ["qq", "dingtalk"]

# ── 默认值（可被 .env 覆盖） ──
DEFAULTS = {
    "WEB_HOST": "127.0.0.1",
    "WEB_PORT": "8001",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "change-me-please",
    "ADMIN_PASSWORD_SALT": "",
    "JWT_SECRET": "change-me-to-a-long-random-secret",
    "AI_API_KEY": "",
    "AI_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "AI_MODEL": "deepseek-v4-flash-0731",
    "AI_MODEL_VISION": "qwen-vl-plus",   # 图片识别（阿里云百炼视觉模型）
    "AI_ENABLE_THINKING": "true",
    # 安全配置
    "REGISTER_OPEN": "true",          # 是否开放注册（公网部署建议 false 或启用邀请码）
    "REGISTER_INVITE_CODE": "",       # 邀请码（非空则注册必须填写）
    "COOKIE_SECURE": "false",         # HTTPS 部署时设为 true
    "REPORT_HOUR": "18",
    "REPORT_MINUTE": "0",
    "POLL_INTERVAL": "90",
    "COMMAND_INTERVAL": "3",
    "SERVERCHAN_KEY": "",
    "QQ_ENABLED": "false",
    "DINGTALK_ENABLED": "false",
}


def _read_env(filename: str) -> dict:
    """读取 configs 目录下的 .env 文件（不存在则返回空）"""
    path = CONFIGS_DIR / filename
    if path.exists():
        values = {k: v for k, v in dotenv_values(path).items() if v is not None}
        return {k: v.strip() for k, v in values.items()}
    return {}


def load_env(filename: str) -> dict:
    """读取 .env 并合并默认值（平台配置同时继承 app.env）"""
    merged = dict(DEFAULTS)
    if filename != "app.env":
        merged.update(_read_env("app.env"))
    merged.update(_read_env(filename))
    return merged


def get_platform_config(platform: str) -> dict:
    """读取某平台的完整配置（app.env + {platform}.env）"""
    if platform not in PLATFORMS:
        raise ValueError(f"未知平台: {platform}")
    return load_env(f"{platform}.env")


def get_app_config() -> dict:
    """读取通用配置（含管理后台/AI/调度）"""
    return load_env("app.env")


def ensure_dirs() -> None:
    """确保数据目录存在"""
    for d in (DATA_DIR, COMMANDS_DIR, REPORTS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def platform_db_path(platform: str) -> Path:
    return DATA_DIR / f"{platform}.db"


def platform_report_dir(platform: str) -> Path:
    return REPORTS_DIR / platform


# ── 多租户：每用户独立数据空间 ──
def user_data_dir(username: str) -> Path:
    """某用户的数据根目录：data/users/{username}/"""
    return DATA_DIR / "users" / username


def user_platform_db_path(username: str, platform: str) -> Path:
    """某用户某平台的消息库"""
    return user_data_dir(username) / f"{platform}.db"


def user_report_dir(username: str, platform: str) -> Path:
    """某用户某平台的报告目录"""
    return user_data_dir(username) / "reports" / platform


def user_media_dir(username: str, platform: str) -> Path:
    """某用户某平台的媒体目录"""
    return user_data_dir(username) / "media" / platform


def ensure_user_dirs(username: str) -> None:
    """确保用户数据目录存在"""
    root = user_data_dir(username)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "media").mkdir(parents=True, exist_ok=True)
    for p in PLATFORMS:
        (root / "reports" / p).mkdir(parents=True, exist_ok=True)
        (root / "media" / p).mkdir(parents=True, exist_ok=True)
