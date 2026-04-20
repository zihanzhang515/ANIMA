from sense.sensor_state import shared_state
shared_state.save_snapshot()
import time; time.sleep(1)
print("Duration:", shared_state.get_state_duration())
