"""独立的迪文 CFG 到晶兴 CONFIG.txt 转换库。"""

from .converter import (
    AmbiguousModelError,
    ConfigError,
    DwinConfig,
    JgxingConfig,
    UnknownModelError,
    UnsupportedModelError,
    convert_to_jgxing,
    detect_model,
    generate_config_txt,
    parse_dwin_config,
    resolve_system,
)

__all__ = [
    "AmbiguousModelError",
    "ConfigError",
    "DwinConfig",
    "JgxingConfig",
    "UnknownModelError",
    "UnsupportedModelError",
    "convert_to_jgxing",
    "detect_model",
    "generate_config_txt",
    "parse_dwin_config",
    "resolve_system",
]
