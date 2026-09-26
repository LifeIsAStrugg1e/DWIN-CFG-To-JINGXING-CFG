/* 允许使用标准 C 的 fopen/fread 等函数（MSVC 下默认会报警告） */
#define _CRT_SECURE_NO_WARNINGS

#include "convert_tools.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

/* =========================================================================
 * 一、设备档案定义
 * ====================================================================== */

/*
 * 设备配置文件的偏移结构体
 * 描述某型号设备在二进制配置文件中的各项参数位置。
 */
typedef struct {
    const char*          name;      /* 设备产品名 */
    const unsigned char* id_bytes;  /* 身份字节（文件开头的识别标志） */
    int                  id_len;    /* 身份字节长度（部分型号为 4 字节，部分为 5 字节） */
    int                  cfg_off;   /* 系统配置字节偏移 */
    int                  baud_off;  /* 波特率字节偏移 */
    int                  baud_size; /* 波特率字段占用的字节数 */
    int                  audio_off; /* 音频文件字节偏移，无则置 -1 */
    int                  bg_off;    /* 背景文件字节偏移，无则置 -1 */
    int                  baud_base; /* 通过分频值计算波特率时使用的基准频率 */
} Device;

/* 各设备的身份字节 */
/* T5UI 系列 */
static const unsigned char ID_C1[] = { 0x54, 0x35, 0x43, 0x31 }; /* "T5C1" */
static const unsigned char ID_C2[] = { 0x54, 0x35, 0x43, 0x32 }; /* "T5C2" */
static const unsigned char ID_C3[] = { 0x54, 0x35, 0x43, 0x33 }; /* "T5C3" */
static const unsigned char ID_C4[] = { 0x54, 0x35, 0x43, 0x34 }; /* "T5C4" */

static const unsigned char ID_D1[] = { 0x54, 0x35, 0x44, 0x31 }; /* "T5D1" */
static const unsigned char ID_D2[] = { 0x54, 0x35, 0x44, 0x32 }; /* "T5D2" */
static const unsigned char ID_D3[] = { 0x54, 0x35, 0x44, 0x33 }; /* "T5D3" */

/*
 * T5L 系列
 * T5L_DGUSII 与 T5L_TA 的区别在于是否存在 14 开头的 bin 文件（有则为 DGUSII）。
 * 除 DGUSII 额外拥有音频与背景地址外，其余偏移与 TA 一致。
 */
static const unsigned char ID_DGUSII[] = { 0x54, 0x35, 0x4C, 0x43, 0x31 }; /* "T5L_DGUSII" */
static const unsigned char ID_TA[] = { 0x54, 0x35, 0x4C, 0x43, 0x31 }; /* "T5L_TA" */

static const unsigned char ID_IOT_LCM_TA[] = { 0x41, 0x49, 0x6F, 0x54, 0x31 }; /* "T5L_IOT_LCM_TA" */
/* 设备档案表 */
static const Device DEVICES[] = {
    /* 设备名        身份字节         身份长度   配置偏移  波特率偏移   波特率长度    音频偏移  背景偏移   波特率基准 */
    { "T5U1C1",     ID_C1,           4,        0x04,     0x08,       1,          -1,       -1,       7833600 },
    { "T5U1C2",     ID_C2,           4,        0x08,     0x09,       1,          -1,       -1,       7833600 },
    { "T5U1C3",     ID_C3,           4,        0x08,     0x09,       1,          -1,       -1,       7833600 },
    { "T5U1C4",     ID_C4,           4,        0x08,     0x09,       1,          -1,       -1,       7833600 },
    { "T5U1D1",     ID_D1,           4,        0x08,     0x09,       1,          -1,       -1,       7833600 },
    { "T5U1D2",     ID_D2,           4,        0x08,     0x09,       1,          -1,       -1,       7833600 },
    { "T5U1D3",     ID_D3,           4,        0x08,     0x09,       1,          -1,       -1,       7833600 },
    { "T5L_DGUSII", ID_DGUSII,       5,        0x05,     0x0A,       2,          -1,       0x08,     3225600 },
    { "T5L_TA",     ID_TA,           5,        0x05,     0x0A,       2,          0x07,     0x08,     3225600 },
    { "AIOT_LCM_TA",ID_IOT_LCM_TA,   5,        0x05,     0x0C,       3,          0x07,     0x08,     -1 },
};

/* 波特率字段直接保存实际波特率的设备名 */
static const char* DIRECT_BAUD_DEVICE_NAMES[] = {
    "AIOT_LCM_TA",
};

/* =========================================================================
 * 二、波特率映射表
 * ====================================================================== */

