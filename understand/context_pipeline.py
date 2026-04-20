"""
understand/context_pipeline.py
-------------------------------
慢速理解层：每 CHECK_INTERVAL 秒评估一次场景。

v2 改动：
  - 接入 sensor_state 的三个时间查询方法
  - 新增 Curious/Confused 时间维度区分逻辑
  - 新增 Tired session duration 检查
  - match_context() 现在传入 session_duration_sec
  - 测试模式和正式模式双参数切换
"""

import time
import threading
import datetime
from sense.sensor_state import shared_state
from config.context_rules import match_context
from config.emotions import get_emotion

# ─────────────────────────────────────────
# 模式切换（改这一行切换所有时间参数）
# ─────────────────────────────────────────
MODE = "test"   # "test" 快速验证  |  "real" 正式使用

if MODE == "test":
    CHECK_INTERVAL   = 10     # 每10秒评估一次
    CURIOUS_WINDOW   = 10     # 归零 <10秒 → Curious
    CONFUSED_WINDOW  = 20     # 归零 >20秒 → Confused
    ACTIVE_LOOKBACK  = 60     # 过去1分钟内有没有高活跃
    TIRED_SESSION    = 600    # 在场10分钟 → Tired（测试用，之前60s太短了）
    TIRED_HOUR       = 20     # 晚8点（测试用）
else:
    CHECK_INTERVAL   = 30     # 每30秒评估一次
    CURIOUS_WINDOW   = 90     # 归零 <90秒 → Curious
    CONFUSED_WINDOW  = 180    # 归零 >180秒 → Confused
    ACTIVE_LOOKBACK  = 300    # 过去5分钟内有没有高活跃
    TIRED_SESSION    = 1800   # 在场30分钟 → Tired
    TIRED_HOUR       = 23     # 23:00（正式）


