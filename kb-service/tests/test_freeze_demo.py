from datetime import datetime, timedelta

from freezegun import freeze_time


def test_time_is_frozen():
    with freeze_time("2026-01-01 12:00:00"):
        assert datetime.now() == datetime(2026, 1, 1, 12, 0, 0)


def test_time_can_tick():
    with freeze_time("2026-01-01 12:00:00") as ft:
        ft.tick(timedelta(minutes=30))
        assert datetime.now() == datetime(2026, 1, 1, 12, 30, 0)
