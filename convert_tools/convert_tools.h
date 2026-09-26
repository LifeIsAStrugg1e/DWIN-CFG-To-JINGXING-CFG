#ifndef CONVERT_TOOLS_H
#define CONVERT_TOOLS_H

/*
 * convert_tools - 设备配置文件(CFG)转换库
 *
 * 功能概述：
 *   解析设备二进制配置文件，自动识别设备型号，提取波特率、系统配置、
 *   背景文件、音频文件等参数，生成寄存器配置文本并写入同目录下的 config.TXT。
 *
 * 使用方式：
 *   本库只依赖标准 C 运行库，可编译为静态库直接嵌入到其他项目中。
 *   调用方只需提供输入文件路径，输出文件固定为同目录下的 config.TXT。
 *
 * 示例：
 *   CfgResult r = cfg_convert_to_file("D:\\data\\T5LCFG.CFG");
 *   if (r != CFG_OK) {
 *       // 通过 cfg_result_string(r) 获取可读的错误描述
 *   }
 */

#ifdef __cplusplus
extern "C" {
#endif

/*
 * 转换结果错误码
 * 所有对外接口均以此枚举作为返回值。
 */
typedef enum {
    CFG_OK = 0,              /* 转换成功 */
    CFG_ERR_INVALID_ARG,     /* 传入参数为空指针 */
    CFG_ERR_OPEN_INPUT,      /* 无法打开输入文件 */
    CFG_ERR_READ_INPUT,      /* 读取输入文件失败 */
    CFG_ERR_OUT_OF_MEMORY,   /* 内存分配失败 */
    CFG_ERR_UNKNOWN_DEVICE,  /* 无法识别的设备型号 */
    CFG_ERR_PATH_TOO_LONG,   /* 推导出的输出路径超出缓冲区 */
    CFG_ERR_OPEN_OUTPUT,     /* 无法创建输出文件 */
    CFG_ERR_WRITE_OUTPUT     /* 写入输出文件失败 */
} CfgResult;

/*
 * 解析设备配置文件并生成寄存器配置文本，
 * 输出到与输入文件同目录下的 config.TXT。
 *
 * @param input_path 输入设备配置文件路径（例如 "D:\\data\\T5LCFG.CFG"），
 *                   输出文件固定为同目录下的 config.TXT。
 *
 * @return CfgResult 错误码，返回 CFG_OK 表示转换并写入成功。
 */
CfgResult cfg_convert_to_file(const char* input_path);

/*
 * 获取错误码对应的可读描述（中文）。
 *
 * @param result 错误码
 * @return 指向静态字符串的指针，调用方无需释放。
 */
const char* cfg_result_string(CfgResult result);

#ifdef __cplusplus
}
#endif

#endif /* CONVERT_TOOLS_H */
