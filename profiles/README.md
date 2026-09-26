# 设备规则维护

设备规则的唯一人工来源是 `设备规则.xlsx`。`generated/` 下的 JSON 由导出器生成，不要手工修改。

在项目根目录运行：

```powershell
update_profiles.cmd
```

导出失败时先修复 Excel 报错的工作表和行号，不要绕过校验器。

## 设备型号表

每行一个设备。只有 `Status=已验证` 的设备会进入 JSON。

- `DeviceID`：程序内部唯一型号名。
- `DisplayName`：界面显示名称。
- `HeaderHex`：文件头十六进制字节，用空格分隔，不写 `0x`。
- `MinimumSize`：解析所需的最小字节数。
- `DefaultSystem`：`JGUS`、`JGUSII` 或 `INSTRUCTION`。
- `Status`：建议使用 `草稿`、`待验证`、`已验证`、`停用`。
- 相同文件头允许对应多个设备。此时转换必须通过 `--source-model` 或界面选择型号。

## 源字段表

源字段把 CFG 字节解析为统一的 `DwinConfig` 字段。偏移从 0 开始，字节内 `Bit=0` 表示最低位。相同字段可有多行，按 `Priority` 从小到大覆盖。

支持的 `FieldType`：

- `bit`：读取一个位，可使用 `Invert`、`TrueValue`、`FalseValue`。
- `bitfield`：从 `Bit` 开始读取 `BitWidth` 个连续位。
- `uint`：读取无符号整数。
- `divisor`：使用 `Constant / 原始值`，适合波特率除数。
- `direct_baud`：直接读取实际波特率。
- `constant`：不读取源字节，直接使用 `Constant`。

扩展控制列：

- `SkipFalse`：位为 0 时不覆盖已有默认值。
- `SkipValuesHex`：逗号分隔的原始十六进制值，命中时保留默认值，例如 `0000,FFFF`。
- `NullIfZero`：填写“是”时，原始值 0 解析为未配置。
- `Divide`：读取后执行整数除法。
- `MinimumValue`：限制解析结果的最小值。

## 位映射表

把语义字段写入目标寄存器位。目标系统、寄存器和位号的组合不能重复。

支持的 `Operation`：`truthy`、`falsy`、`equals`、`not_equals`。后两种必须填写 `CompareValue`。没有目标位的行可用于记录“源字段在目标系统中没有对应配置”。

## 寄存器默认值表

固定寄存器填写 `DefaultValueHex`。动态寄存器填写 `SourceField`、`OutputPolicy` 和 `Transform`。

支持的转换：`direct`、`enum`、`percent_to_63`、`seconds`、`seconds_x2`、`touch_type`、`debug_switch`。

## 新增设备流程

1. 在设备型号表复制示例行，状态先设为 `草稿`。
2. 在源字段表录入偏移、位号、长度、默认值和特殊值处理。
3. 确认目标系统已有位映射和寄存器规则；没有时再补充目标规则。
4. 用真实 CFG 和预期寄存器输出增加回归测试。
5. 运行 `update_profiles.cmd`，确认导出和全部测试通过。
6. 验证结果后再把设备状态改为 `已验证`。

## 备份和回滚

修改工作簿前先复制到 `profiles/backups/`。回滚时恢复工作簿，然后重新运行 `update_profiles.cmd`，不要只恢复 JSON。
