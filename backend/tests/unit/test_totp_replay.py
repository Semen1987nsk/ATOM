import time

import pyotp

from services import totp_service


class _FakeUser:
    def __init__(self):
        self.totp_secret = pyotp.random_base32()
        self.totp_last_used_step = None


def test_same_code_rejected_on_replay():
    user = _FakeUser()
    code = pyotp.TOTP(user.totp_secret).now()
    assert totp_service.verify_code_for_user(user, code) is True
    # Повтор того же кода в том же окне — replay, должен быть отклонён.
    assert totp_service.verify_code_for_user(user, code) is False


def test_previous_step_code_rejected_after_current_accepted():
    """Код предыдущего шага (offset -1) отклоняется, если текущий уже принят."""
    user = _FakeUser()
    totp = pyotp.TOTP(user.totp_secret)
    now = int(time.time())
    current_code = totp.at(now)
    prev_code = totp.at(now - 30)

    assert totp_service.verify_code_for_user(user, current_code) is True
    # totp_last_used_step продвинут на текущий шаг → старый шаг уже не пройдёт.
    if prev_code != current_code:
        assert totp_service.verify_code_for_user(user, prev_code) is False
