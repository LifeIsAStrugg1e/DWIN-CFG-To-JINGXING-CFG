"""Load generated JSON profiles and apply data-driven conversion rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Type


PROFILE_DIR = Path(__file__).resolve().parents[1] / "profiles" / "generated"


class ProfileError(ValueError):
    """Raised when generated profile data is missing or invalid."""


def _load_json(name: str) -> Any:
    path = PROFILE_DIR / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProfileError("缺少配置文件：{}，请先从 Excel 导出 JSON".format(path))
    except (OSError, ValueError) as error:
        raise ProfileError("无法读取配置文件 {}：{}".format(path, error))


def load_devices() -> Dict[str, Dict[str, Any]]:
    document = _load_json("devices.json")
    return {item["model"]: item for item in document["devices"]}


def load_targets() -> Dict[str, Dict[str, Any]]:
    document = _load_json("targets.json")
    return {item["system"]: item for item in document["targets"]}


def load_enums() -> Dict[str, Dict[int, int]]:
    document = _load_json("enums.json")
    return {
        name: {int(item["source"]): int(item["target"]) for item in rows}
        for name, rows in document["enums"].items()
    }


def detect_profile_model(data: bytes) -> Optional[str]:
    matches = []
    for model, profile in load_devices().items():
        if data.startswith(bytes.fromhex(profile["header_hex"])):
            matches.append(model)
    if len(matches) > 1:
        raise ProfileError("文件头匹配多个设备：{}".format(", ".join(matches)))
    return matches[0] if matches else None


def _read_unsigned(data: bytes, rule: Dict[str, Any]) -> int:
    offset = rule["offset"]
    size = rule.get("size", 1)
    return int.from_bytes(data[offset : offset + size], rule.get("byte_order", "big"))


def parse_with_profile(data: bytes, profile: Dict[str, Any], config_type: Type[Any]) -> Any:
    minimum_size = profile["minimum_size"]
    if len(data) < minimum_size:
        raise ProfileError(
            "{} 配置数据不完整：至少需要 {} 字节，实际 {} 字节".format(
                profile["display_name"], minimum_size, len(data)
            )
        )

    values = {
        "model": profile["model"],
        "model_name": profile["display_name"],
        "baudrate": 115200,
        "direction": 0,
        "crc_enable": False,
        "buzzer_enable": True,
        "tp_auto_upload": False,
        "tp_buzzer": True,
        "backlight_standby": False,
        "load_22": False,
        "var_per_page": 64,
        "brightness_on": 64,
        "brightness_off": 0,
        "backlight_time": 5,
        "bg_image_id": None,
        "audio_id": None,
        "tp_type": 1,
        "debug_enable": False,
        "tp_switch_enable": False,
        "raw_data": data,
    }

    for rule in sorted(profile["fields"], key=lambda item: item.get("priority", 100)):
        field_type = rule["type"]
        raw = _read_unsigned(data, rule)
        if raw in rule.get("skip_values", []):
            continue
        if field_type == "bit":
            result = bool((raw >> rule["bit"]) & 1)
            if rule.get("invert"):
                result = not result
            if result and "true_value" in rule:
                result = rule["true_value"]
            elif not result and "false_value" in rule:
                result = rule["false_value"]
            elif not result and rule.get("skip_false"):
                continue
        elif field_type == "bitfield":
            width = rule["bit_width"]
            result = (raw >> rule["bit"]) & ((1 << width) - 1)
        elif field_type == "divisor":
            if raw == 0:
                raise ProfileError("{} 的 {} 除数不能为 0".format(profile["model"], rule["field"]))
            result = rule["constant"] // raw
        elif field_type in ("uint", "direct_baud"):
            result = None if raw == 0 and rule.get("null_if_zero") else raw
        elif field_type == "constant":
            result = rule["constant"]
        else:
            raise ProfileError("不支持的源字段类型：{}".format(field_type))

        if result is not None and not isinstance(result, bool):
            result = result * rule.get("scale", 1) + rule.get("add", 0)
            if "divide" in rule:
                result //= rule["divide"]
            if "minimum_value" in rule:
                result = max(rule["minimum_value"], result)
        values[rule["field"]] = result

    return config_type(**values)


def _condition_matches(value: Any, mapping: Dict[str, Any]) -> bool:
    operation = mapping["operation"]
    if operation == "truthy":
        return bool(value)
    if operation == "falsy":
        return not bool(value)
    if operation == "equals":
        return value == mapping["compare_value"]
    if operation == "not_equals":
        return value != mapping["compare_value"]
    raise ProfileError("不支持的位映射操作：{}".format(operation))


def _transform_value(value: Any, rule: Dict[str, Any], enums: Dict[str, Dict[int, int]]) -> int:
    transform = rule["transform"]
    parameter = rule.get("parameter")
    if transform == "direct":
        result = int(value)
    elif transform == "enum":
        table = enums[parameter]
        if int(value) not in table:
            if parameter == "JGXING_BAUD":
                raise ProfileError("晶兴系统不支持波特率：{}".format(value))
            raise ProfileError("枚举 {} 不支持值 {}".format(parameter, value))
        result = table[int(value)]
    elif transform == "percent_to_63":
        result = int(value) * 0x3F // 100
    elif transform == "seconds":
        result = max(1, int(value))
    elif transform == "seconds_x2":
        result = max(1, int(value) * 2)
    elif transform == "touch_type":
        result = 0x7F if int(value) == 1 else 0xFF
    elif transform == "debug_switch":
        result = 0x7F if bool(value) else 0xFF
    else:
        raise ProfileError("不支持的寄存器转换：{}".format(transform))
    return min(0xFF, max(0, result))


def convert_with_target_profile(dwin: Any, system: str, config_type: Type[Any]) -> Any:
    targets = load_targets()
    if system not in targets:
        raise ProfileError("缺少目标系统规则：{}".format(system))
    target = targets[system]
    config = config_type()

    for register, value in target["defaults"].items():
        setattr(config, register, value)

    for mapping in sorted(target["bit_mappings"], key=lambda item: item.get("priority", 100)):
        value = getattr(dwin, mapping["source_field"])
        if _condition_matches(value, mapping):
            register = mapping["target_register"]
            current = getattr(config, register)
            setattr(config, register, current | (1 << mapping["target_bit"]))

    enums = load_enums()
    for rule in target["value_mappings"]:
        value = getattr(dwin, rule["source_field"])
        if value is None and rule["output_policy"] == "if_present":
            setattr(config, rule["target_register"], None)
            continue
        if not value and rule["output_policy"] == "if_nonzero":
            setattr(config, rule["target_register"], None)
            continue
        setattr(config, rule["target_register"], _transform_value(value, rule, enums))
    return config
