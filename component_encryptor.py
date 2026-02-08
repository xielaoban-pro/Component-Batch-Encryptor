import os
import sys
import base64
import zlib
import random
import string
import argparse
import re
import shutil
import json
import binascii

# ==========================================
# 配置与常量 (sdczz.com)
# ==========================================

# 配置文件路径
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(APP_DIR, 'component_config.json')

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_config(key, value):
    config = load_config()
    config[key] = value
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        pass

# ==========================================
# 辅助函数
# ==========================================

def get_random_string(length=8):
    return ''.join(random.choices(string.ascii_letters, k=length))

def to_hex_string(s):
    """将字符串转换为 PHP Hex 格式 (e.g. \x61\x62...)"""
    return "".join([f"\\x{ord(c):02x}" for c in s])

def read_file_content(file_path):
    """智能读取文件内容 (自动尝试 UTF-8 和 GBK)"""
    # 1. 尝试 UTF-8
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        pass
    
    # 2. 尝试 GB18030 (兼容 GBK/GB2312)
    try:
        with open(file_path, 'r', encoding='gb18030') as f:
            return f.read()
    except:
        return None

def extract_doc_comment(content):
    """
    提取文件开头的注释块。
    """
    head_sample = content[:2048]
    match = re.search(r'^\s*(?:<\?php\s*)?\s*(\/\*.*?\*\/)', head_sample, re.DOTALL)
    if match:
        return match.group(1)
    
    match_loose = re.search(r'^\s*(\/\*.*?\*\/)', head_sample, re.DOTALL)
    if match_loose:
        return match_loose.group(1)
        
    return ""

def prepare_content(content):
    content = content.strip()
    if content.startswith("<?php"): content = content[5:]
    elif content.startswith("<?"): content = content[2:]
    if content.endswith("?>"): content = content[:-2]
    return content.strip()

# ==========================================
# 组件加密算法 (Github / Open Source Style)
# ==========================================

def encrypt_clean(content, header):
    """Level 1: 基础清理"""
    content = re.sub(r'//.*', '', content)
    content = re.sub(r'#.*', '', content)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    content = re.sub(r'\s+', ' ', content)
    
    return f"<?php\n{header}\n{content}\n?>"

def encrypt_hex(content, header):
    """Level 2: Hex 变量混淆"""
    b64 = base64.b64encode(content.encode('utf-8')).decode('ascii')
    
    v_a = get_random_string(5)
    v_b = get_random_string(5)
    
    hex_decode = to_hex_string("base64_decode")
    
    # 修复: 去除 $ 和变量名之间的空格
    stub = f"""<?php
{header}
${v_a} = "{hex_decode}";
${v_b} = "{b64}";
eval(${v_a}(${v_b}));
?>"""
    return stub

def encrypt_class(content, header):
    """Level 3: 类组件封装"""
    class_name = "Component_" + get_random_string(6)
    method_name = "run_" + get_random_string(4)
    prop_name = "_" + get_random_string(10)
    
    compressed = zlib.compress(content.encode('utf-8'))
    b64 = base64.b64encode(compressed).decode('ascii')
    
    # 修复: 去除 private static $ 后面和 self::$ 后面的空格
    stub = f"""<?php
{header}
class {class_name} {{
    private static ${prop_name} = '{b64}';
    
    public static function {method_name}() {{
        $src = base64_decode(self::${prop_name});
        if ($src) {{
            eval(gzuncompress($src));
        }}
    }}
}}
{class_name}::{method_name}();
?>"""
    return stub

def encrypt_goto(content, header):
    """Level 4: 流程控制混淆"""
    compressed = zlib.compress(content.encode('utf-8'))
    b64 = base64.b64encode(compressed).decode('ascii')
    
    part_len = len(b64) // 3
    p1 = b64[:part_len]
    p2 = b64[part_len:part_len*2]
    p3 = b64[part_len*2:]
    
    v_data = get_random_string(4)
    label_start = get_random_string(5).upper()
    label_mid = get_random_string(5).upper()
    label_end = get_random_string(5).upper()
    label_exec = get_random_string(5).upper()
    
    # 修复: 去除 $ 后的空格，并补全 eval 行尾的分号
    stub = f"""<?php
{header}
${v_data} = '';
goto {label_mid};

{label_start}:
${v_data} .= '{p3}';
goto {label_exec};

{label_mid}:
${v_data} .= '{p1}';
goto {label_end};

{label_exec}:
eval(gzuncompress(base64_decode(${v_data})));
exit;

{label_end}:
${v_data} .= '{p2}';
goto {label_start};
?>"""
    return stub

# ==========================================
# 业务逻辑
# ==========================================

