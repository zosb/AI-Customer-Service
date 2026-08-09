from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.deps import get_current_admin


def test_admin_dependency_accepts_admin():
    user = SimpleNamespace(role="admin")
    assert get_current_admin(user) is user


def test_admin_dependency_rejects_normal_user():
    with pytest.raises(HTTPException) as exc:
        get_current_admin(SimpleNamespace(role="user"))
    assert exc.value.status_code == 403
    assert exc.value.detail == "需要管理员权限"
