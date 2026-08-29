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

# ── 平台注册表（单一事实来源：新增平台 = 这里加一行 + platforms/ 加适配器） ──
PLATFORM_META = {
    "qq": {
        "display_name": "QQ",
        "enabled_key": "QQ_ENABLED",
        "app_id_key": "QQ_APP_ID",
        "groups_key": "QQ_GROUP_OPENIDS",
        "keys": ["QQ_APP_ID", "QQ_APP_SECRET", "QQ_ENV", "QQ_GROUP_OPENIDS", "QQ_ENABLED"],
        "secret_keys": ["QQ_APP_SECRET"],
        "adapter": "platforms.qq:QQAdapter",
        "test": {
            "method": "POST",
            "url": "https://bots.qq.com/app/getAppAccessToken",
            "body": lambda c: {"appId": c.get("QQ_APP_ID", ""),
                               "clientSecret": c.get("QQ_APP_SECRET", "")},
            "ok_field": "access_token",
        },
    },
    "dingtalk": {
        "display_name": "钉钉",
        "enabled_key": "DINGTALK_ENABLED",
        "app_id_key": "DINGTALK_APP_KEY",
        "groups_key": "DINGTALK_CHAT_IDS",
        "keys": ["DINGTALK_APP_KEY", "DINGTALK_APP_SECRET", "DINGTALK_CHAT_IDS", "DINGTALK_ENABLED"],
        "secret_keys": ["DINGTALK_APP_SECRET"],
        "adapter": "platforms.dingtalk:DingTalkAdapter",
        "test": {
            "method": "POST",
            "url": "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            "body": lambda c: {"appKey": c.get("DINGTALK_APP_KEY", ""),
                               "appSecret": c.get("DINGTALK_APP_SECRET", "")},
            "ok_field": "accessToken",
        },
    },
    "feishu": {
        "display_name": "飞书",
        "enabled_key": "FEISHU_ENABLED",
        "app_id_key": "FEISHU_APP_ID",
        "groups_key": "FEISHU_CHAT_IDS",
        "keys": ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_CHAT_IDS", "FEISHU_ENABLED"],
        "secret_keys": ["FEISHU_APP_SECRET"],
        "adapter": "platforms.feishu:FeishuAdapter",
        "test": {
            "method": "POST",
            "url": "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            "body": lambda c: {"app_id": c.get("FEISHU_APP_ID", ""),
                               "app_secret": c.get("FEISHU_APP_SECRET", "")},
            "ok_field": "tenant_access_token",
        },
    },
    "workwechat": {
        "display_name": "企业微信",
        "enabled_key": "WORKWECHAT_ENABLED",
        "app_id_key": "WORKWECHAT_CORP_ID",
        "groups_key": "WORKWECHAT_CHAT_IDS",
        "keys": ["WORKWECHAT_CORP_ID", "WORKWECHAT_AGENT_ID", "WORKWECHAT_SECRET",
                 "WORKWECHAT_TOKEN", "WORKWECHAT_AES_KEY", "WORKWECHAT_CHAT_IDS",
                 "WORKWECHAT_ENABLED"],
        "secret_keys": ["WORKWECHAT_SECRET", "WORKWECHAT_TOKEN", "WORKWECHAT_AES_KEY"],
        "adapter": "platforms.workwechat:WorkWechatAdapter",
        "test": {
            "method": "GET",
            "url": "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            "params": lambda c: {"corpid": c.get("WORKWECHAT_CORP_ID", ""),
                                 "corpsecret": c.get("WORKWECHAT_SECRET", "")},
            "ok_field": "access_token",
        },
    },
}
PLATFORMS = list(PLATFORM_META)

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
    "FEISHU_ENABLED": "false",
    "WORKWECHAT_ENABLED": "false",
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