/* 波特率与寄存器编码的对应关系 */
typedef struct {
    int baud; /* 真实波特率 */
    int code; /* 寄存器编码值 */
} BaudMap;

static const BaudMap BAUD_TABLE[] = {
    { 1200,   0x00 },
    { 2400,   0x01 },
    { 4800,   0x02 },
    { 9600,   0x03 },
    { 19200,  0x04 },
    { 38400,  0x05 },
    { 57600,  0x06 },
    { 115200, 0x07 },
};

/* =========================================================================
 * 三、内部工具函数
 * ====================================================================== */

/*
 * 在设备档案表中查找匹配的设备型号。
 * 若未适配则返回 NULL。
 *
 * @param data 文件数据
 * @param len  数据长度
 */
static const Device* find_device(const unsigned char* data, int len)
{
    int count = (int)(sizeof(DEVICES) / sizeof(DEVICES[0]));

    for (int i = 0; i < count; i++) {
        const Device* device = &DEVICES[i];

        if (len < device->id_len) { /* 数据长度不足以容纳身份字节，跳过 */
            continue;
        }
        if (memcmp(data, device->id_bytes, (size_t)device->id_len) == 0) {
            return device;
        }
    }

    return NULL; /* 档案表中不存在该型号 */
}

/* 判断设备的波特率字段是否直接保存实际波特率 */
static int is_direct_baud_device(const Device* device)
{
    int count = (int)(sizeof(DIRECT_BAUD_DEVICE_NAMES) /
                      sizeof(DIRECT_BAUD_DEVICE_NAMES[0]));

    for (int i = 0; i < count; i++) {
        if (strcmp(device->name, DIRECT_BAUD_DEVICE_NAMES[i]) == 0) {
            return 1;
        }
    }

    return 0;
}

/* 按大端序读取设备档案指定的波特率字段 */
static int read_baud_value(const unsigned char* data, const Device* device)
{
    int value = 0;

    for (int i = 0; i < device->baud_size; i++) {
        value = (value << 8) | data[device->baud_off + i];
    }

    return value;
}

/*
 * 将整个文件读入内存。
 * 成功时返回缓冲区指针并通过 out_len 返回长度；
 * 失败时返回 NULL 并通过 out_result 返回错误码。
 *
 * @param path       文件路径
 * @param out_len    输出：文件长度
 * @param out_result 输出：错误码
 */
static unsigned char* read_file(const char* path, int* out_len, CfgResult* out_result)
{
    FILE* fp = fopen(path, "rb");
    if (fp == NULL) {
        *out_result = CFG_ERR_OPEN_INPUT;
        return NULL;
    }

    /* 获取文件长度 */
    fseek(fp, 0, SEEK_END);
    long size = ftell(fp);
    fseek(fp, 0, SEEK_SET);

    if (size < 0) {
        fclose(fp);
        *out_result = CFG_ERR_READ_INPUT;
        return NULL;
    }

    unsigned char* buf = (unsigned char*)malloc((size_t)size);
    if (buf == NULL) {
        fclose(fp);
        *out_result = CFG_ERR_OUT_OF_MEMORY;
        return NULL;
    }

    size_t read_count = fread(buf, 1, (size_t)size, fp);
    fclose(fp);

    if (read_count != (size_t)size) { /* 实际读取长度与预期不符 */
        free(buf);
        *out_result = CFG_ERR_READ_INPUT;
        return NULL;
    }

    *out_len = (int)size;
    *out_result = CFG_OK;
    return buf;
}

/* 根据真实波特率查询寄存器编码，未知返回 0xFF */
static int baud_to_code(int baud)
{
    int count = (int)(sizeof(BAUD_TABLE) / sizeof(BAUD_TABLE[0]));

    for (int i = 0; i < count; i++) {
        if (BAUD_TABLE[i].baud == baud) {
            return BAUD_TABLE[i].code;
        }
    }
    return 0xFF;
}

/* 根据寄存器编码查询真实波特率，未知返回 -1 */
static int code_to_baud(int code)
{
    int count = (int)(sizeof(BAUD_TABLE) / sizeof(BAUD_TABLE[0]));

    for (int i = 0; i < count; i++) {
        if (BAUD_TABLE[i].code == code) {
            return BAUD_TABLE[i].baud;
        }
    }
    return -1;
}

/* 取 value 的第 bit 位（0/1） */
static int get_bit(int value, int bit)
{
    return (value >> bit) & 1;
}

/* 将 value 的第 bit 位置为 bit_val（0/1），结果限制在低 8 位 */
static int set_bit(int value, int bit, int bit_val)
{
    int mask = 1 << bit;

    if (bit_val) {
        return (value | mask) & 0xFF;
    }
    return (value & ~mask) & 0xFF;
}

