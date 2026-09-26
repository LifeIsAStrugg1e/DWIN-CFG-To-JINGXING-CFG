"""Small local web UI for CFG conversion and rule inspection."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
from dataclasses import asdict, fields
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

from lib.converter import (
    ConfigError,
    JgxingConfig,
    convert_to_jgxing,
    generate_config_txt,
    parse_dwin_config,
    resolve_system,
)
from lib.profile_engine import load_devices, load_targets


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
MAX_UPLOAD_SIZE = 2 * 1024 * 1024

LEGACY_SOURCE_RULES: Dict[str, List[Dict[str, Any]]] = {
    "AIOT_LCM_TA": [
        {"field": "crc_enable", "offset": 5, "size": 1, "bit": 7, "type": "bit"},
        {"field": "tp_switch_enable", "offset": 5, "size": 1, "bit": 6, "type": "bit"},
        {"field": "direction", "offset": 5, "size": 1, "bit": 0, "width": 2, "type": "bitfield", "scale": 90},
        {"field": "baudrate", "offset": 12, "size": 3, "type": "direct_baud"},
        {"field": "brightness_on", "offset": 15, "size": 1, "type": "uint", "transform": "raw * 100 / 64"},
        {"field": "tp_type", "offset": 33, "size": 1, "type": "nibble", "transform": "0/F=电阻，其余=电容"},
    ],
    "T5UIC3": [
        {"field": "tp_auto_upload", "offset": 8, "size": 1, "bit": 7, "type": "bit"},
        {"field": "var_per_page", "offset": 8, "size": 1, "bit": 6, "type": "bit", "true_value": 128, "false_value": 64},
        {"field": "load_22", "offset": 8, "size": 1, "bit": 5, "type": "bit"},
        {"field": "tp_buzzer", "offset": 8, "size": 1, "bit": 3, "type": "bit"},
        {"field": "backlight_standby", "offset": 8, "size": 1, "bit": 2, "type": "bit"},
        {"field": "direction", "offset": 8, "size": 1, "bit": 0, "width": 2, "type": "bitfield", "scale": 90},
        {"field": "baudrate", "offset": 9, "size": 2, "type": "divisor", "constant": 7833600},
        {"field": "brightness_on", "offset": 12, "size": 1, "type": "uint"},
        {"field": "brightness_off", "offset": 13, "size": 1, "type": "uint"},
        {"field": "backlight_time", "offset": 14, "size": 2, "type": "uint", "transform": "raw / 2"},
    ],
}

FIELD_LABELS = {
    "baudrate": "波特率", "direction": "显示方向", "crc_enable": "CRC 校验",
    "buzzer_enable": "蜂鸣器", "tp_auto_upload": "触摸自动上传", "tp_buzzer": "触摸伴音",
    "backlight_standby": "背光待机", "load_22": "加载 22 文件", "var_per_page": "每页变量数",
    "brightness_on": "点亮亮度", "brightness_off": "待机亮度", "backlight_time": "背光时间",
    "bg_image_id": "背景图 ID", "audio_id": "音频 ID", "tp_type": "触摸类型",
    "debug_enable": "调试开关", "tp_switch_enable": "触控开关", "上电清屏": "上电清屏",
    "主频": "主频", "上电SD接口状态": "上电 SD 接口状态", "backlight_EN": "背光使能",
}
JGUS_REGISTER_LABELS = {
    "R1": "波特率", "R2": "系统配置", "R3": "帧头/显示模式", "RA": "帧头低字节",
    "RC": "扩展系统配置", "R6": "点亮亮度", "R7": "待机亮度", "R8": "背光时间",
    "R10": "背景图", "R11": "音频", "R12": "系统版本", "RD": "触摸类型", "RE": "调试开关",
}
INSTRUCTION_REGISTER_LABELS = {
    "R0": "液晶屏索引参数", "R1": "波特率索引", "R2": "触摸屏工作模式", "R3": "显示工作模式",
    "R6": "触摸后背光亮度", "R7": "待机背光亮度", "R8": "背光点亮时间", "R9": "格式化操作",
    "R10": "背景图片字库 ID", "R11": "音频文件字库 ID", "R12": "图片格式/软件版本",
    "RD": "硬件环境配置", "RE": "调试信息",
}


def _register_label(system: str, register: str) -> str:
    labels = INSTRUCTION_REGISTER_LABELS if system == "INSTRUCTION" else JGUS_REGISTER_LABELS
    return labels.get(register, register)


def _profile_rules(model: str) -> List[Dict[str, Any]]:
    for profile in load_devices().values():
        if profile["model"] == model:
            return profile["fields"]
    return LEGACY_SOURCE_RULES.get(model, [])


def _model_from_bytes(data: bytes, source_model: Optional[str]) -> str:
    if data.startswith(b"T5LC1"):
        return source_model or "T5L_AMBIGUOUS"
    if data.startswith(b"T5C1"): return "T5UIC1"
    if data.startswith(b"T5C2"): return "T5UIC2"
    if data.startswith(b"T5C3"): return "T5UIC3"
    if data.startswith(b"T5C4"): return "T5UIC4"
    if data.startswith(b"T5D1"): return "T5UID1"
    if data.startswith(b"T5D2"): return "T5UID2"
    if data.startswith(b"T5D3"): return "T5UID3"
    if data.startswith(b"AIoT1"): return "AIOT_LCM_TA"
    return "UNKNOWN"


def _raw_hex(data: bytes, offset: int, size: int) -> str:
    return " ".join("{:02X}".format(value) for value in data[offset : offset + size])


def _field_value(dwin: Any, rule: Dict[str, Any]) -> Any:
    value = getattr(dwin, rule["field"], None)
    if isinstance(value, bool):
        return "开启" if value else "关闭"
    if value is None:
        return "未设置"
    if rule.get("field") == "direction":
        return "{}°".format(value)
    if rule.get("field") == "baudrate":
        return "{} bps".format(value)
    return value


def _source_rows(data: bytes, model: str, dwin: Any) -> List[Dict[str, Any]]:
    rows = []
    for rule in _profile_rules(model):
        offset = rule.get("offset")
        size = rule.get("size", 1)
        if offset is None or offset + size > len(data):
            continue
        rows.append({
            "field": rule["field"],
            "label": FIELD_LABELS.get(rule["field"], rule["field"]),
            "offset": "0x{:02X}".format(offset),
            "offsetValue": offset,
            "size": size,
            "raw": _raw_hex(data, offset, size),
            "bit": rule.get("bit"),
            "width": rule.get("width") or rule.get("bit_width"),
            "type": rule.get("type", "field"),
            "transform": rule.get("transform"),
            "value": _field_value(dwin, rule),
        })
    return rows


def _rule_text(mapping: Dict[str, Any]) -> str:
    operation = mapping["operation"]
    if operation in ("equals", "not_equals"):
        symbol = "=" if operation == "equals" else "≠"
        return "{} {} {}".format(FIELD_LABELS.get(mapping["source_field"], mapping["source_field"]), symbol, mapping.get("compare_value"))
    return "{} {}".format(FIELD_LABELS.get(mapping["source_field"], mapping["source_field"]), "非零" if operation == "truthy" else "为零")


def _mapping_rows(dwin: Any, system: str, result: JgxingConfig) -> List[Dict[str, Any]]:
    target = load_targets()[system]
    rows = []
    for mapping in target["bit_mappings"]:
        source_field = mapping["source_field"]
        value = getattr(dwin, source_field, None)
        active = False
        if mapping["operation"] == "truthy": active = bool(value)
        elif mapping["operation"] == "falsy": active = not bool(value)
        elif mapping["operation"] == "equals": active = value == mapping.get("compare_value")
        elif mapping["operation"] == "not_equals": active = value != mapping.get("compare_value")
        register = mapping["target_register"]
        register_value = getattr(result, register, 0)
        rows.append({
            "source": FIELD_LABELS.get(source_field, source_field),
            "sourceField": source_field,
            "sourceValue": "开启" if value is True else ("关闭" if value is False else value),
            "rule": _rule_text(mapping),
            "target": register,
            "targetLabel": _register_label(system, register),
            "bit": mapping["target_bit"],
            "active": active,
            "result": "1" if (register_value & (1 << mapping["target_bit"])) else "0",
        })
    for mapping in target["value_mappings"]:
        source_field = mapping["source_field"]
        value = getattr(dwin, source_field, None)
        target_value = getattr(result, mapping["target_register"], None)
        rows.append({
            "source": FIELD_LABELS.get(source_field, source_field),
            "sourceField": source_field,
            "sourceValue": value,
            "rule": mapping["transform"],
            "target": mapping["target_register"],
            "targetLabel": _register_label(system, mapping["target_register"]),
            "bit": None,
            "active": target_value is not None,
            "result": "{:02X}".format(target_value) if target_value is not None else "—",
        })
    return rows


def build_conversion_payload(data: bytes, source_model: Optional[str] = None, system: str = "AUTO") -> Dict[str, Any]:
    model = _model_from_bytes(data, source_model)
    dwin = parse_dwin_config(data, model_hint=source_model)
    target_system = resolve_system(dwin.model, system)
    result = convert_to_jgxing(dwin, target_system)
    text = generate_config_txt(result, target_system)
    registers = []
    for line in text.strip().splitlines():
        match = re.match(r"^([A-Z0-9]+)=([0-9A-F]{2})", line)
        if not match:
            continue
        name, value = match.groups()
        registers.append({
            "name": name,
            "label": _register_label(target_system, name),
            "value": value,
            "number": int(value, 16),
            "bits": ["1" if int(value, 16) & (1 << bit) else "0" for bit in range(7, -1, -1)],
        })
    return {
        "model": dwin.model,
        "modelName": dwin.model_name,
        "targetSystem": target_system,
        "inputSize": len(data),
        "header": _raw_hex(data, 0, min(5, len(data))),
        "config": {key: value for key, value in asdict(dwin).items() if key != "raw_data"},
        "bytes": [{"offset": offset, "hex": _raw_hex(data, offset, min(16, len(data) - offset))} for offset in range(0, len(data), 16)],
        "sourceFields": _source_rows(data, model, dwin),
        "mappings": _mapping_rows(dwin, target_system, result),
        "registers": registers,
        "text": text,
    }


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def _json(self, status: int, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/meta":
            devices = load_devices()
            self._json(HTTPStatus.OK, {
                "systems": ["AUTO", "JGUS", "JGUSII", "INSTRUCTION"],
                "sourceModels": ["AUTO", "T5L_DGUSII", "T5L_TA"],
                "profiles": [
                    {"model": model, "name": profile["display_name"], "defaultSystem": profile["default_system"], "verified": True}
                    for model, profile in devices.items()
                ],
            })
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/convert":
            self._json(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_UPLOAD_SIZE:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "文件为空或超过 2 MB"})
            return
        data = self.rfile.read(length)
        query = parse_qs(parsed.query)
        source_model = query.get("source_model", [None])[0] or None
        system = query.get("system", ["AUTO"])[0]
        try:
            self._json(HTTPStatus.OK, {"ok": True, "result": build_conversion_payload(data, source_model, system)})
        except (ConfigError, OSError, ValueError) as error:
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"ok": False, "error": str(error)})

    def log_message(self, format: str, *args: Any) -> None:
        print("[web] " + format % args)


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), AppHandler)
    print("CFG Studio running at http://{}:{}/".format(host, port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="CFG Studio 本地可视化转换工具")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    run_server(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
