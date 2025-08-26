from pydantic import Field
from typing import Dict, ClassVar, List
from .i18n import I18nMixin, Description


class BiliBiliLiveConfig(I18nMixin):
    """Configuration for BiliBili Live platform."""

    room_ids: List[int] = Field([], alias="room_ids")
    sessdata: str = Field("", alias="sessdata")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "room_ids": Description(
            en="List of BiliBili live room IDs to monitor", zh="要监控的B站直播间ID列表"
        ),
        "sessdata": Description(
            en="SESSDATA cookie value for authenticated requests (optional)",
            zh="用于认证请求的SESSDATA cookie值（可选）",
        ),
    }


class TwitchLiveConfig(I18nMixin):
    """Configuration for Twitch Live platform."""

    channel: str = Field("", alias="channel")
    oauth_token: str = Field("", alias="oauth_token")
    username: str = Field("", alias="username")

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "channel": Description(
            en="Twitch channel name to monitor (without #)", zh="要监控的Twitch频道名称（不含#）"
        ),
        "oauth_token": Description(
            en="OAuth token for Twitch authentication (optional for read-only)",
            zh="用于Twitch认证的OAuth令牌（只读模式可选）",
        ),
        "username": Description(
            en="Bot username for Twitch (optional, defaults to anonymous)",
            zh="Twitch机器人用户名（可选，默认匿名）",
        ),
    }


class LiveConfig(I18nMixin):
    """Configuration for live streaming platforms integration."""

    bilibili_live: BiliBiliLiveConfig = Field(
        BiliBiliLiveConfig(), alias="bilibili_live"
    )
    twitch_live: TwitchLiveConfig = Field(
        TwitchLiveConfig(), alias="twitch_live"
    )

    DESCRIPTIONS: ClassVar[Dict[str, Description]] = {
        "bilibili_live": Description(
            en="Configuration for BiliBili Live platform", zh="B站直播平台配置"
        ),
        "twitch_live": Description(
            en="Configuration for Twitch Live platform", zh="Twitch直播平台配置"
        ),
    }