def process_file(input_file, output_file, mode, keep_comments, silent=False):
    if not os.path.exists(input_file):
        if not silent: print(f"[-] 文件不存在: {input_file}")
        return False

    raw = read_file_content(input_file)
    if raw is None:
        if not silent: print(f"[-] 读取失败(编码错误): {input_file}")
        return False

    header = ""
    if keep_comments:
        header = extract_doc_comment(raw)
        if not silent:
            if header:
                preview = header.replace('\n', ' ')[:30] + "..."
                print(f"[+] 提取到注释: {preview}")
            else:
                print("[-] 未检测到有效的头部注释块 (将使用默认版权)")
    
    level_map = {'1': 'Clean', '2': 'Hex', '3': 'Class', '4': 'Goto'}
    level_name = level_map.get(str(mode), 'Unknown')
    
    if not header:
        header = f"/* sdczz.com 声达组件加密 | 级别: {level_name} */"

    content = prepare_content(raw)
    
    if not silent:
        print(f"[*] 处理中: {level_name} -> {output_file}")

    try:
        if str(mode) == '1': final = encrypt_clean(content, header)
        elif str(mode) == '2': final = encrypt_hex(content, header)
        elif str(mode) == '3': final = encrypt_class(content, header)
        elif str(mode) == '4': final = encrypt_goto(content, header)
        else: final = encrypt_class(content, header)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(final)
        return True
    except Exception as e:
        if not silent: print(f"[-] 错误: {e}")
        return False

def process_directory(input_dir, output_dir, mode, keep_comments):
    if not os.path.exists(input_dir): return
    
    print(f"[*] 批量处理目录: {input_dir}")
    print(f"[*] 输出目录: {output_dir}")
    print("=" * 40)
    
    c_enc = 0
    c_cp = 0
    
    for root, dirs, files in os.walk(input_dir):
        rel = os.path.relpath(root, input_dir)
        target = os.path.join(output_dir, rel)
        if not os.path.exists(target): os.makedirs(target)
        
        for f in files:
            src = os.path.join(root, f)
            dst = os.path.join(target, f)
            
            if f.lower().endswith('.php'):
                if process_file(src, dst, mode, keep_comments, silent=True):
                    c_enc += 1
                    print(f"[OK] 加密: {os.path.join(rel, f)}")
                else:
                    shutil.copy2(src, dst)
            else:
                shutil.copy2(src, dst)
                c_cp += 1
    
    print("=" * 40)
    print(f"处理完成: 加密 {c_enc} 个, 复制 {c_cp} 个")

# ==========================================
# 主程序
# ==========================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("==========================================")
        print("      声达网络 PHP 组件加密工具 (Component Ed.)")
        print("      基于 GitHub 开源混淆逻辑架构")
        print("==========================================")
        
        config = load_config()
        last_dir = config.get('last_output_dir', '')
        
        while True:
            path = input("\n[?] 输入文件/文件夹路径: ").strip().strip('"')
            if path: break
            
        is_dir = os.path.isdir(path)
        base = os.path.basename(path)
        
        def_out = ""
        if last_dir and os.path.isdir(last_dir):
            if is_dir: def_out = os.path.join(last_dir, base + "_component")
            else: def_out = os.path.join(last_dir, "comp_" + base)
        else:
            def_out = path + "_component" if is_dir else "comp_" + base
            
        out = input(f"[?] 输出路径 (默认: {def_out}): ").strip()
        if not out: out = def_out
        
        try:
            curr = os.path.dirname(os.path.abspath(out))
            if curr != last_dir: save_config('last_output_dir', curr)
        except:
            pass
        
        print("\n选择组件加密级别:")
        print("  1. Clean  [基础] - 仅清理注释空格，保留结构")
        print("  2. Hex    [中级] - 关键逻辑 Hex 编码 (Shell风格)")
        print("  3. Class  [高级] - 封装为类组件，静态调用 (推荐)")
        print("  4. Goto   [混淆] - 模拟 Yakpro 流程打乱 (复杂)")
        
        m = input("\n[?] 输入序号 (1-4, 默认 3): ").strip()
        if m not in ['1','2','3','4']: m = '3'
        
        k = input("[?] 保留原注释 (y/N): ").strip().lower() == 'y'
        
        if is_dir: process_directory(path, out, m, k)
        else: process_file(path, out, m, k)
        
        input("\n按回车退出...")
        sys.exit(0)
    
    # CLI 模式
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("-o", "--output")
    parser.add_argument("-m", "--mode", default="3")
    args = parser.parse_args()
    
    out = args.output if args.output else args.input + "_comp"
    if os.path.isdir(args.input):
        process_directory(args.input, out, args.mode, False)
    else:
        process_file(args.input, out, args.mode, False)