/*
 * 解析系统配置字节，拆分为 R2 与 RC 两个寄存器值。
 *
 * @param src_byte 原始系统配置字节
 * @param r2_out   输出：R2 寄存器值
 * @param rc_out   输出：RC 寄存器值
 */
static void parse_system_config(int src_byte, int* r2_out, int* rc_out)
{
    int r2 = 0;
    int rc = 0;

    r2 = set_bit(r2, 4, get_bit(src_byte, 7));
    r2 = set_bit(r2, 2, get_bit(src_byte, 5));
    r2 = set_bit(r2, 3, get_bit(src_byte, 4));
    r2 = set_bit(r2, 5, get_bit(src_byte, 2));

    rc = set_bit(rc, 5, (1 - get_bit(src_byte, 3)) & 1);
    rc = set_bit(rc, 7, get_bit(src_byte, 0));
    rc = set_bit(rc, 6, get_bit(src_byte, 1));

    *r2_out = r2;
    *rc_out = rc;
}

/* 输出文本缓冲区大小，足够容纳全部寄存器行 */
#define CFG_OUTPUT_BUFFER_SIZE 1024

/*
 * 向输出缓冲区追加格式化文本，自动防止缓冲区溢出。
 * 若剩余空间不足则截断，不会越界写入。
 *
 * @param buf  输出缓冲区
 * @param size 缓冲区总大小
 * @param pos  当前写入位置（输入/输出）
 * @param fmt  格式化字符串
 */
static void append_format(char* buf, size_t size, size_t* pos, const char* fmt, ...)
{
    if (*pos >= size) {
        return;
    }

    va_list args;
    va_start(args, fmt);
    int written = vsnprintf(buf + *pos, size - *pos, fmt, args);
    va_end(args);

    if (written < 0) {
        return;
    }

    *pos += (size_t)written;
    if (*pos >= size) { /* 发生截断时回退到缓冲区末尾，保证下次写入不越界 */
        *pos = size - 1;
    }
}

/* 输出文件名（固定生成在输入文件所在目录） */
#define CFG_OUTPUT_NAME "config.TXT"

/* 路径缓冲区大小 */
#define CFG_PATH_BUFFER_SIZE 1024

/*
 * 根据输入文件路径推导输出路径：
 * 输出文件与输入文件位于同一目录，文件名为 CFG_OUTPUT_NAME。
 * 例如 "D:\\data\\T5LCFG.CFG" -> "D:\\data\\config.TXT"。
 * 若输入路径不含目录分隔符，则输出到当前工作目录。
 *
 * @param input_path 输入文件路径
 * @param out        输出缓冲区
 * @param out_size   缓冲区大小
 *
 * @return 成功返回 1，缓冲区不足返回 0
 */
static int build_output_path(const char* input_path, char* out, size_t out_size)
{
    const char* last_sep = NULL;

    /* 查找最后一个目录分隔符，同时兼容 Windows 的 '\\' 与 Unix 的 '/' */
    for (const char* p = input_path; *p != '\0'; p++) {
        if (*p == '\\' || *p == '/') {
            last_sep = p;
        }
    }

    if (last_sep == NULL) { /* 没有目录部分，输出到当前目录 */
        int n = snprintf(out, out_size, "%s", CFG_OUTPUT_NAME);
        return (n > 0 && (size_t)n < out_size);
    }

    size_t dir_len = (size_t)(last_sep - input_path) + 1; /* 含结尾分隔符 */
    size_t name_len = strlen(CFG_OUTPUT_NAME);

    if (dir_len + name_len + 1 > out_size) {
        return 0;
    }

    memcpy(out, input_path, dir_len);
    memcpy(out + dir_len, CFG_OUTPUT_NAME, name_len + 1);
    return 1;
}

/* =========================================================================
 * 四、配置文本生成
 * ====================================================================== */

/*
 * 根据文件数据识别设备并生成寄存器配置文本。
 *
 * @param data     文件数据
 * @param len      数据长度
 * @param out_buf  输出文本缓冲区
 * @param out_size 缓冲区大小
 *
 * @return CfgResult 错误码
 */
