# CFG Convert Tools

CFG 配置转换工具，将迪文设备的二进制配置转换为晶兴目标系统的寄存器配置文本。

项目使用 Python 标准库运行，不依赖 Flask 或其他第三方运行库。支持 Python 3.7 及以上版本。

## 功能

- 解析设备 CFG 文件并转换为统一的语义配置。
- 根据 `JGUS`、`JGUSII` 或 `INSTRUCTION` 规则生成目标寄存器。
- 通过 Excel 维护设备字段、位映射、寄存器默认值和枚举值。
- 提供本地 Web 界面，显示源字段、原始字节、目标寄存器和位映射。
- 支持命令行和 Python API。

## 快速开始

### 命令行

```powershell
py -3 cfg_convert_tools.py input.CFG
py -3 cfg_convert_tools.py input.CFG -o output.txt
```

默认输出到输入文件同目录的 `config.TXT`。

`T5LC1` 文件头同时用于 T5L DGUSII 和 T5L TA，必须手动指定源型号：

```powershell
py -3 cfg_convert_tools.py T5LCFG.CFG --source-model T5L_DGUSII
py -3 cfg_convert_tools.py T5LCFG.CFG --source-model T5L_TA
```

覆盖自动选择的目标系统：

```powershell
py -3 cfg_convert_tools.py input.CFG --system JGUSII
```

### Web 界面

```powershell
py -3 web_app.py --port 8765
```

浏览器打开 <http://127.0.0.1:8765/>。界面支持拖放 CFG、选择源设备和目标系统、查看转换关系，以及下载 `config.TXT`。

## Python API

```python
from cfg_convert_tools import convert_cfg, generate_config_text

output_path = convert_cfg(
    "T5LCFG.CFG",
    source_model="T5L_DGUSII",
    system="AUTO",
)

text = generate_config_text(
    cfg_bytes,
    source_model="T5L_TA",
    system="INSTRUCTION",
)
```

核心实现位于 `lib/converter.py`，规则加载和解释位于 `lib/profile_engine.py`。

## 设备规则

人工只编辑 `profiles/设备规则.xlsx`，不要直接编辑 `profiles/generated/*.json`。更新规则后运行：

```powershell
update_profiles.cmd
```

脚本会依次：

1. 校验 Excel 的设备、源字段、位映射、寄存器默认值和枚举映射。
2. 生成运行时 JSON。
3. 执行项目测试和核心库测试。

详细字段说明见 `profiles/README.md`。规则工作簿的备份保存在 `profiles/backups/`。

## 当前设备

已通过 Excel 规则驱动：

- T5L DGUSII
- T5L TA
- T5UIC2
- T5UID3

其他设备可能只能识别文件头，完整字段规则验证后才能加入 `已验证` 状态。未验证设备不会导出到运行时 JSON。

## 测试

```powershell
py -3 -B -m unittest discover -s tests -v
py -3 -B -m unittest discover -s lib\tests -v
```

测试覆盖设备识别、Excel 规则导出、T5L 两种解析结果、目标位映射、寄存器输出和 Web API 数据结构。

## 目录结构

```text
cfg_convert_tools.py       命令行入口和兼容 API
web_app.py                 本地 Web 服务
web/                       Web 前端
lib/                       转换器、规则引擎和核心测试
profiles/                  Excel 规则、生成 JSON 和备份
tools/                     Excel 规则导出器
tests/                     项目级回归测试
docs/                      开发说明
convert_tools/             历史 C/Visual Studio 实现，仅供对照
```

## 开发说明

完整的开发流程、规则迁移约定和故障排查见 `docs/DEVELOPMENT.md`。
