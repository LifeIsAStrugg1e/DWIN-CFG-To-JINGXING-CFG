# 独立转换核心

`converter.py` 负责型号检测、CFG 语义解析、晶兴寄存器映射和文本生成，
不读写文件，也不依赖第三方包。

## API

```python
from lib import (
    parse_dwin_config,
    resolve_system,
    convert_to_jgxing,
    generate_config_txt,
)

dwin = parse_dwin_config(data, model_hint="T5L_DGUSII")
system = resolve_system(dwin.model, "AUTO")
jgxing = convert_to_jgxing(dwin, system)
text = generate_config_txt(jgxing, system)
```

`T5LC1` 存在源型号歧义，必须通过 `model_hint` 传入 `T5L_DGUSII` 或
`T5L_TA`。未知型号、截断数据、尚无可靠解析器的型号以及目标系统不支持的
波特率都会抛出 `ConfigError` 的相应子类。

## 批量 CLI

从项目根目录运行：

```powershell
py -3 -m lib.cli input_dir output_dir
py -3 -m lib.cli input.CFG output.txt --source-model T5L_DGUSII
```

目录模式生成 `<原文件名>_CONFIG.txt`。
