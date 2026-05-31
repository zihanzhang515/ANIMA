"""
test/test_privacy.py
--------------------
Table 5 Row 4: Tokenisation & Privacy Verification

验证两件事：
1. events 表里有新记录（tokenisation 工作正常）
2. 原始传感器 buffer 在每次 token 生成后不会被持久化
   （sensor_state 只持有当前帧，没有历史 raw data）

运行方法：
    cd /Users/jennifer/ANIMA
    python -m test.test_privacy
"""

import sys
import os
import sqlite3
import time
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("  PEARL — Tokenisation & Privacy Verification")
print("=" * 60)

# ─────────────────────────────────────────────────────────────
# STEP 1: 记录 events 表的 baseline 行数
# ─────────────────────────────────────────────────────────────
from memory.memory_store import DB_PATH, get_connection, save_event

conn = get_connection()
baseline_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
conn.close()
print(f"\n[STEP 1] Baseline: events table has {baseline_count} rows")

# ─────────────────────────────────────────────────────────────
# STEP 2: 模拟一次 session — 写入一个 token
# ─────────────────────────────────────────────────────────────
now      = datetime.datetime.now()
hour_str = f"{now.hour:02d}:00"
day_type = "Weekend" if now.weekday() >= 5 else "Weekday"
test_token = f"<DeepFocus, {hour_str}, {day_type}, focus>"

# 模拟 raw sensor state（就是 context_pipeline 传给 save_event 的那个 dict）
fake_raw_state = {
    "face_present":   True,
    "face_x":         0.47,
    "face_size":      0.23,
    "speech_active":  False,
    "audio_category": "silence",
    "input_rate":     "high",
    "current_emotion":"relaxed",
}

save_event(test_token, "focus", "DeepFocus", fake_raw_state)
print(f"\n[STEP 2] Simulated token written: {test_token}")

# ─────────────────────────────────────────────────────────────
# STEP 3: 验证 events 表增加了一行，且存储的是 token 不是 raw data
# ─────────────────────────────────────────────────────────────
conn = get_connection()
new_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
latest = conn.execute(
    "SELECT * FROM events ORDER BY id DESC LIMIT 1"
).fetchone()
conn.close()

print(f"\n[STEP 3] events table now has {new_count} rows (+{new_count - baseline_count})")
print(f"         Latest row:")
print(f"           id        = {latest['id']}")
print(f"           token     = {latest['token']}")
print(f"           emotion   = {latest['emotion']}")
print(f"           scenario  = {latest['scenario']}")
print(f"           hour      = {latest['hour_of_day']}")
print(f"           day_type  = {latest['day_type']}")

# 关键检查：确认 raw sensor 字段（face_x, face_size 等）没有出现在 DB 里
conn2 = get_connection()
cursor = conn2.execute("PRAGMA table_info(events)")
columns = [row[1] for row in cursor.fetchall()]
conn2.close()

raw_fields = ["face_x", "face_size", "audio_rms", "speech_active", "input_rate"]
leaked = [f for f in raw_fields if f in columns]

print(f"\n         events table columns: {columns}")
if leaked:
    print(f"  ⚠️  RAW FIELDS FOUND IN DB: {leaked}  ← PRIVACY ISSUE")
else:
    print(f"  ✅ No raw sensor fields in DB — only abstract tokens stored")

# ─────────────────────────────────────────────────────────────
# STEP 4: 验证 sensor_state 没有持久化 raw buffer
#         SensorState 只保留"当前帧"，没有历史列表
# ─────────────────────────────────────────────────────────────
from sense.sensor_state import shared_state

# 检查内部属性里有没有 list-type 的历史 buffer
raw_buffers = {}
for attr_name in vars(shared_state):
    val = getattr(shared_state, attr_name)
    if isinstance(val, list):
        raw_buffers[attr_name] = val

print(f"\n[STEP 4] SensorState internal attributes (list buffers):")
if raw_buffers:
    for k, v in raw_buffers.items():
        print(f"  ⚠️  {k} = {v}  ← raw history buffer found")
else:
    print(f"  ✅ No list buffers — SensorState is single-frame only (no raw history)")

# 也检查 _state dict 本身
state_snapshot = shared_state.get()
print(f"\n         Current _state snapshot (single frame, not accumulated):")
for k, v in state_snapshot.items():
    print(f"    {k:20s} = {v}")

# ─────────────────────────────────────────────────────────────
# STEP 5: 查看最近 5 条 events（展示 token 格式）
# ─────────────────────────────────────────────────────────────
print(f"\n[STEP 5] Most recent 5 events in DB:")
conn = get_connection()
rows = conn.execute(
    "SELECT id, token, emotion, day_type FROM events ORDER BY id DESC LIMIT 5"
).fetchall()
conn.close()

for row in rows:
    print(f"  #{row['id']:4d} | {row['token']:<45s} | {row['emotion']:<10s} | {row['day_type']}")

# ─────────────────────────────────────────────────────────────
# 总结
# ─────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("  SUMMARY")
print("=" * 60)
check1 = new_count > baseline_count
check2 = len(leaked) == 0
check3 = len(raw_buffers) == 0

print(f"  [{'✅' if check1 else '❌'}] events table records new tokens      : {new_count} rows (was {baseline_count})")
print(f"  [{'✅' if check2 else '❌'}] No raw sensor fields stored in DB")
print(f"  [{'✅' if check3 else '❌'}] No raw history buffer in SensorState")
print()

if check1 and check2 and check3:
    print("  Table 5 Entry → Tokenisation & Privacy : ✅ COMPLETE")
else:
    print("  Table 5 Entry → ⚠️  Some checks failed, see above")
print("=" * 60)
