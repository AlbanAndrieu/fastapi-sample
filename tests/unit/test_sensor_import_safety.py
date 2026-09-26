"""Import-safety contracts for the demo sensor module."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SENSOR = ROOT / "nabla" / "api" / "demo" / "sensor.py"
LIFESPAN = ROOT / "nabla" / "lifespan.py"


def test_sensor_demo_objects_are_not_constructed_at_module_import() -> None:
    source = SENSOR.read_text(encoding="utf-8")

    assert "\nsensor = SensorData()" not in source
    assert "\nchart_factory = ChartFactory()" not in source
    assert "def initialize_sensor_demo()" in source


def test_sensor_demo_initialization_is_owned_by_application_lifespan() -> None:
    source = LIFESPAN.read_text(encoding="utf-8")

    assert "initialize_sensor_demo()" in source