static CfgResult generate_config_text(const unsigned char* data, int len,
                                      char* out_buf, size_t out_size)
{
    const Device* device = find_device(data, len);
    if (device == NULL) {
        return CFG_ERR_UNKNOWN_DEVICE;
    }

    size_t pos = 0;

    /* --- R1: 波特率 --- */
    if (is_direct_baud_device(device)) {
        int baud = read_baud_value(data, device);
        int code = baud_to_code(baud);
        append_format(out_buf, out_size, &pos, "R1=%02X;//波特率 %d bps\n", code, baud);
    }
    else if (device->baud_size == 1) {
        int code = data[device->baud_off];
        int baud = code_to_baud(code);
        append_format(out_buf, out_size, &pos, "R1=%02X;//波特率 %d bps\n", code, baud);
    }
    else if (device->baud_size > 1) {
        int raw = read_baud_value(data, device);
        int baud = (raw > 0) ? (device->baud_base / raw) : 0;
        int code = baud_to_code(baud);
        append_format(out_buf, out_size, &pos, "R1=%02X;//波特率 %d bps\n", code, baud);
    }

    /* --- R2 / RC: 系统配置 --- */
    int src_byte = data[device->cfg_off];
    int r2 = 0;
    int rc = 0;
    parse_system_config(src_byte, &r2, &rc);
    append_format(out_buf, out_size, &pos, "R2=%02X;//系统配置\n", r2);
    append_format(out_buf, out_size, &pos, "RC=%02X;//系统配置\n", rc);

    /* --- R3 / RA: 通信帧头 --- */
    append_format(out_buf, out_size, &pos, "R3=5A;//通信数据帧头高字节\n");
    append_format(out_buf, out_size, &pos, "RA=A5;//通信数据帧头低字节\n");

    /* --- R5 / R9: 串口速率高低字节 --- */
    append_format(out_buf, out_size, &pos, "R5=00;//串口通信速率设置的高字节\n");
    append_format(out_buf, out_size, &pos, "R9=00;//串口通信速率设置的低字节\n");

    /* --- R10: 背景文件（仅部分型号具备） --- */
    if (device->bg_off != -1) {
        int bg = data[device->bg_off];
        if (bg >= 0x01 && bg <= 0xFF) {
            append_format(out_buf, out_size, &pos, "R10=%02X;//背景文件\n", bg);
        }
    }

    /* --- R11: 音频文件（仅部分型号具备） --- */
    if (device->audio_off != -1) {
        int audio = data[device->audio_off];
        if (audio >= 0x01 && audio <= 0xFF) {
            append_format(out_buf, out_size, &pos, "R11=%02X;//音频文件\n", audio);
        }
    }

    /* --- R12: 底图库（默认值，需手动修改） --- */
    append_format(out_buf, out_size, &pos, "R12=01;//需手动更改\n");

    return CFG_OK;
}

/* =========================================================================
 * 五、公共接口
 * ====================================================================== */

CfgResult cfg_convert_to_file(const char* input_path)
{
    if (input_path == NULL) {
        return CFG_ERR_INVALID_ARG;
    }

    /* 1. 推导输出路径：输入文件同目录下的 config.TXT */
    char output_path[CFG_PATH_BUFFER_SIZE];
    if (!build_output_path(input_path, output_path, sizeof(output_path))) {
        return CFG_ERR_PATH_TOO_LONG;
    }

    /* 2. 读取输入配置文件 */
    int len = 0;
    CfgResult result = CFG_OK;
    unsigned char* data = read_file(input_path, &len, &result);
    if (data == NULL) {
        return result;
    }

    /* 3. 识别设备并生成配置文本 */
    char out_buf[CFG_OUTPUT_BUFFER_SIZE] = { 0 };
    result = generate_config_text(data, len, out_buf, sizeof(out_buf));
    free(data);
    if (result != CFG_OK) {
        return result;
    }

    /* 4. 写入目标文件 */
    FILE* fp = fopen(output_path, "w");
    if (fp == NULL) {
        return CFG_ERR_OPEN_OUTPUT;
    }

    if (fputs(out_buf, fp) == EOF) {
        fclose(fp);
        return CFG_ERR_WRITE_OUTPUT;
    }

    fclose(fp);
    return CFG_OK;
}

const char* cfg_result_string(CfgResult result)
{
    switch (result) {
    case CFG_OK:               return "转换成功";
    case CFG_ERR_INVALID_ARG:  return "参数为空";
    case CFG_ERR_OPEN_INPUT:   return "无法打开输入文件";
    case CFG_ERR_READ_INPUT:   return "读取输入文件失败";
    case CFG_ERR_OUT_OF_MEMORY:return "内存分配失败";
    case CFG_ERR_UNKNOWN_DEVICE:return "无法识别的设备型号";
    case CFG_ERR_PATH_TOO_LONG:return "输出路径超出缓冲区";
    case CFG_ERR_OPEN_OUTPUT:  return "无法创建输出文件";
    case CFG_ERR_WRITE_OUTPUT: return "写入输出文件失败";
    default:                   return "未知错误";
    }
}
