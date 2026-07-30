import pytest
from app.auth import new_auth

def test_new_auth_read():
    assert new_auth('user_id', scope='read') == True

def test_new_auth_write():
    assert new_auth('user_id', scope='write') == True


def test_new_auth_invalid_scope():
    with pytest.raises(ValueError):
        new_auth('user_id', scope='invalid')
