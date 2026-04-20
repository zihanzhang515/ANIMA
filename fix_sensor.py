import sys, re

file_path = "/Users/jennifer/ANIMA/sense/sensor_state.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add _high_activity_start_time
if "_high_activity_start_time" not in content:
    content = content.replace("self._last_high_activity_time: float = 0.0", 
                              "self._last_high_activity_time: float = 0.0\n        self._high_activity_start_time: float = 0.0")

# 2. Update logic for _high_activity_start_time
target_update = """            if key == "input_rate":
                if value in ("high", "medium"):
                    self._last_high_activity_time = now
                    self._input_zero_since = 0.0   # 重置归零计时
                elif value == "low":
                    if self._input_zero_since == 0.0:
                        self._input_zero_since = now  # 开始计归零时长"""

replacement_update = """            if key == "input_rate":
                if value in ("high", "medium"):
                    self._last_high_activity_time = now
                    self._input_zero_since = 0.0   # 重置归零计时
                    if getattr(self, "_high_activity_start_time", 0.0) == 0.0:
                        self._high_activity_start_time = now
                elif value == "low":
                    self._high_activity_start_time = 0.0
                    if self._input_zero_since == 0.0:
                        self._input_zero_since = now  # 开始计归零时长"""

if target_update in content:
    content = content.replace(target_update, replacement_update)

# 3. Add get_active_duration
if "def get_active_duration" not in content:
    target_insert = """    def get_inactive_duration(self) -> float:"""
    replacement_insert = """    def get_active_duration(self) -> float:
        \"\"\"连续保持 high/medium 活跃的秒数\"\"\"
        with self._lock:
            start_time = getattr(self, "_high_activity_start_time", 0.0)
            if start_time == 0.0:
                return 0.0
            return time.time() - start_time

    def get_inactive_duration(self) -> float:"""
    if target_insert in content:
        content = content.replace(target_insert, replacement_insert)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("sensor_state.py fixed.")
