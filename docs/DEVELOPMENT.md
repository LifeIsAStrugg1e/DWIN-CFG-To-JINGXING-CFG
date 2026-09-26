# 开发指南

## 代码分层

- `cfg_convert_tools.py`：命令行入口和兼容 API。
- `lib/converter.py`：文件头识别、统一配置对象和目标文本生成。
- `lib/profile_engine.py`：加载 JSON、解释源字段规则和目标系统规则。
- `tools/export_profiles.py`：读取 Excel、校验规则并生成 JSON。
- `web_app.py`：标准库 HTTP 服务和 Web API。
- `web/`：前端页面、样式和交互。

运行时只读取 `profiles/generated/*.json`，不会直接打开 Excel。Excel 的变更必须经过导出器。

## 规则更新流程

```powershell
Copy-Item profiles\设备规则.xlsx profiles\backups\设备规则_$(Get-Date -Format yyyyMMdd_HHmmss).xlsx
update_profiles.cmd
```

如果导出失败，按报错中的工作表和行号修正 Excel。不要手工编辑 `profiles/generated`。

## 新设备开发

先确认 CFG 文件头、最小长度、字段偏移和目标系统。若文件头无法区分多个型号，应在 Excel 中使用相同 `HeaderHex`，并在 CLI、Web 或 API 中强制选择 `source_model`。

规则只能表达通用的字节、位、位域、除数、默认值和目标映射。如果遇到新的解析行为，优先扩展 Excel 列和 `profile_engine.py` 的通用解释器，再录入设备规则，不要新增设备专用解析函数。

## 测试流程

```powershell
py -3 -B -m unittest discover -s tests -v
py -3 -B -m unittest discover -s lib\tests -v
```

新增设备至少应覆盖：

- 文件头识别和型号选择。
- 最小长度和截断文件错误。
- 默认值、特殊值和可选字段。
- 代表性的目标位和寄存器输出。
- CLI 或 Web API 的端到端转换。

## Web 开发

启动服务：

```powershell
py -3 web_app.py --port 8765
```

接口：

- `GET /api/meta`：设备、目标系统和规则概要。
- `POST /api/convert?source_model=...&system=...`：请求体为 CFG 原始字节。

修改前端后，用真实 CFG 验证桌面和移动端布局，并检查映射表、寄存器位卡片、原始字节和下载按钮。

## 编码约定

源代码和文档统一使用 UTF-8。新增文件默认使用 ASCII；必须出现中文时使用 UTF-8 保存。不要用系统默认代码页重新保存中文文件。

## 发布检查

1. Excel 已备份。
2. `update_profiles.cmd` 成功完成。
3. 两组测试全部通过。
4. 至少用一个真实 CFG 完成 CLI 或 Web 转换。
5. 确认 `profiles/generated` 与 Excel 同步。
6. 确认没有提交 `__pycache__`、临时锁文件或中间脚本。
