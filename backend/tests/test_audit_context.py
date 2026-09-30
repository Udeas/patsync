from app.audit.context import AuditActor, get_actor, is_explicit, mark_explicit, set_actor


class _FakeSession:
    def __init__(self):
        self.info = {}


def test_actor_set_and_get() -> None:
    set_actor(5, "admin")
    actor = get_actor()
    assert actor == AuditActor(user_id=5, username="admin")


def test_actor_defaults_none_after_clear() -> None:
    set_actor(None, None)
    assert get_actor() == AuditActor(user_id=None, username=None)


def test_session_explicit_marker() -> None:
    s = _FakeSession()
    assert is_explicit(s, "patent", 7) is False
    mark_explicit(s, "patent", 7)
    assert is_explicit(s, "patent", 7) is True
    assert is_explicit(s, "design", 7) is False
