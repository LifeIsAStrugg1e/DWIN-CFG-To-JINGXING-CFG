#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迪文 CFG 到晶兴 CONFIG.txt 的纯转换核心。

本模块只处理 bytes 和配置对象，不读写文件、不启动界面，也不依赖第三方库。

支持型号:
- T5L DGUSII (T5LC1)
- T5L TA (T5LC1 without 14ShowFile.bin)
- T5UIC1 (T5C1)
- T5UIC2 (T5C2)
- T5UIC3 (T5C3)
- T5UIC4 (T5C4)
- T5UID1 (T5D1)
- T5UID2 (T5D2)
- T5UID3 (T5D3)
- AIOT_LCM_TA (AIoT1)
"""

import struct
from dataclasses import dataclass
from typing import Optional

try:
    from .profile_engine import (
        ProfileError,
        convert_with_target_profile,
        detect_profile_model,
        load_devices,
        parse_with_profile,
    )
except ImportError:  # Support running converter.py directly during development.
    from profile_engine import (
        ProfileError,
        convert_with_target_profile,
        detect_profile_model,
        load_devices,
        parse_with_profile,
    )


# 波特率计算常量
DWIN_T5U_BAUD_CONST = 7833600      # T5UIC/UID 系列
DWIN_T5U_BAUD_CONST2 = 3225600     # 部分型号

# 晶兴波特率映射 (R1 值)
JGXING_BAUD_MAP = {
    1200: 0x00, 2400: 0x01, 4800: 0x02, 9600: 0x03,
    19200: 0x04, 38400: 0x05, 57600: 0x06, 115200: 0x07,
    230400: 0x08, 250000: 0x09, 460800: 0x0A, 500000: 0x0B,
    921600: 0x0C, 1000000: 0x0D, 1500000: 0x0E, 2000000: 0x0F,
    3000000: 0x10, 4000000: 0x11, 4500000: 0x12,
}

SYSTEMS = ("JGUS", "JGUSII", "INSTRUCTION")
MODEL_SYSTEMS = {
    "T5UIC2": "INSTRUCTION",
    "T5UIC3": "JGUS",
    "T5UID3": "JGUSII",
    "AIOT_LCM_TA": "INSTRUCTION",
}


class ConfigError(ValueError):
    """Base exception for invalid or unsupported CFG data."""


class UnknownModelError(ConfigError):
    """Raised when a CFG header is not recognized."""


class UnsupportedModelError(ConfigError):
    """Raised when a known header has no verified parser yet."""


class AmbiguousModelError(ConfigError):
    """Raised when a source model cannot be inferred from CFG bytes alone."""


@dataclass
class DwinConfig:
    """迪文配置解析结果"""
    model: str           # 型号标识
    model_name: str      # 型号名称
    baudrate: int        # 波特率
    direction: int       # 显示方向 0/90/180/270
    crc_enable: bool     # CRC 校验
    buzzer_enable: bool  # 蜂鸣器
    tp_auto_upload: bool # 触摸自动上传
    tp_buzzer: bool      # 触摸伴音
    backlight_standby: bool  # 背光待机
    load_22: bool        # 加载 22 文件
    var_per_page: int    # 每页变量数 64/128
    brightness_on: int   # 点亮亮度 (0-100)
    brightness_off: int  # 待机亮度 (0-100)
    backlight_time: int  # 背光时间 (秒)
    bg_image_id: Optional[int]  # 背景图 ID；源格式无此字段时为 None
    audio_id: Optional[int]     # 音频 ID；源格式无此字段时为 None
    tp_type: int         # 触摸类型 0=电阻 1=电容
    debug_enable: bool   # 调试开关
    tp_switch_enable: bool  # 触控开关 0=关闭 (0x72/0x73) 1=开启 (0x78/0x79)
    raw_data: bytes      # 原始数据


@dataclass
class JgxingConfig:
    """晶兴配置生成结果"""
    R1: int = 0x07       # 波特率
    R2: int = 0x0C       # 系统配置/触摸模式
    R3: int = 0x5A       # 帧头高/显示模式
    RA: int = 0xA5       # 帧头低
    RC: Optional[int] = None  # 扩展系统配置
    R6: int = 0x40       # 点亮亮度
    R7: int = 0x40       # 待机亮度
    R8: int = 0x05       # 背光时间
    R10: Optional[int] = None  # 背景图 ID
    R11: Optional[int] = None  # 音频 ID
    R12: int = 0x03      # 图片格式 + 系统版本
    RD: int = 0x7F       # 触摸类型 (7F=电容，FF=电阻)
    RE: int = 0xFF       # 调试开关
    RB: int = 0x00       # 格式化标志
    tp_correct: bool = True  # TP_CORRECT


def calculate_baudrate_register(baudrate: int, const: int) -> int:
    """计算迪文波特率寄存器值"""
    return const // baudrate


def get_baudrate_from_register(reg_value: int, const: int) -> int:
    """从寄存器值反推波特率"""
    if reg_value == 0:
        return 0
    return const // reg_value


def get_jgxing_R1(baudrate: int) -> int:
    """精确获取晶兴 R1 波特率值，不静默替换为相邻波特率。"""
    try:
        return JGXING_BAUD_MAP[baudrate]
    except KeyError:
        raise ConfigError("晶兴系统不支持波特率：{}".format(baudrate))


def _require_size(data: bytes, size: int, model: str) -> None:
    if len(data) < size:
        raise ConfigError(
            "{} 配置数据不完整：至少需要 {} 字节，实际 {} 字节".format(
                model, size, len(data)
            )
        )


def resolve_system(model: str, requested: str = "AUTO") -> str:
    """Resolve the target system without coupling this rule to the CLI."""
    if requested != "AUTO":
        if requested not in SYSTEMS:
            raise ConfigError("不支持的目标系统：{}".format(requested))
        return requested
    try:
        profile = load_devices().get(model)
        if profile is not None:
            return profile["default_system"]
    except ProfileError as error:
        raise ConfigError(str(error))
    try:
        return MODEL_SYSTEMS[model]
    except KeyError:
        raise UnsupportedModelError("型号 {} 没有默认目标系统".format(model))


def parse_aiot_lcm_ta(data: bytes) -> DwinConfig:
    """解析 AIOT_LCM_TA 配置 (AIoT1)
    
    AIoT1 格式说明 (根据官方文档):
    - 地址 0x00-0x04: 配置识别 "AIoT1"
    - 地址 0x05: 参数配置 (CRC/触控开关/方向等)
    - 地址 0x07-0x08: NAND FLASH 格式化标志 (0x5AA5)
    - 地址 0x09: 触摸屏报点率
    - 地址 0x0C-0x0E: 串口波特率设置值 (3 字节，大端序)，单位 bps
    - 地址 0x0F: 开机背光亮度 (0x00-0x40)
    - 地址 0x10-0x1F: 显示屏配置
    - 地址 0x21-0x23: 触摸屏配置
    """
    config = DwinConfig(
        model="AIOT_LCM_TA",
        model_name="AIOT LCM TA",
        baudrate=115200,  # 默认值
        direction=0,
        crc_enable=False,
        buzzer_enable=True,
        tp_auto_upload=False,
        tp_buzzer=True,
        backlight_standby=False,
        load_22=False,
        var_per_page=64,
        brightness_on=64,
        brightness_off=0,
        backlight_time=5,
        bg_image_id=None,
        audio_id=None,
        tp_type=1,
        debug_enable=False,
        tp_switch_enable=False,  # 触控开关默认关闭
        raw_data=data
    )
    
    _require_size(data, 0x10, config.model_name)
    
    # 地址 0x05: 参数配置
    if len(data) >= 0x06:
        sys_config = data[0x05]
        config.crc_enable = bool(sys_config & 0x80)  # bit7: CRC 校验
        config.tp_switch_enable = bool(sys_config & 0x40)  # bit6: 触控开关 0=关闭 (0x72/0x73) 1=开启 (0x78/0x79)
        # bit5: 按压中是否上传 0=上传 1=不上传
        # bit4: 背景色恢复 1=自动恢复 0=不恢复
        # bit3: 触摸模式 0=上传 73/79 指令 1=不上传
        # bit1-0: 显示方向 00=0° 01=90° 10=180° 11=270°
        config.direction = (sys_config & 0x03) * 90
    
    # 地址 0x09: 触摸屏报点率 (报点率 = 400Hz / 设置值)
    if len(data) >= 0x0A:
        tp_rate = data[0x09]
        if tp_rate > 0:
            pass  # 报点率 = 400 / tp_rate
    
    # 地址 0x0C-0x0E: 波特率 (3 字节，大端序)
    # 直接存储波特率值，不是除数
    # 例如：115200 = 0x01C200
    if len(data) >= 0x0F:
        baud_value = struct.unpack('>I', b'\x00' + data[0x0C:0x0F])[0]
        if baud_value >= 5400 and baud_value <= 11059200:
            config.baudrate = baud_value
    
    # 地址 0x0F: 开机背光亮度 (0x00-0x40，即 0-64)
    if len(data) >= 0x10:
        brightness = data[0x0F]
        # 转换为 0-100 范围
        config.brightness_on = min(100, brightness * 100 // 64)
    
    # 地址 0x21-0x22: 触摸屏配置
    if len(data) >= 0x23:
        tp_mode = data[0x21]
        tp_type_bits = (tp_mode >> 4) & 0x0F
        # 0x0*=4 线电阻，0x1*=电容，0x2*=Incell，0x9*=TPS04，0xF*=5 线电阻
        if tp_type_bits in [0x00, 0x0F]:
            config.tp_type = 0  # 电阻屏
        else:
            config.tp_type = 1  # 电容屏
        
        tp_sense = data[0x22]  # 灵敏度 0-31
    
    return config


def parse_t5uic2(data: bytes) -> DwinConfig:
    """解析 T5UIC2 配置 (T5C2)"""
    config = DwinConfig(
        model="T5UIC2",
        model_name="T5UIC2",
        baudrate=115200,
        direction=0,
        crc_enable=False,
        buzzer_enable=True,
        tp_auto_upload=False,
        tp_buzzer=True,
        backlight_standby=False,
        load_22=False,
        var_per_page=64,
        brightness_on=64,
        brightness_off=0,
        backlight_time=5,
        bg_image_id=None,
        audio_id=None,
        tp_type=1,
        debug_enable=False,
        tp_switch_enable=False,
        raw_data=data
    )
    
    _require_size(data, 0x10, config.model_name)
    
    # 地址 0x08: System_Config
    sys_config = data[0x08]
    # bit7: 背光亮度控制
    # bit6: 显示方向 0=不偏转 1=偏转 90°
    # bit5: 触控开关
    # bit4: 背景色恢复
    # bit3: 触摸模式
    config.direction = 90 if (sys_config & 0x40) else 0
    
    # 地址 0x09: 波特率 (2 字节，大端序)
    if len(data) >= 0x0B:
        baud_reg = struct.unpack('>H', data[0x09:0x0B])[0]
        if baud_reg > 0:
            config.baudrate = get_baudrate_from_register(baud_reg, DWIN_T5U_BAUD_CONST)
    
    # 地址 0x21: System1_Config
    if len(data) >= 0x22:
        sys_config1 = data[0x21]
        # bit4: 伴音 0=开启 1=关闭
        config.tp_buzzer = not bool(sys_config1 & 0x10)
        # bit5: 持续按压上传
        # bit6: 显示翻转 180°
        if sys_config1 & 0x40:
            config.direction = 180
    
    return config


def parse_t5uic3(data: bytes) -> DwinConfig:
    """解析 T5UIC3 配置 (T5C3) - DGUS 模式"""
    config = DwinConfig(
        model="T5UIC3",
        model_name="T5UIC3",
        baudrate=115200,
        direction=0,
        crc_enable=False,
        buzzer_enable=True,
        tp_auto_upload=False,
        tp_buzzer=True,
        backlight_standby=False,
        load_22=False,
        var_per_page=64,
        brightness_on=64,
        brightness_off=0,
        backlight_time=5,
        bg_image_id=None,
        audio_id=None,
        tp_type=1,
        debug_enable=False,
        tp_switch_enable=False,
        raw_data=data
    )
    
    _require_size(data, 0x10, config.model_name)
    
    # 地址 0x08: System_Config
    if len(data) >= 0x09:
        sys_config = data[0x08]
        config.tp_auto_upload = bool(sys_config & 0x80)  # bit7: 自动上传
        config.var_per_page = 128 if (sys_config & 0x40) else 64  # bit6: 页变量数
        config.load_22 = bool(sys_config & 0x20)  # bit5: 加载 22 文件
        config.tp_buzzer = bool(sys_config & 0x08)  # bit3: 触摸伴音
        config.backlight_standby = bool(sys_config & 0x04)  # bit2: 背光待机
        config.direction = (sys_config & 0x03) * 90  # bit1-0: 显示方向
    
    # 地址 0x09: 波特率 (2 字节，大端序)
    if len(data) >= 0x0B:
        baud_reg = struct.unpack('>H', data[0x09:0x0B])[0]
        if baud_reg > 0:
            config.baudrate = get_baudrate_from_register(baud_reg, DWIN_T5U_BAUD_CONST)
    
    # 地址 0x0C-0x0F: 背光配置 (亮度/待机亮度/时间)
    if len(data) >= 0x10:
        config.brightness_on = data[0x0C]
        config.brightness_off = data[0x0D]
        # 0x0E-0x0F: 点亮时间 (单位 0.5s)
        time_val = struct.unpack('>H', data[0x0E:0x10])[0]
        config.backlight_time = max(1, time_val // 2)  # 转换为秒
    
    return config


def parse_t5uid3(data: bytes) -> DwinConfig:
    """解析 T5UID3 配置 (T5D3)"""
    config = DwinConfig(
        model="T5UID3",
        model_name="T5UID3",
        baudrate=115200,
        direction=0,
        crc_enable=False,
        buzzer_enable=True,
        tp_auto_upload=True,
        tp_buzzer=True,
        backlight_standby=False,
        load_22=False,
        var_per_page=64,
        brightness_on=64,
        brightness_off=0,
        backlight_time=5,
        bg_image_id=None,
        audio_id=None,
        tp_type=1,
        debug_enable=False,
        tp_switch_enable=False,
        raw_data=data
    )
    
    _require_size(data, 0x10, config.model_name)
    
    # 地址 0x08: System_Config
    sys_config = data[0x08]
    config.tp_auto_upload = bool(sys_config & 0x80)
    config.var_per_page = 128 if (sys_config & 0x40) else 64
    config.load_22 = bool(sys_config & 0x20)
    config.tp_buzzer = bool(sys_config & 0x08)
    config.backlight_standby = bool(sys_config & 0x04)
    config.direction = (sys_config & 0x03) * 90
    
    # 地址 0x09: 波特率 (2 字节，大端序)
    if len(data) >= 0x0B:
        baud_reg = struct.unpack('>H', data[0x09:0x0B])[0]
        if baud_reg > 0:
            config.baudrate = get_baudrate_from_register(baud_reg, DWIN_T5U_BAUD_CONST)
    
    return config


def detect_model(data: bytes) -> str:
    """检测配置文件型号"""
    try:
        profile_model = detect_profile_model(data)
    except ProfileError as error:
        if data.startswith(b"T5LC1"):
            return "T5L_AMBIGUOUS"
        raise ConfigError(str(error))
    if profile_model is not None:
        return profile_model
    if len(data) < 4:
        return "UNKNOWN"
    
    # 检查文件头
    header = data[:5]
    
    # T5L DGUSII / T5L TA: 0x54 0x35 0x4C 0x43 0x31 ("T5LC1")
    # 两者文件头相同，存在歧义，返回特殊标识
    if header[:5] == b'T5LC1':
        return "T5L_AMBIGUOUS"
    
    # T5UIC1: 0x54 0x35 0x43 0x31 ("T5C1")
    if header[:4] == b'T5C1':
        return "T5UIC1"
    
    # T5UIC2: 0x54 0x35 0x43 0x32 ("T5C2")
    if header[:4] == b'T5C2':
        return "T5UIC2"
    
    # T5UIC3: 0x54 0x35 0x43 0x33 ("T5C3")
    if header[:4] == b'T5C3':
        return "T5UIC3"
    
    # T5UIC4: 0x54 0x35 0x43 0x34 ("T5C4")
    if header[:4] == b'T5C4':
        return "T5UIC4"
    
    # T5UID1: 0x54 0x35 0x44 0x31 ("T5D1")
    if header[:4] == b'T5D1':
        return "T5UID1"
    
    # T5UID2: 0x54 0x35 0x44 0x32 ("T5D2")
    if header[:4] == b'T5D2':
        return "T5UID2"
    
    # T5UID3: 0x54 0x35 0x44 0x33 ("T5D3")
    if header[:4] == b'T5D3':
        return "T5UID3"
    
    # AIOT_LCM_TA: 0x41 0x49 0x6F 0x54 0x31 ("AIoT1")
    if header[:5] == b'AIoT1':
        return "AIOT_LCM_TA"
    
    return "UNKNOWN"


def parse_dwin_config(data: bytes, model_hint: Optional[str] = None) -> DwinConfig:
    """解析迪文配置文件。

    T5LC1 文件头无法区分 DGUSII 与 TA，调用方必须通过 model_hint
    指定 ``T5L_DGUSII`` 或 ``T5L_TA``。
    """
    try:
        profiles = load_devices()
    except ProfileError as error:
        raise ConfigError(str(error))
    if model_hint in profiles:
        profile = profiles[model_hint]
        if not data.startswith(bytes.fromhex(profile["header_hex"])):
            raise ConfigError(
                "指定源型号 {} 与文件头不一致".format(model_hint)
            )
        try:
            return parse_with_profile(data, profile, DwinConfig)
        except ProfileError as error:
            raise ConfigError(str(error))

    model = detect_model(data)
    profile = profiles.get(model)
    if profile is not None:
        try:
            return parse_with_profile(data, profile, DwinConfig)
        except ProfileError as error:
            raise ConfigError(str(error))

    if model == "T5L_AMBIGUOUS":
        raise AmbiguousModelError(
            "T5LC1 无法仅凭文件内容区分 DGUSII 与 TA，请指定源型号"
        )
    if model_hint is not None and model_hint != model:
        raise ConfigError(
            "指定源型号 {} 与文件头检测结果 {} 不一致".format(model_hint, model)
        )

    if model == "UNKNOWN":
        raise UnknownModelError("无法识别的 CFG 文件头")
    elif model == "AIOT_LCM_TA":
        return parse_aiot_lcm_ta(data)
    elif model == "T5UIC2":
        return parse_t5uic2(data)
    elif model == "T5UIC3":
        return parse_t5uic3(data)
    elif model == "T5UID3":
        return parse_t5uid3(data)
    raise UnsupportedModelError("已识别型号 {}，但尚无可靠解析规则".format(model))


def convert_to_jgxing(dwin: DwinConfig, system: str = "JGUSII") -> JgxingConfig:
    """将迪文配置转换为晶兴配置"""
    if system not in SYSTEMS:
        raise ConfigError("不支持的目标系统：{}".format(system))
    try:
        return convert_with_target_profile(dwin, system, JgxingConfig)
    except ProfileError as error:
        raise ConfigError(str(error))


def generate_config_txt(jgxing: JgxingConfig, system: str = "JGUSII") -> str:
    """生成晶兴 CONFIG.txt 内容
    
    指令集模式寄存器：R1, R2, R3, R6, R7, R8, R9, R10, R11, R12, RD, RE
    JGUSII 模式寄存器：R1, R2, R3, RA, R6, R7, R8, R10, R11, R12, RD, RE
    """
    lines = [
        f"R1={jgxing.R1:02X}",
        f"R2={jgxing.R2:02X}",
    ]
    if jgxing.RC is not None:
        lines.append(f"RC={jgxing.RC:02X}")
    lines.append(f"R3={jgxing.R3:02X}")
    
    if system == "INSTRUCTION":
        # 指令集模式：R9 = 格式化标志
        if jgxing.RB == 0x5A:
            lines.append(f"R9={jgxing.RB:02X}")
        else:
            lines.append("R9=00")
        # 指令集模式没有 RA
    else:
        # JGUSII/JGUS 模式：RA = 帧头低字节
        lines.append(f"RA={jgxing.RA:02X}")
    
    lines.extend([
        f"R6={jgxing.R6:02X}",
        f"R7={jgxing.R7:02X}",
        f"R8={jgxing.R8:02X}",
    ])
    if jgxing.R10 is not None:
        lines.append(f"R10={jgxing.R10:02X}")
    if jgxing.R11 is not None:
        lines.append(f"R11={jgxing.R11:02X}")
    lines.extend([
        f"R12={jgxing.R12:02X}",
        f"RD={jgxing.RD:02X}",
        f"RE={jgxing.RE:02X}",
    ])
    
    if jgxing.tp_correct:
        lines.append("TP_CORRECT")
    
    return '\n'.join(lines) + '\n'


