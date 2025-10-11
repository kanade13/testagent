#!/usr/bin/env python3
#start_test.py
"""
测试启动脚本
用于启动FastAPI服务器并测试WebSocket交互
"""
import subprocess
import sys
import time
import os

def install_dependencies():
    """从 requirements.txt 安装所有依赖"""
    print("📦 正在从 requirements.txt 安装依赖包...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        print("✅ 所有依赖已安装")
    except subprocess.CalledProcessError as e:
        print(f"❌ 安装依赖失败: {e}")
        # 可以在这里决定是否要退出
        sys.exit(1)

def start_server():
    """启动FastAPI服务器"""
    print("🚀 启动FastAPI服务器...")
    try:
        # 设置环境变量
        env = os.environ.copy()
        env["PYTHONPATH"] = "."
        
        # 启动uvicorn服务器
        cmd = [sys.executable, "-m", "uvicorn", "app.main:app",
       "--host", "0.0.0.0", "--port", "24000", "--reload"]

        print(f"执行命令: {' '.join(cmd)}")
        
        process = subprocess.Popen(cmd, env=env)
        print(f"✅ 服务器已启动，PID: {process.pid}")
        print("📝 服务器地址: http://localhost:24000")
        print("📝 WebSocket地址: ws://localhost:24000/ws/case")
        print("📝 API文档: http://localhost:24000/docs")
        
        return process
    except Exception as e:
        print(f"❌ 启动服务器失败: {e}")
        return None

def main():
    print("=== TestAgent WebSocket 交互测试 ===\n")
    
    # 检查依赖
    #install_dependencies()
    
    # 启动服务器
    server_process = start_server()
    
    if server_process:
        try:
            print("\n⏰ 等待服务器启动完成...")
            time.sleep(3)
            
            print("\n📋 测试指南:")
            print("1. 服务器启动后，打开另一个终端")
            print("2. 运行: python test_websocket_client.py")
            print("3. 观察WebSocket交互过程")
            print("4. 按 Ctrl+C 停止服务器")
            
            # 等待用户中断
            server_process.wait()
            
        except KeyboardInterrupt:
            print("\n🛑 停止服务器...")
            server_process.terminate()
            server_process.wait()
            print("✅ 服务器已停止")

if __name__ == "__main__":
    main()