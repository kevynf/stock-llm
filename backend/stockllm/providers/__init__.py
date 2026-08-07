import os

from .base import ProviderUnavailable, ResearchProvider
from .demo import DemoProvider
from .live import AKShareProvider


def get_provider(mode: str) -> ResearchProvider:
    if mode == "live":
        return AKShareProvider()
    if mode == "demo" and os.getenv("STOCKLLM_ENABLE_DEMO") == "1":
        return DemoProvider()
    raise ProviderUnavailable("示例数据仅限开发测试，用户研究必须使用可核验数据源")


__all__ = [
    "AKShareProvider",
    "DemoProvider",
    "ProviderUnavailable",
    "ResearchProvider",
    "get_provider",
]
