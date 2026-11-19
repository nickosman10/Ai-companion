"""Offline tests: no API key, microphone or display needed.

Run with:  python -m pytest tests
"""

from types import SimpleNamespace as NS

import pytest

from companion import brain as brain_mod
from companion.config import Settings
from companion.desktop import split_combo, translate_key
from companion.memory import Memory
from companion.tools import TOOLS, ToolContext, run_tool
from companion.voice import is_stop_command, match_wake_word


# ---------------------------------------------------------------- voice
def test_wake_word_with_request():
    assert match_wake_word("hey buddy open spotify", ["hey buddy", "buddy"]) == "open spotify"


def test_wake_word_alone():
    assert match_wake_word("buddy", ["hey buddy", "buddy"]) == ""


def test_no_wake_word():
    assert match_wake_word("somebody said hello", ["buddy"]) is None


def test_stop_words():
    assert is_stop_command("stop")
    assert is_stop_command("okay please stop")
    assert not is_stop_command("stop motion animation ideas")


# -------------------------------------------------------------- desktop
def test_key_translation():
    assert translate_key("Return") == "enter"
    assert translate_key("super") == "win"
    assert translate_key("Page_Down") == "pagedown"
    assert translate_key("A") == "a"
    assert split_combo("ctrl+shift+T") == ["ctrl", "shift", "t"]
    assert split_combo("ctrl++") == ["ctrl", "+"]
    assert split_combo("+") == ["+"]


# ---------------------------------------------------------------- tools
@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr("companion.memory.MEMORY_FILE", tmp_path / "memory.json")
    monkeypatch.setattr("companion.memory.DATA_DIR", tmp_path)
    spoken = []
    c = ToolContext(memory=Memory(), speak=spoken.append, notify=lambda t: None,
                    confirm=lambda q: False)
    c.spoken = spoken
    return c


def test_memory_roundtrip(ctx):
    run_tool(ctx, "remember", {"fact": "Likes chess"})
    assert "Likes chess" in run_tool(ctx, "recall_memories", {})
    run_tool(ctx, "forget", {"number": 1})
    assert run_tool(ctx, "recall_memories", {}) == "(nothing yet)"


def test_shell_needs_confirmation(ctx):
    out = run_tool(ctx, "run_powershell", {"command": "echo hi", "reason": "test"})
    assert "declined" in out


def test_random_pick(ctx):
    assert run_tool(ctx, "random_pick", {"kind": "coin"}) in ("Heads", "Tails")
    assert run_tool(ctx, "random_pick", {"kind": "choice", "options": ["a"]}) == "a"


def test_tool_schemas_are_valid():
    for t in TOOLS.values():
        d = t.definition()
        assert d["input_schema"]["type"] == "object"
        assert set(d["input_schema"]["required"]) <= set(d["input_schema"]["properties"])


# ---------------------------------------------------------------- brain
def block(type_, **kw):
    return NS(type=type_, **kw)


class FakeClient:
    """Returns scripted responses and records each request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


class FakeDesktop:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def run(self, name, inp):
        self.calls.append(name)
        if name == self.fail_on:
            raise RuntimeError("boom")
        return ("image", "AAAA") if name == "screenshot" else ("text", "OK")


def make_brain(ctx, responses, desktop=None):
    b = brain_mod.Brain.__new__(brain_mod.Brain)
    b.settings = Settings()
    b.ctx = ctx
    b.on_status = lambda s: None
    b.client = FakeClient(responses)
    b.desktop = desktop or FakeDesktop()
    b.messages = []
    import threading

    b.stop_event = threading.Event()
    b.system = "sys"
    b.tools = [{"type": "computer_toolset_20260801"}] + [t.definition() for t in TOOLS.values()]
    return b


def test_plain_reply(ctx):
    b = make_brain(ctx, [NS(content=[block("text", text="Hi there!")], stop_reason="end_turn")])
    assert b.respond("hello") == "Hi there!"
    req = b.client.requests[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["output_config"] == {"effort": "medium"}
    assert req["fallbacks"] == "default"


def test_computer_batch_and_toolset_echo(ctx):
    calls = [
        block("tool_use", id="t1", name="left_click", toolset_name="computer", input={"coordinate": [1, 2]}),
        block("tool_use", id="t2", name="type", toolset_name="computer", input={"text": "x"}),
        block("tool_use", id="t3", name="screenshot", toolset_name="computer", input={}),
        block("tool_use", id="t4", name="get_time", input={}),
    ]
    desktop = FakeDesktop(fail_on="type")
    b = make_brain(ctx, [
        NS(content=calls, stop_reason="tool_use"),
        NS(content=[block("text", text="Done.")], stop_reason="end_turn"),
    ], desktop)
    assert b.respond("do it") == "Done."

    results = b.client.requests[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2", "t3", "t4"]
    assert all(r["toolset_name"] == "computer" for r in results[:3])
    assert "toolset_name" not in results[3]
    assert results[1]["is_error"] and "boom" in results[1]["content"]
    # After a failed computer action the rest of the computer batch is skipped...
    assert results[2]["content"] == brain_mod.NOT_EXECUTED
    assert desktop.calls == ["left_click", "type"]
    # ...but custom tools still run.
    assert not results[3].get("is_error")


def test_say_tool_and_refusal(ctx):
    b = make_brain(ctx, [
        NS(content=[block("tool_use", id="s1", name="say", input={"text": "On it"})], stop_reason="tool_use"),
        NS(content=[], stop_reason="refusal"),
    ])
    assert "can't help" in b.respond("x")
    assert ctx.spoken == ["On it"]


def test_stop_answers_pending_tools(ctx):
    b = make_brain(ctx, [
        NS(content=[block("tool_use", id="a", name="get_time", input={})], stop_reason="tool_use"),
    ])
    # respond() clears the stop flag when a turn starts, so press stop mid-turn.
    orig = b._run_tools

    def stopping(blocks):
        b.stop_event.set()
        return orig(blocks)

    b._run_tools = stopping
    assert "stopped" in b.respond("go").lower()
    last = b.messages[-1]["content"][0]
    assert last["tool_use_id"] == "a" and last["is_error"]


# ---------------------------------------------------------------- skins
def test_default_skin_has_all_animations():
    from companion.skin import ANIMATIONS, load_skin

    s = load_skin("default", 160)
    assert s.size[1] == 160
    for anim in ANIMATIONS:
        assert s.frames[anim] and all(f.size == s.size for f in s.frames[anim])


def test_single_image_skin_is_animated(tmp_path, monkeypatch):
    from PIL import Image

    from companion import skin as skin_mod

    monkeypatch.setattr(skin_mod, "SKINS_DIR", tmp_path)
    (tmp_path / "hero").mkdir()
    img = Image.new("RGBA", (200, 400), (0, 0, 0, 0))
    img.paste((200, 50, 50, 255), (50, 20, 150, 380))
    img.save(tmp_path / "hero" / "hero.png")
    s = skin_mod.load_skin("hero", 120)
    assert len(s.frames["walk"]) == 4
    assert all(f.size == s.size for fs in s.frames.values() for f in fs)


def test_move_yourself_without_pet(ctx):
    assert "turned off" in run_tool(ctx, "move_yourself", {"action": "wave"})
    ctx.pet_command = lambda a: f"Doing: {a}"
    assert run_tool(ctx, "move_yourself", {"action": "wave"}) == "Doing: wave"
