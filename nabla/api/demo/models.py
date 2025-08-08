from collections import deque
import random
from datetime import datetime

class SensorData:
    def __init__(self):
        # Room temperature range (adjust if you live in Antarctica)
        self.min_temp = 18.0
        self.max_temp = 26.0
        self.min_humidity = 30.0
        self.max_humidity = 65.0

    def generate_reading(self):
        return {
            "timestamp": datetime.now().isoformat(),
            "temperature": round(random.uniform(self.min_temp, self.max_temp), 1),
            "humidity": round(random.uniform(self.min_humidity, self.max_humidity), 1),
            "status": random.choice(["normal", "warning", "critical"])
        }
# Store the last 20 readings (because nobody cares about data from 1995)
recent_readings = deque(maxlen=20)
