"""The panel knows the `file` task channel, or a file-channel doer's run reads as nothing (I1).

The panel admits a task-channel fact only in a closed shape: the channel, its bound, the unit and
the scope that bound measures, all four, and a channel the server cannot have declared is refused.
A fact it does not know makes the whole preview, and the whole controls answer, `null`, so the
run's grant review and its controls would vanish for the run of any provider that takes its task
by file. What is held, under the real Studio modules and Node:

- the shape: `file` is admitted with `utf8_bytes` and `task`, exactly as `stdin` is, and with
  nothing else; the channel the transport profile declares must be the channel of the fact;
- the controls answer carries it in and hands it back;
- the two notes that say it (the grant review and the document form) exist in both languages
  and take the one parameter each sentence needs.

Node is required; the helper skips without it, which a green run here must not be counted as.
"""
from __future__ import annotations

from tests.desk_node import run_js
from tests.test_policy_runtime import ASK, setup
from tests.test_studio_automation import js, wire

FILE = {"channel": "file", "limit": 262144, "unit": "utf8_bytes", "scope": "task"}


def test_the_closed_shape_admits_the_file_channel_with_its_unit_and_scope_and_nothing_else():
    verdicts = run_js("""
      const ok = (value) => providers.taskChannelShape(value);
      console.log(JSON.stringify([ok(d), ok({...d, unit: "utf16_units"}),
        ok({...d, scope: "command_line"}), ok({...d, limit: 0}), ok({...d, extra: 1}),
        ok({...d, channel: "pipe"}), ok({...d, channel: "files"})]));
    """, {"providers": "studio-automation-providers.js"}, FILE)

    assert verdicts == [True, False, False, False, False, False, False]


def test_a_file_fact_is_admitted_only_with_its_own_declared_channel(tmp_path):
    """The preview of a real grant: the fact and the channel the profile declares must agree."""
    from conductor.command.adapters.provider import ProviderConfig
    from conductor.command.policy_providers import ProviderAuthority
    from tests.test_command_provider_contract import _contract
    f = setup(tmp_path)
    config = ProviderConfig("claude-code", "/opt/claude/bin/claude", "fake-claude-jsonl-v1",
                            env_allow=("ANTHROPIC_API_KEY",))
    authority = ProviderAuthority([config], [_contract(auth="api_key")], f.registry)
    f.policy.provider_digest = authority.digest
    f.policy.provider_facts = authority.facts
    payload = wire(tmp_path / "separate")
    payload["preview"] = f.policy.preview("run", ASK)
    payload["file"] = FILE

    result = js("""
      const row = p.preview.provider_facts.providers[0], file = p.file;
      const trial = (transport, value) => { row.transport = transport; row.task_channel = value;
        return Boolean(model.projectAutomationPreview(p.preview, p.read)); };
      console.log(JSON.stringify([trial({task_channel: "file"}, file),
        trial({task_channel: "stdin"}, file),
        trial({task_channel: "file"}, {...file, channel: "stdin"}),
        trial({task_channel: "file"}, {...file, unit: "utf16_units"}),
        trial({task_channel: "file"}, {...file, scope: "command_line"}),
        trial({task_channel: "file"}, {...file, limit: 0}),
        trial({task_channel: "file"}, {...file, extra: 1}), trial({}, file),
        trial({task_channel: "file"}, null)]));
    """, payload)

    assert result == [True, False, False, False, False, False, False, False, False]


def test_the_controls_answer_carries_the_file_channel_in_and_hands_it_back():
    done = run_js("""
      const read = (value) => controls.projectControls({providers: [], isolation_facts: [],
        instances: [{instance_id: 'doer', adapter_id: 'grok-build', model: null, controls: [],
          argument_schemas: {}, isolation: {}, task_channel: value}]});
      const kept = read(d);
      console.log(JSON.stringify([kept === null ? null : controls.wireControls(kept)
        .instances[0].task_channel, [{...d, unit: 'utf16_units'}, {...d, scope: 'command_line'},
        {...d, limit: 0}, {...d, extra: 1}, {...d, channel: 'pipe'}]
        .map((value) => read(value) === null)]));
    """, {"controls": "studio-controls.js"}, FILE)

    assert done == [FILE, [True] * 5]


def test_the_two_notes_that_say_the_file_channel_exist_in_both_languages():
    said = run_js("""
      const take = (key, params) => ['en', 'ru'].map((locale) => {
        try { return copy.message(locale, key, params); } catch (error) { return null; } });
      console.log(JSON.stringify([copy.validateMessages(copy.MESSAGES),
        take('automation.task_channel_file', {limit: '262144'}),
        take('run_docs.channel_file', {adapter: 'doer', limit: '262144'})]));
    """, {"copy": "studio-i18n.js"})

    assert said[0] is True
    assert said[1] == [
        "Task channel: a file in the folder of the attempt itself. The whole task — instruction, "
        "input documents and any correction included — must fit in 262144 UTF-8 bytes; a larger "
        "task is refused before it starts.",
        "Канал задачи: файл в папке самой попытки. Вся задача — с инструкцией, входными "
        "документами и замечаниями для исправления — должна уместиться в 262144 байт UTF-8; "
        "более крупная задача отклоняется до запуска."]
    assert said[2] == [
        "doer receives its task as a file in the folder of its own attempt: the whole task — this "
        "document, the instruction and every other input included — must fit in 262144 bytes of "
        "UTF-8. A larger task is refused before it starts.",
        "doer получает задачу файлом в папке своей попытки: вся задача — вместе с этим "
        "документом, инструкцией и остальными входами — должна уместиться в 262144 байт UTF-8. "
        "Более крупная задача отклоняется до запуска."]
