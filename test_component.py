#!/usr/bin/env python3
"""测试XiaoZhi ESP32 Home Assistant集成的基本结构和配置。

此脚本用于检测组件的结构完整性和基本配置的正确性，
而不需要启动完整的Home Assistant实例。
"""

import os
import sys
import json
import importlib.util
import traceback
from pathlib import Path

def check_file_exists(file_path, required=True):
    """检查文件是否存在。"""
    sys.stdout.write(f"检查文件：{file_path}\n")
    sys.stdout.flush()
    path = Path(file_path)
    exists = path.exists()
    status = "✅" if exists else "❌" if required else "⚠️"
    sys.stdout.write(f"{status} {file_path}\n")
    sys.stdout.flush()
    return exists

def load_python_module(file_path):
    """加载Python模块并检查基本语法。"""
    sys.stdout.write(f"检查Python语法：{file_path}\n")
    sys.stdout.flush()
    try:
        spec = importlib.util.spec_from_file_location("module.name", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.stdout.write(f"✅ {file_path} - 无语法错误\n")
        sys.stdout.flush()
        return True
    except Exception as e:
        sys.stdout.write(f"❌ {file_path} - 错误: {str(e)}\n")
        traceback.print_exc()
        sys.stdout.flush()
        return False

def validate_json_file(file_path):
    """验证JSON文件的格式。"""
    sys.stdout.write(f"验证JSON：{file_path}\n")
    sys.stdout.flush()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json.load(f)
        sys.stdout.write(f"✅ {file_path} - 有效的JSON\n")
        sys.stdout.flush()
        return True
    except Exception as e:
        sys.stdout.write(f"❌ {file_path} - JSON错误: {str(e)}\n")
        sys.stdout.flush()
        return False

def check_required_keys(json_file, required_keys):
    """检查JSON文件中是否包含所有必需的键。"""
    sys.stdout.write(f"检查必需键：{json_file}\n")
    sys.stdout.flush()
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        missing_keys = [key for key in required_keys if key not in data]
        
        if missing_keys:
            sys.stdout.write(f"❌ {json_file} - 缺少必需的键: {', '.join(missing_keys)}\n")
            sys.stdout.flush()
            return False
        else:
            sys.stdout.write(f"✅ {json_file} - 包含所有必需的键\n")
            sys.stdout.flush()
            return True
    except Exception as e:
        sys.stdout.write(f"❌ {json_file} - 无法检查键: {str(e)}\n")
        sys.stdout.flush()
        return False

def main():
    """主函数：运行所有检查。"""
    sys.stdout.write("开始XiaoZhi ESP32集成测试...\n")
    sys.stdout.flush()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    component_dir = os.path.join(base_dir, "custom_components", "xiaozhi")
    
    sys.stdout.write(f"基础目录：{base_dir}\n")
    sys.stdout.write(f"组件目录：{component_dir}\n")
    sys.stdout.flush()
    
    sys.stdout.write("\n=== 检查目录结构 ===\n")
    sys.stdout.flush()
    check_file_exists(component_dir)
    check_file_exists(os.path.join(component_dir, "translations"))
    
    sys.stdout.write("\n=== 检查核心文件 ===\n")
    sys.stdout.flush()
    core_files = [
        os.path.join(component_dir, "__init__.py"),
        os.path.join(component_dir, "manifest.json"),
        os.path.join(component_dir, "const.py"),
        os.path.join(component_dir, "config_flow.py"),
        os.path.join(component_dir, "websocket_server.py"),
        os.path.join(component_dir, "binary_sensor.py"),
        os.path.join(component_dir, "services.yaml"),
        os.path.join(component_dir, "translations", "zh.json"),
    ]
    
    all_files_exist = True
    for file_path in core_files:
        exists = check_file_exists(file_path)
        all_files_exist = all_files_exist and exists
    
    if not all_files_exist:
        sys.stdout.write("\n❌ 缺少一些核心文件，请创建它们\n")
        sys.stdout.flush()
        return
    
    sys.stdout.write("\n=== 验证JSON文件 ===\n")
    sys.stdout.flush()
    json_files = [
        os.path.join(component_dir, "manifest.json"),
        os.path.join(component_dir, "translations", "zh.json"),
        os.path.join(base_dir, "hacs.json"),
    ]
    
    json_valid = True
    for file_path in json_files:
        valid = validate_json_file(file_path)
        json_valid = json_valid and valid
    
    if not json_valid:
        sys.stdout.write("\n❌ 一些JSON文件无效，请修复它们\n")
        sys.stdout.flush()
        return
    
    sys.stdout.write("\n=== 检查必需的配置键 ===\n")
    sys.stdout.flush()
    # 检查manifest.json的必需键
    manifest_required_keys = ["domain", "name", "documentation", "dependencies", "codeowners", "config_flow"]
    manifest_keys_ok = check_required_keys(os.path.join(component_dir, "manifest.json"), manifest_required_keys)
    
    # 检查hacs.json的必需键
    hacs_required_keys = ["name", "hacs"]
    hacs_keys_ok = check_required_keys(os.path.join(base_dir, "hacs.json"), hacs_required_keys)
    
    sys.stdout.write("\n=== 检查Python文件语法 ===\n")
    sys.stdout.flush()
    python_files = [
        os.path.join(component_dir, "__init__.py"),
        os.path.join(component_dir, "const.py"),
        os.path.join(component_dir, "config_flow.py"),
        os.path.join(component_dir, "websocket_server.py"),
        os.path.join(component_dir, "binary_sensor.py"),
    ]
    
    python_valid = True
    for file_path in python_files:
        valid = load_python_module(file_path)
        python_valid = python_valid and valid
    
    sys.stdout.write("\n=== 结果摘要 ===\n")
    sys.stdout.write(f"目录结构检查: {'✅ 通过' if all_files_exist else '❌ 失败'}\n")
    sys.stdout.write(f"JSON文件验证: {'✅ 通过' if json_valid else '❌ 失败'}\n")
    sys.stdout.write(f"配置键检查: {'✅ 通过' if manifest_keys_ok and hacs_keys_ok else '❌ 失败'}\n")
    sys.stdout.write(f"Python语法检查: {'✅ 通过' if python_valid else '❌ 失败'}\n")
    sys.stdout.flush()
    
    if all_files_exist and json_valid and manifest_keys_ok and hacs_keys_ok and python_valid:
        sys.stdout.write("\n✅ 所有检查通过！集成结构看起来正确。\n")
        sys.stdout.write("您可以尝试在Home Assistant中安装此集成。\n")
        sys.stdout.flush()
    else:
        sys.stdout.write("\n❌ 一些检查失败。请修复上述问题后再尝试安装集成。\n")
        sys.stdout.flush()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stdout.write(f"测试脚本运行时出错: {str(e)}\n")
        traceback.print_exc()
        sys.stdout.flush() 