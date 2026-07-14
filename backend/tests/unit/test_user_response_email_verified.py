from schemas import UserResponse


def test_user_response_exposes_email_verified():
    assert "email_verified" in UserResponse.model_fields
