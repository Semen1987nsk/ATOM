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
