#!/usr/bin/env python3
"""测试XiaoZhi ESP32 Home Assistant集成的基本结构和配置。

此脚本用于检测组件的结构完整性和基本配置的正确性，
而不需要启动完整的Home Assistant实例。
"""

import os
import sys
import json
import importlib.util
from pathlib import Path

def check_file_exists(file_path, required=True):
    """检查文件是否存在。"""
    path = Path(file_path)
    exists = path.exists()
    status = "✅" if exists else "❌" if required else "⚠️"
    print(f"{status} {file_path}")
    return exists

def load_python_module(file_path):
    """加载Python模块并检查基本语法。"""
    try:
        spec = importlib.util.spec_from_file_location("module.name", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(f"✅ {file_path} - 无语法错误")
        return True
    except Exception as e:
        print(f"❌ {file_path} - 错误: {e}")
        return False

def validate_json_file(file_path):
    """验证JSON文件的格式。"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json.load(f)
        print(f"✅ {file_path} - 有效的JSON")
        return True
    except Exception as e:
        print(f"❌ {file_path} - JSON错误: {e}")
        return False

def check_required_keys(json_file, required_keys):
    """检查JSON文件中是否包含所有必需的键。"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        missing_keys = [key for key in required_keys if key not in data]
        
        if missing_keys:
            print(f"❌ {json_file} - 缺少必需的键: {', '.join(missing_keys)}")
            return False
        else:
            print(f"✅ {json_file} - 包含所有必需的键")
            return True
    except Exception as e:
        print(f"❌ {json_file} - 无法检查键: {e}")
        return False

def main():
    """主函数：运行所有检查。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    component_dir = os.path.join(base_dir, "custom_components", "xiaozhi")
    
    print("=== 检查目录结构 ===")
    check_file_exists(component_dir)
    check_file_exists(os.path.join(component_dir, "translations"))
    
    print("\n=== 检查核心文件 ===")
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
        print("\n❌ 缺少一些核心文件，请创建它们")
        return
    
    print("\n=== 验证JSON文件 ===")
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
        print("\n❌ 一些JSON文件无效，请修复它们")
        return
    
    print("\n=== 检查必需的配置键 ===")
    # 检查manifest.json的必需键
    manifest_required_keys = ["domain", "name", "documentation", "dependencies", "codeowners", "config_flow"]
    manifest_keys_ok = check_required_keys(os.path.join(component_dir, "manifest.json"), manifest_required_keys)
    
    # 检查hacs.json的必需键
    hacs_required_keys = ["name", "hacs"]
    hacs_keys_ok = check_required_keys(os.path.join(base_dir, "hacs.json"), hacs_required_keys)
    
    print("\n=== 检查Python文件语法 ===")
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
    
    print("\n=== 结果摘要 ===")
    print(f"目录结构检查: {'✅ 通过' if all_files_exist else '❌ 失败'}")
    print(f"JSON文件验证: {'✅ 通过' if json_valid else '❌ 失败'}")
    print(f"配置键检查: {'✅ 通过' if manifest_keys_ok and hacs_keys_ok else '❌ 失败'}")
    print(f"Python语法检查: {'✅ 通过' if python_valid else '❌ 失败'}")
    
    if all_files_exist and json_valid and manifest_keys_ok and hacs_keys_ok and python_valid:
        print("\n✅ 所有检查通过！集成结构看起来正确。")
        print("您可以尝试在Home Assistant中安装此集成。")
    else:
        print("\n❌ 一些检查失败。请修复上述问题后再尝试安装集成。")

if __name__ == "__main__":
    main() 