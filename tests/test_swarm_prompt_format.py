from app.modules.swarm.prompt_format import serialize_for_prompt


def test_serialize_for_prompt_truncates_large_payload():
    payload = {
        "items": [
            {
                "doc_id": f"d{i}",
                "text_snippet": "x" * 2000,
                "nested": {"reason": "y" * 1200},
            }
            for i in range(40)
        ]
    }
    rendered, meta = serialize_for_prompt(payload, max_chars=1800, max_list_items=12, max_text_chars=300)
    assert isinstance(rendered, str)
    assert len(rendered) <= 1800
    assert meta["truncated"] is True
    assert meta["chars_raw"] >= meta["chars_final"]


def test_serialize_for_prompt_is_stable_json():
    payload = {"b": 2, "a": {"z": 1, "y": 2}}
    rendered1, _ = serialize_for_prompt(payload, max_chars=1000)
    rendered2, _ = serialize_for_prompt(payload, max_chars=1000)
    assert rendered1 == rendered2
    assert rendered1.startswith("{")
    assert "\"a\"" in rendered1 and "\"b\"" in rendered1
