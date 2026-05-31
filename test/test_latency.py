"""
test/test_latency.py
--------------------
Table 5 Row 1: End-to-end latency benchmark
测量从"传感器信号输入 shared_state"到"bridge._send() 被调用"的完整路径延迟。

路径：
  1. sensor update → shared_state.update()
  2. context_pipeline._evaluate() → match_context() → _apply_time_overrides()
  3. _generate_token()
  4. on_emotion_change callback → bridge.send_emotion() → bridge._send()

因为正式 pipeline 是每 CHECK_INTERVAL 秒才跑一次，
这里直接调用 _evaluate() 来单独计时，
代表的是"一次完整评估+决策+发指令"的实际耗时。

运行方法：
    cd /Users/jennifer/ANIMA
    python -m test.test_latency
"""

import sys
import os
import time
import statistics

# ── 路径设置 ──────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 预先初始化 bridge（模拟模式，不需要 Arduino）───────────────
from express.serial_bridge import bridge
bridge.connect()   # → simulation mode if no hardware

# ── 初始化 study_manager（_evaluate 内部会引用它）──────────────
from express.study_manager import study_manager
# 确保 is_paused = False，否则 _evaluate 会直接 return
study_manager.is_paused = False

# ── 设置 shared_state：模拟"用户在场且正在打字"的典型状态 ──────
from sense.sensor_state import shared_state
shared_state.force_update("face_present",   True)
shared_state.force_update("speech_active",  False)
shared_state.force_update("audio_category", "silence")
shared_state.force_update("input_rate",     "high")

# 预热：让时间追踪器有合理的初始值
shared_state.update("face_present", False)
shared_state.update("face_present", True)
shared_state.update("input_rate",   "high")
time.sleep(0.05)  # 50ms 让内部计时器稳定

# ── 构造 ContextPipeline，注入计时感知的 callback ──────────────
from understand.context_pipeline import ContextPipeline

received_commands = []   # 记录 callback 是否被触发

def on_emotion_change(emotion_name, scenario, params):
    """模拟 main.py 里的 callback：记录时间戳。"""
    received_commands.append(time.perf_counter())
    # 也发送到模拟 bridge（完整路径）
    bridge.send_emotion(params)

pipeline = ContextPipeline(on_emotion_change=on_emotion_change)

# ── 100 次计时 ────────────────────────────────────────────────
N = 100
latencies_ms = []

print("=" * 55)
print("  PEARL — End-to-end Latency Benchmark  (N=100)")
print("=" * 55)
print("测量路径：shared_state.update() → bridge._send()")
print()

for i in range(N):
    # 模拟传感器信号变化：每次交替 high/medium，触发真实路径
    new_rate = "high" if i % 2 == 0 else "medium"

    # ── START：传感器数据进入系统 ──
    t_start = time.perf_counter()

    shared_state.update("input_rate", new_rate)
    pipeline._evaluate()          # 完整评估 + 可能触发 callback

    # ── END：_send() 内部时间（用 send_emotion 封装计时）──
    t_end = time.perf_counter()

    latency_ms = (t_end - t_start) * 1000
    latencies_ms.append(latency_ms)

    if (i + 1) % 10 == 0:
        print(f"  [{i+1:3d}/100] latest={latency_ms:.2f} ms")

# ── 统计 ──────────────────────────────────────────────────────
mean_ms = statistics.mean(latencies_ms)
sd_ms   = statistics.stdev(latencies_ms)
min_ms  = min(latencies_ms)
max_ms  = max(latencies_ms)
p95_ms  = sorted(latencies_ms)[int(0.95 * N)]

print()
print("=" * 55)
print("  RESULTS")
print("=" * 55)
print(f"  Mean      : {mean_ms:.2f} ms")
print(f"  SD        : {sd_ms:.2f} ms")
print(f"  Min       : {min_ms:.2f} ms")
print(f"  Max       : {max_ms:.2f} ms")
print(f"  95th pct  : {p95_ms:.2f} ms")
print()

# ── Table 5 填表格式 ──────────────────────────────────────────
verdict = "✅ PASS" if mean_ms < 100 else "❌ FAIL"
print(f"  Table 5 Entry → Mean ± SD = {mean_ms:.1f} ± {sd_ms:.1f} ms")
print(f"  Target: mean < 100 ms  →  {verdict}")
print()

# ── 将结果写入 logs/ 供存档 ───────────────────────────────────
import datetime, json
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(log_dir, exist_ok=True)
result = {
    "test":       "end_to_end_latency",
    "timestamp":  datetime.datetime.now().isoformat(),
    "N":          N,
    "mean_ms":    round(mean_ms, 3),
    "sd_ms":      round(sd_ms,   3),
    "min_ms":     round(min_ms,  3),
    "max_ms":     round(max_ms,  3),
    "p95_ms":     round(p95_ms,  3),
    "target_ms":  100,
    "pass":       mean_ms < 100,
    "raw":        [round(v, 3) for v in latencies_ms],
}
out_path = os.path.join(log_dir, "latency_results.json")
with open(out_path, "w") as f:
    json.dump(result, f, indent=2)
print(f"  Raw data saved → {out_path}")
print("=" * 55)
