"""Prompt persistence, precedence and analyst consistency (mocked LLM)."""
import pytest

from app.prompts import DEFAULT_PROMPT, PRESETS, resolve_system_prompt


def chat(c, sid="s", msg="m", **extra):
    return c.post("/chat", json={"session_id": sid, "message": msg, **extra})


def system_of(fake_llm):
    return fake_llm.calls[-1]["messages"][0]["content"]


# ---- 1. custom prompt survives a follow-up that repeats analyst_type ----------------

def test_custom_prompt_persists_when_followup_repeats_analyst_type(client, fake_llm):
    assert chat(client, "s", "first", analyst_type="customer", system_prompt="MY CUSTOM PROMPT").status_code == 200
    assert system_of(fake_llm) == "MY CUSTOM PROMPT"
    assert chat(client, "s", "second", analyst_type="customer").status_code == 200
    assert system_of(fake_llm) == "MY CUSTOM PROMPT"  # not replaced by the preset
    assert system_of(fake_llm) != PRESETS["customer"]
    third = fake_llm.calls[-1]["messages"]
    assert [m["role"] for m in third] == ["system", "user", "assistant", "user"]  # history intact


# ---- 2. analyst consistency -----------------------------------------------------------

def test_switching_analyst_on_existing_session_is_422_and_not_persisted(client, fake_llm):
    chat(client, "s", "one", analyst_type="customer")
    calls_before = len(fake_llm.calls)
    r = chat(client, "s", "two", analyst_type="workplace")
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, str) and "customer" in detail and "workplace" in detail
    assert len(fake_llm.calls) == calls_before  # LLM never called
    msgs = client.get("/sessions/s/messages").json()["messages"]
    assert [m["content"] for m in msgs] == ["one", "echo:one"]  # nothing added
    # session still works with its own analyst, and prompt unchanged
    assert chat(client, "s", "three", analyst_type="customer").status_code == 200
    assert system_of(fake_llm) == PRESETS["customer"]


def test_switch_rejected_even_when_new_system_prompt_supplied(client, fake_llm):
    chat(client, "s", "one", analyst_type="customer", system_prompt="ORIGINAL")
    r = chat(client, "s", "two", analyst_type="patterns", system_prompt="OTHER")
    assert r.status_code == 422
    chat(client, "s", "three")
    assert system_of(fake_llm) == "ORIGINAL"


def test_same_analyst_with_new_prompt_updates_prompt_keeps_history(client, fake_llm):
    chat(client, "s", "one", analyst_type="customer", system_prompt="OLD")
    chat(client, "s", "two", analyst_type="customer", system_prompt="NEW")
    assert system_of(fake_llm) == "NEW"
    assert len(fake_llm.calls[-1]["messages"]) == 1 + 2 + 1
    chat(client, "s", "three")  # follow-up without prompt keeps NEW
    assert system_of(fake_llm) == "NEW"


def test_new_sessions_can_use_different_analysts(client, fake_llm):
    chat(client, "a", analyst_type="customer")
    chat(client, "b", analyst_type="workplace")
    assert system_of(fake_llm) == PRESETS["workplace"]


def test_session_without_analyst_can_adopt_one_but_prompt_is_unchanged(client, fake_llm):
    chat(client, "s", "one")  # default prompt stored, no analyst
    assert chat(client, "s", "two", analyst_type="customer").status_code == 200
    assert system_of(fake_llm) == DEFAULT_PROMPT  # stored prompt outranks the preset
    assert chat(client, "s", "three", analyst_type="workplace").status_code == 422  # now locked


def test_analyst_type_persisted_in_sessions_table(client, settings):
    chat(client, "s", analyst_type="patterns")
    from app.db import Database
    assert Database(settings.database_path).get_session("s")["analyst_type"] == "patterns"


# ---- 3. precedence (unit) ---------------------------------------------------------------

@pytest.mark.parametrize("req,stored,analyst,expected", [
    ("NEW", "STORED", "customer", "NEW"),                       # 1 new request prompt
    (None, "STORED", "customer", "STORED"),                     # 2 stored prompt
    (None, None, "customer", PRESETS["customer"]),              # 3 preset (new session)
    (None, None, None, DEFAULT_PROMPT),                         # 4 default
    (None, None, "bogus", DEFAULT_PROMPT),
])
def test_resolve_precedence(req, stored, analyst, expected):
    assert resolve_system_prompt(req, stored, analyst) == expected
