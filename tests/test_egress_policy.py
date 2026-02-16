import re

from app.modules.privacy.egress_policy import apply_egress_policy


def test_egress_policy_off_keeps_text(monkeypatch):
    monkeypatch.setenv("EGRESS_PII_POLICY", "off")
    monkeypatch.setenv("EGRESS_PII_APPLY_TO_CHATGPT", "1")

    decision = apply_egress_policy("mail me at reporter@example.com", provider="chatgpt")
    assert decision.text == "mail me at reporter@example.com"
    assert decision.transformed is False
    assert decision.reason_codes == ["allow.egress_policy_off"]


def test_egress_policy_provider_disabled(monkeypatch):
    monkeypatch.setenv("EGRESS_PII_POLICY", "redact")
    monkeypatch.setenv("EGRESS_PII_APPLY_TO_OLLAMA", "0")

    text = "Call +46 70 123 45 67"
    decision = apply_egress_policy(text, provider="ollama")
    assert decision.text == text
    assert decision.reason_codes == ["allow.provider_filter_disabled.ollama"]
    assert decision.transformed is False


def test_egress_policy_pseudonymizes_with_stable_tokens(monkeypatch):
    monkeypatch.setenv("EGRESS_PII_POLICY", "pseudonymize")
    monkeypatch.setenv("EGRESS_PII_APPLY_TO_CHATGPT", "1")
    monkeypatch.setenv("EGRESS_PII_TOKEN_SALT", "seed-1")

    text = "Email jane@example.com and jane@example.com, phone +46 70 123 45 67"
    decision = apply_egress_policy(text, provider="chatgpt")
    assert decision.transformed is True
    assert decision.transform_count == 3
    assert "transform.pseudonymize.email" in decision.reason_codes
    assert "transform.pseudonymize.phone" in decision.reason_codes
    assert "jane@example.com" not in decision.text
    matches = re.findall(r"\[PII_EMAIL_[0-9a-f]{10}\]", decision.text)
    assert len(matches) == 2
    assert matches[0] == matches[1]
    assert re.search(r"\[PII_PHONE_[0-9a-f]{10}\]", decision.text)


def test_egress_policy_redacts_known_categories(monkeypatch):
    monkeypatch.setenv("EGRESS_PII_POLICY", "redact")
    monkeypatch.setenv("EGRESS_PII_APPLY_TO_OLLAMA", "1")

    text = "IP 127.0.0.1 and id 19800101-1234"
    decision = apply_egress_policy(text, provider="ollama")
    assert decision.transformed is True
    assert "[REDACTED_IP_ADDRESS]" in decision.text
    assert "[REDACTED_SE_PERSONNUMMER]" in decision.text
    assert "transform.redact.ip_address" in decision.reason_codes
    assert "transform.redact.se_personnummer" in decision.reason_codes
