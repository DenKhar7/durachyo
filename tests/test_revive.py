from bot.revive import in_quiet_hours


def test_quiet_hours_plain_range():
    assert in_quiet_hours(3, "1-10")
    assert not in_quiet_hours(10, "1-10")
    assert not in_quiet_hours(0, "1-10")


def test_quiet_hours_over_midnight():
    assert in_quiet_hours(23, "22-8")
    assert in_quiet_hours(2, "22-8")
    assert not in_quiet_hours(12, "22-8")


def test_quiet_hours_disabled():
    assert not in_quiet_hours(5, "0-0")