class ContextPipeline:
    def __init__(self, on_emotion_change=None):
        """
        on_emotion_change: callback(emotion_name, scenario_name, params)
        """
        self.on_emotion_change  = on_emotion_change
        self.current_emotion    = "relaxed"
        self.current_scenario   = "Default"
        self.emotion_entered_at = time.time()

        # 每个情绪的最短持续时间（秒）
        # 在此时间内，即使信号变化也不切换情绪
        self.EMOTION_MIN_HOLD = {
            "focus":    30,   # test: 降低到30s
            "happy":    15,   # test: 降低到15s
            "curious":  10,   # test: 降低到10s
            "tired":    20,   # tired 至少保持 20s（播完动画）
            "confused": 15,   # test: 降低到15s
            "listen":   10,   # test: 降低到10s
            "relaxed":  0,
        }

        # 情绪最长持续时间 → 超时后自动回归 relaxed（"一次性提醒"语义）
        # None 表示不限制（情绪会一直保持直到被新信号覆盖）
        self.EMOTION_MAX_HOLD = {
            "tired":    120,  # tired 最多 2 分钟，然后"提醒过了"→ 回 relaxed
            "curious":  60,   # curious 最多 1 分钟，如果没有新活跃 → 回 relaxed
            "confused": 120,  # confused 最多 2 分钟 → 回 relaxed
        }

        # 候选确认机制：同一情绪连续出现 N 次才正式切换（防抖）
        self._pending_emotion   = None
        self._pending_scenario  = None
        self._pending_count     = 0
        self.CONFIRM_THRESHOLD  = 2   # 需要连续 2 次评估（测试模式 20 秒）都认为一样才切换

        self._stop_event = threading.Event()

    # ─────────────────────────────────────────
    # 线程管理
    # ─────────────────────────────────────────

    def start(self):
        thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="ContextPipeline"
        )
        thread.start()
        print(f"[UNDERSTAND] Context pipeline started. MODE={MODE}, interval={CHECK_INTERVAL}s")
        return thread

    def stop(self):
        self._stop_event.set()

    def _run(self):
        while not self._stop_event.is_set():
            time.sleep(CHECK_INTERVAL)
            self._evaluate()

    # ─────────────────────────────────────────
    # 核心评估逻辑
    # ─────────────────────────────────────────

    def _evaluate(self):
        current          = shared_state.get()
        previous         = shared_state.get_prev()
        session_duration = shared_state.get_session_duration()
        inactive_secs    = shared_state.get_inactive_duration()
        active_secs      = shared_state.get_active_duration()
        absent_secs      = shared_state.get_absent_duration()
        was_active       = shared_state.was_recently_active(ACTIVE_LOOKBACK)

        changes = shared_state.count_changes()
        print(f"\n[UNDERSTAND] ── 评估 ── {changes} 个信号变化")
        print(f"  face={current['face_present']} | speech={current['speech_active']} | "
              f"audio={current['audio_category']} | input={current['input_rate']}")
        print(f"  inactive={inactive_secs:.0f}s | session={session_duration:.0f}s | "
              f"was_active={was_active}")

        # ── 第一步：基础规则匹配 ──
        new_emotion, new_scenario = match_context(current, previous)

        # ── 第二步：时间维度覆盖逻辑 ──
        new_emotion, new_scenario = self._apply_time_overrides(
            new_emotion, new_scenario,
            current, inactive_secs, was_active, session_duration, active_secs, absent_secs
        )

        # ── 第三步：生成 token（原始数据到此止步）──
        token = self._generate_token(current, new_emotion, new_scenario)
        print(f"[UNDERSTAND] Token: {token}")

        # ── 第四步：写入记忆 ──
        try:
            from memory.memory_store import save_event
            save_event(token, new_emotion, new_scenario, current)
        except Exception as e:
            print(f"[UNDERSTAND] 记忆写入失败: {e}")

        # ── 第五步：候选确认 + 情绪切换 ──
        # 先用 pending 机制做防抖：同一情绪连续出现 CONFIRM_THRESHOLD 次才切换
        # ── 最长持续时间检查：超时强制回 relaxed ──────────────────
        time_in_current = time.time() - self.emotion_entered_at
        max_hold = self.EMOTION_MAX_HOLD.get(self.current_emotion)
        if max_hold and time_in_current >= max_hold:
            print(f"[UNDERSTAND] ⏰ {self.current_emotion} 超过最长时间 {max_hold}s → 回归 relaxed")
            self.current_emotion    = "relaxed"
            self.current_scenario   = "Idle Ambient"
            self.emotion_entered_at = time.time()
            self._pending_emotion   = None
            self._pending_count     = 0
            shared_state.update("current_emotion", "relaxed")
            if self.on_emotion_change:
                params = get_emotion("relaxed")
                self.on_emotion_change("relaxed", "Idle Ambient", params)
            shared_state.save_snapshot()
            return

        if new_emotion != self.current_emotion:
            if new_emotion == self._pending_emotion:
                self._pending_count += 1
            else:
                # 新候选，重置计数
                self._pending_emotion  = new_emotion
                self._pending_scenario = new_scenario
                self._pending_count    = 1

            if self._pending_count >= self.CONFIRM_THRESHOLD:
                # 候选确认：检查 min_hold
                time_in_current = time.time() - self.emotion_entered_at
                min_hold = self.EMOTION_MIN_HOLD.get(self.current_emotion, 0)

                if time_in_current < min_hold:
                    print(f"[UNDERSTAND] 忽略切换：{self.current_emotion} 只持续了 "
                          f"{int(time_in_current)}s（最少需要 {min_hold}s）")
                else:
                    print(f"[UNDERSTAND] ✅ 情绪切换（{self._pending_count}次确认）："
                          f"{self.current_emotion} → {new_emotion} ({new_scenario})")
                    self.current_emotion    = new_emotion
                    self.current_scenario   = new_scenario
                    self.emotion_entered_at = time.time()
                    shared_state.update("current_emotion", new_emotion)
                    # 重置候选
                    self._pending_emotion = None
                    self._pending_count   = 0

                    if self.on_emotion_change:
                        params = get_emotion(new_emotion)
                        self.on_emotion_change(new_emotion, new_scenario, params)
            else:
                print(f"[UNDERSTAND] 📋 候选({self._pending_count}/{self.CONFIRM_THRESHOLD}）："
                      f"{self.current_emotion} → {new_emotion}，等待确认")
        else:
            # 当前情绪 == 新情绪，重置候选
            self._pending_emotion = None
            self._pending_count   = 0
            print(f"[UNDERSTAND] 情绪不变：{self.current_emotion}")

        # ALWAYS update the public state so Web UI can see it even on late connect
        shared_state.update("current_emotion", self.current_emotion)
        shared_state.save_snapshot()

    # ─────────────────────────────────────────
    # 时间维度覆盖
    # ─────────────────────────────────────────

    def _apply_time_overrides(
        self,
        emotion: str,
        scenario: str,
        current: dict,
        inactive_secs: float,
        was_active: bool,
        session_duration: float,
        active_secs: float,
        absent_secs: float
    ) -> tuple:
        """
        在规则表匹配结果的基础上，应用时间维度逻辑。

        主要处理四种情况：
        1. Curious vs Confused：靠 inactive_secs 区分
        2. Tired：session_duration 超过阈值时触发
        3. Relaxed vs Curious：如果从来没活跃过，不应该是 Curious
        4. Focus / Happy：靠 active_secs 判断持续时间
        5. Long Absence：靠 absent_secs 判断
        """
        
        # ── 覆盖-1：过早的离开（防闪烁） ──────────────
        if scenario == "Long Absence":
            absent_target = 60 if MODE == "test" else 1800
            if absent_secs < absent_target:
                print(f"[UNDERSTAND] 时间拦截：离开 {absent_secs:.0f}s < {absent_target}s → 保持 relaxed")
                return "relaxed", "Idle Ambient"


        # ── 覆盖0：Focus 和 Happy 长时间要求 ────────────────
        if emotion == "focus":
            focus_target = 30 if MODE == "test" else 600
            if active_secs < focus_target:
                print(f"[UNDERSTAND] 时间拦截：活跃 {active_secs:.0f}s < {focus_target}s，Focus不成立 → 保持 relaxed")
                return "relaxed", "Idle Ambient"
                
        if emotion == "happy":
            happy_target = 10 if MODE == "test" else 30
            if active_secs < happy_target:
                print(f"[UNDERSTAND] 时间拦截：活跃 {active_secs:.0f}s < {happy_target}s，Happy不成立 → 保持 relaxed")
                return "relaxed", "Idle Ambient"

        # ── 覆盖1：Curious vs Confused 时间区分 ──────────────
        # 规则表里两个都依赖 requires_transition_from，
        # 这里用时间精确区分
        if emotion in ("curious", "confused"):
            if not was_active:
                # 过去 ACTIVE_LOOKBACK 秒内从来没高活跃过
                # 说明用户本来就一直在低活跃，不是"停下来了"
                # 应该是 Relaxed 而不是 Curious
                print(f"[UNDERSTAND] 覆盖：{emotion} → relaxed（无前置活跃期）")
                return "relaxed", "Idle Ambient"

            if inactive_secs == 0.0:
                # 目前还在活跃，不是 Curious/Confused 状态
                pass

            elif inactive_secs < CURIOUS_WINDOW:
                # 刚停下来不到 CURIOUS_WINDOW 秒 → Curious
                print(f"[UNDERSTAND] 时间覆盖：归零 {inactive_secs:.0f}s < {CURIOUS_WINDOW}s → curious")
                return "curious", "Active Break"

            elif inactive_secs >= CONFUSED_WINDOW:
                # 停了很久 → Confused
                print(f"[UNDERSTAND] 时间覆盖：归零 {inactive_secs:.0f}s >= {CONFUSED_WINDOW}s → confused")
                return "confused", "Stuck"

            else:
                # 灰色地带（CURIOUS_WINDOW ~ CONFUSED_WINDOW）→ 维持 Curious 等待
                print(f"[UNDERSTAND] 时间覆盖：归零 {inactive_secs:.0f}s 在灰色地带 → 维持 curious")
                return "curious", "Active Break"

        # ── 覆盖2：session duration 触发 Tired ────────────────
        # 连续在场超过 TIRED_SESSION 秒触发，但如果已经是 tired 就不再强制（让其他情绪能切换）
        # 在 test 模式下完全禁用此覆盖，用下面的注释行启用
        if MODE != "test":   # test 模式下不靠 session 强制 tired，只靠 Late Night 规则
            if (current["face_present"]
                    and session_duration >= TIRED_SESSION
                    and current["input_rate"] in ("low", "medium")
                    and not current["speech_active"]
                    and emotion not in ("happy", "listen", "focus", "tired")):
                print(f"[UNDERSTAND] 时间覆盖：在场 {session_duration:.0f}s → tired")
                return "tired", "Extended Session"

        return emotion, scenario

    # ─────────────────────────────────────────
    # Token 生成（隐私保护：原始数据在此丢弃）
    # ─────────────────────────────────────────

    def _generate_token(self, state: dict, emotion: str, scenario: str) -> str:
        """
        生成抽象记忆 token。
        格式：<场景, HH:00, Weekday/Weekend, 情绪>

        原始传感器数据不存储，只存这个抽象标签。
        这是隐私保护的关键步骤。
        # RAW SENSOR DATA DISCARDED HERE
        """
        now      = datetime.datetime.now()
        hour_str = f"{now.hour:02d}:00"
        day_type = "Weekend" if now.weekday() >= 5 else "Weekday"
        return f"<{scenario}, {hour_str}, {day_type}, {emotion}>"
