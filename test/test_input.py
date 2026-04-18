import sys
import os
import threading
import time

# 将项目根目录加入到sys.path，以便能够正确导入 sense 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sense.input_monitor import run_input_monitor

def main():
    print("Starting Input Monitor Test...")
    print("请随意敲击键盘或移动/点击鼠标测试活跃度...")
    print("日志会每 10 秒钟结算一次活跃度（Low/Medium/High）")
    print("按 Ctrl+C 退出。\n")
    
    # 创建一个事件用于控制线程结束
    stop_event = threading.Event()
    
    # 在独立线程中运行 input_monitor，这是为了不阻塞主线程
    monitor_thread = threading.Thread(target=run_input_monitor, args=(stop_event,), daemon=True)
    monitor_thread.start()
    
    try:
        # 主线程保持运行并捕获中断信号
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Input Monitor Test...")
        stop_event.set()
        monitor_thread.join(timeout=2)
        print("测试已退出。")

if __name__ == "__main__":
    main()
