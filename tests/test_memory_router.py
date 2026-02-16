from app.modules.memory.router import parse_explicit_remember, route_memory


def test_parse_explicit_remember_en():
    parsed = parse_explicit_remember("remember this: my favorite color is blue")
    assert parsed is not None
    assert parsed["text"] == "my favorite color is blue"
    assert parsed["memory_kind"] is None


def test_parse_explicit_remember_sv():
    parsed = parse_explicit_remember("kom ihåg detta: min favoritfärg är blå")
    assert parsed is not None
    assert parsed["text"] == "min favoritfärg är blå"


def test_route_memory_procedural():
    routed = route_memory("Step by step workflow: 1. run tests 2. deploy")
    assert routed["memory_kind"] == "procedural"
    assert routed["memory_type"] == "working"


def test_route_memory_session_hint_is_episodic():
    routed = route_memory("we talked about this yesterday", memory_type_hint="session")
    assert routed["memory_kind"] == "episodic"
    assert routed["memory_type"] == "session"
