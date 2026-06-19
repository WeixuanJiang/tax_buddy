import pytest
from pydantic import ValidationError

from knowledge_engine.api.models import RegisterRequest, ChatRequest


def test_register_valid():
    r = RegisterRequest(username="alice_1", password="hunter2pw",
                         occupation="nurse", postcode="3000")
    assert r.username == "alice_1"


@pytest.mark.parametrize("bad", [
    {"username": "al", "password": "hunter2pw", "occupation": "n", "postcode": "3000"},      # too short
    {"username": "has space", "password": "hunter2pw", "occupation": "n", "postcode": "3000"},
    {"username": "alice", "password": "short", "occupation": "n", "postcode": "3000"},        # pw < 8
    {"username": "alice", "password": "hunter2pw", "occupation": "", "postcode": "3000"},      # empty occ
    {"username": "alice", "password": "hunter2pw", "occupation": "n", "postcode": "30a0"},     # bad postcode
    {"username": "alice", "password": "hunter2pw", "occupation": "n", "postcode": "30000"},    # 5 digits
])
def test_register_invalid(bad):
    with pytest.raises(ValidationError):
        RegisterRequest(**bad)


def test_chatrequest_has_no_user_id():
    assert "user_id" not in ChatRequest.model_fields
