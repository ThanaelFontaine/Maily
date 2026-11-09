"""scripts/check_workflows.py: the workflows run on GitHub-hosted runners only, with every action
pinned by a full commit SHA. Each refused form is tried on both checks (text, then structure):
the guard must fail when either one finds something."""
import importlib.util
import pathlib
import textwrap

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHA = "fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09"
PINNED = f"actions/checkout@{SHA}"


def _cw():
    spec = importlib.util.spec_from_file_location("check_workflows", ROOT / "scripts" / "check_workflows.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CW = _cw()


def workflow(runs_on="runs-on: ubuntu-latest", step=f"- uses: {PINNED}", extra=""):
    """A small workflow with one job; `runs_on` and `step` are written as they are."""
    return (
        "name: t\n"
        "on: push\n"
        "jobs:\n"
        "  one:\n"
        f"    {runs_on}\n"
        f"{textwrap.indent(extra, '    ')}"
        "    steps:\n"
        f"      {step}\n"
    )


def found(text):
    """Every problem of both checks, as the guard prints them."""
    return CW.text_problems(text) + CW.structure_problems(text)


def only_text(text):
    return CW.text_problems(text)


def only_structure(text):
    return CW.structure_problems(text)


# ---- accepted -----------------------------------------------------------------------------


@pytest.mark.parametrize("runs_on", [
    "runs-on: ubuntu-latest",
    "runs-on: ubuntu-24.04",
    "runs-on: macos-latest",
    "runs-on: windows-latest",
    "runs-on: 'ubuntu-latest'",
    'runs-on: "ubuntu-latest"',
    "runs-on: [ubuntu-latest]",
    "runs-on:\n      - ubuntu-latest",
])
def test_a_github_hosted_label_is_accepted(runs_on):
    assert found(workflow(runs_on)) == []


def test_the_matrix_of_the_tests_workflow_is_accepted():
    text = workflow("runs-on: ${{ matrix.os }}", extra="strategy:\n  matrix:\n    os: [macos-latest, ubuntu-latest]\n")
    assert found(text) == []


def test_a_matrix_include_with_hosted_labels_is_accepted():
    extra = "strategy:\n  matrix:\n    include:\n      - os: ubuntu-latest\n      - os: macos-latest\n"
    assert found(workflow("runs-on: ${{ matrix.os }}", extra=extra)) == []


@pytest.mark.parametrize("step", [
    f"- uses: {PINNED} # v5.1.0",
    f"- uses: '{PINNED}'",
    "- uses: astral-sh/setup-uv@d0cc045d04ccac9d8b7881df0226f9e82c39688e",
    "- uses: actions/cache/restore@d0cc045d04ccac9d8b7881df0226f9e82c39688e",
    "- run: echo hello",
    "- run: |\n          echo hello\n          uses nothing",
])
def test_pinned_actions_and_run_steps_are_accepted(step):
    assert found(workflow(step=step)) == []


def test_a_local_reusable_workflow_is_accepted():
    text = "name: t\non: push\njobs:\n  call:\n    uses: ./.github/workflows/build.yml\n    with:\n      ref: main\n"
    assert found(text) == []


def test_the_deny_flag_of_gh_attestation_is_accepted_but_not_the_word_beside_it():
    run = "- run: gh attestation verify f --repo a/b --deny-self-hosted-runners"
    assert found(workflow(step=run)) == []
    assert found(workflow(step="- run: echo self-hosted"))
    assert found(workflow(step=run + " self-hosted"))


# ---- refused: runners ---------------------------------------------------------------------


@pytest.mark.parametrize("runs_on", [
    "runs-on: self-hosted",
    "runs-on: [self-hosted, macOS]",
    "runs-on: [self-hosted]",
    "runs-on: ['self-hosted', 'macOS']",
    "runs-on:\n      - self-hosted\n      - macOS",
    "runs-on:\n      - self-hosted",
    "runs-on: SELF-HOSTED",
    "runs-on: macos-mini",
    "runs-on: [ubuntu-latest, macOS]",
    "runs-on: ${{ inputs.runner }}",
    "runs-on: ${{ github.repository_owner && 'macos-mini' }}",
    "runs-on:\n      group: my-group",
    "runs-on:\n      labels: [macOS]",
    "runs-on: {group: my-group}",
    'runs-on: "self\\x2dhosted"',
    'runs-on: "self\\u002dhosted"',
])
def test_a_runner_that_is_not_hosted_by_github_is_refused(runs_on):
    assert found(workflow(runs_on))


def test_a_job_without_runs_on_is_refused():
    text = "name: t\non: push\njobs:\n  one:\n    steps:\n      - run: echo\n"
    assert only_structure(text)


def test_runs_on_hidden_in_a_comment_or_another_form_is_refused():
    assert only_text(workflow("# runs-on: self-hosted\n    runs-on: ubuntu-latest"))
    assert only_text(workflow("# runs-on is ubuntu-latest\n    runs-on: ubuntu-latest"))
    assert only_text(workflow("runs-on: ubuntu-latest  # self-hosted"))
    assert only_text(workflow("? runs-on\n    : ubuntu-latest"))


def test_the_word_self_hosted_is_refused_in_a_name_a_string_or_a_comment():
    assert found(workflow(step="- run: echo ok\n        name: self-hosted"))
    assert found(workflow(step="- run: echo ok\n        name: 'self-hosted'"))
    assert found("# self-hosted\n" + workflow())


@pytest.mark.parametrize("extra", [
    # a label that is not hosted, in the list
    "strategy:\n  matrix:\n    os: [ubuntu-latest, self-hosted]\n",
    "strategy:\n  matrix:\n    os: [ubuntu-latest, macos-mini]\n",
    "strategy:\n  matrix:\n    os:\n      - ubuntu-latest\n      - macos-mini\n",
    # a label that is not hosted, in include
    "strategy:\n  matrix:\n    os: [ubuntu-latest]\n    include:\n      - os: macos-mini\n",
    "strategy:\n  matrix:\n    include:\n      - os: ubuntu-latest\n      - os: macos-mini\n",
    # a matrix that cannot be read
    "strategy:\n  matrix: ${{ fromJSON(inputs.m) }}\n",
    "strategy:\n  matrix:\n    os: ${{ inputs.os }}\n",
    "strategy:\n  matrix:\n    os: ubuntu-latest\n",
    "strategy:\n  matrix:\n    other: [ubuntu-latest]\n",
    "strategy:\n  fail-fast: false\n",
    "strategy:\n  matrix:\n    os: [ubuntu-latest]\n    include: ${{ inputs.more }}\n",
    "strategy:\n  matrix:\n    os: [ubuntu-latest, {label: macos-mini}]\n",
    "strategy:\n  matrix:\n    os: [ubuntu-latest, 5]\n",
])
def test_a_matrix_runner_is_resolved_and_every_value_must_be_hosted(extra):
    assert only_structure(workflow("runs-on: ${{ matrix.os }}", extra=extra))


def test_a_matrix_reference_to_a_key_that_is_not_in_the_matrix_is_refused():
    extra = "strategy:\n  matrix:\n    os: [ubuntu-latest]\n"
    assert only_structure(workflow("runs-on: ${{ matrix.runner }}", extra=extra))


def test_a_matrix_value_naming_self_hosted_is_refused_by_both_checks():
    extra = "strategy:\n  matrix:\n    os: [ubuntu-latest, self-hosted]\n"
    text = workflow("runs-on: ${{ matrix.os }}", extra=extra)
    assert only_text(text) and only_structure(text)


# ---- refused: actions ---------------------------------------------------------------------


@pytest.mark.parametrize("target", [
    "actions/checkout@v5",
    "actions/checkout@v5.1.0",
    "actions/checkout@main",
    "actions/checkout",
    f"actions/checkout@{SHA[:39]}",
    f"actions/checkout@{SHA}0",
    f"actions/checkout@{SHA.upper()}",
    "actions/checkout@" + "g" * 40,
    f"actions/checkout@{SHA}@v5",
    "docker://alpine:3.20",
    f"docker://alpine@sha256:{'a' * 64}",
    f"other/repo/.github/workflows/ci.yml@{SHA}",
    "./.github/actions/mine",
    "./local-action",
    "../outside",
])
def test_an_action_without_a_full_sha_or_a_local_action_is_refused(target):
    text = workflow(step=f"- uses: {target}")
    assert only_text(text) and only_structure(text)


def test_a_job_that_calls_a_workflow_of_another_repository_is_refused():
    text = f"name: t\non: push\njobs:\n  call:\n    uses: other/repo/.github/workflows/ci.yml@{SHA}\n"
    assert only_text(text) and only_structure(text)


def test_a_job_that_calls_a_local_path_that_is_not_a_workflow_is_refused():
    text = "name: t\non: push\njobs:\n  call:\n    uses: ./somewhere/else.yml\n"
    assert only_text(text) and only_structure(text)


def test_a_step_cannot_call_a_local_workflow_either():
    assert only_structure(workflow(step="- uses: ./.github/workflows/build.yml"))


@pytest.mark.parametrize("step", [
    "- uses: actions/checkout@v5 # " + SHA,
    "- name: x\n        uses: actions/checkout@v5",
    "- {uses: actions/checkout@v5}",
    '- {"uses": "actions/checkout@v5"}',
    '- "uses": actions/checkout@v5',
    '- "\\x75ses": actions/checkout@v5',
    "- uses: >-\n          actions/checkout@v5",
    "- uses: |\n          actions/checkout@v5",
])
def test_unpinned_actions_in_other_spellings_are_refused(step):
    assert found(workflow(step=step))


def test_a_uses_that_is_not_a_string_is_refused():
    assert only_structure(workflow(step="- uses: [actions/checkout]"))
    assert only_structure(workflow(step="- uses: 5"))


# ---- refused: forms the text check cannot follow -------------------------------------------


@pytest.mark.parametrize("extra", [
    "env: &anchor\n  A: b\n",
    "env: *anchor\n",
    "env: !!map {}\n",
    "? complex\n: key\n",
])
def test_anchors_aliases_tags_and_explicit_keys_are_refused(extra):
    assert only_text(workflow(extra=extra))


def test_a_document_marker_is_refused():
    assert only_text("---\n" + workflow())
    assert only_text(workflow() + "...\n")
    assert only_text("%YAML 1.2\n" + workflow())


def test_an_open_string_or_expression_or_flow_collection_is_refused():
    assert only_text(workflow(step="- run: \"echo\nuses: x\""))
    assert only_text(workflow(step="- run: ${{ format('a'"))
    assert only_text(workflow(step="- with: {a: b,\n          c: d}"))


def test_a_line_ending_with_a_backslash_is_refused():
    assert only_text(workflow(step="- uses: actions/checkout@v5 \\"))


# ---- refused: YAML that PyYAML reads differently ---------------------------------------------


def test_duplicate_keys_and_merge_keys_are_refused():
    twice = "name: t\non: push\njobs:\n  one:\n    runs-on: ubuntu-latest\n    runs-on: self-hosted\n    steps: []\n"
    assert found(twice)
    merge = ("name: t\non: push\njobs:\n  base: &b\n    runs-on: ubuntu-latest\n  one:\n    <<: *b\n    steps: []\n")
    assert found(merge)
    assert any("merge key" in p for p in only_structure(merge.replace("&b", "").replace("*b", "{}")))


@pytest.mark.parametrize("text", [
    "name: t\njobs: [\n",
    "- just\n- a list\n",
    "name: t\non: push\n",
    "name: t\non: push\njobs: {}\n",
    "name: t\non: push\njobs:\n  one: not-a-mapping\n",
    "name: t\non: push\njobs:\n  one:\n    runs-on: ubuntu-latest\n    steps: nope\n",
    "name: t\non: push\njobs:\n  one:\n    runs-on: ubuntu-latest\n    steps:\n      - just a string\n",
    "",
])
def test_an_unreadable_or_unexpected_document_is_refused(text):
    assert only_structure(text)


def test_without_pyyaml_the_structure_check_fails_closed(monkeypatch):
    monkeypatch.setattr(CW, "yaml", None)
    assert any("PyYAML missing" in p for p in CW.structure_problems(workflow()))


# ---- the script itself ----------------------------------------------------------------------


def test_main_prints_ok_for_a_clean_folder_and_fails_on_a_bad_one(tmp_path, capsys):
    folder = tmp_path / "wf"
    folder.mkdir()
    (folder / "ok.yml").write_text(workflow(), encoding="utf-8")
    assert CW.main(folder) == 0
    assert "check_workflows ok (1 workflows" in capsys.readouterr().out
    (folder / "bad.yaml").write_text(workflow("runs-on: [self-hosted, macOS]"), encoding="utf-8")
    assert CW.main(folder) == 1
    out = capsys.readouterr().out
    assert "bad.yaml:" in out and "ok.yml:" not in out and "problem(s)" in out


def test_main_fails_when_there_is_no_workflow(tmp_path, capsys):
    assert CW.main(tmp_path) == 1
    assert "no workflow" in capsys.readouterr().out


def test_the_workflows_of_the_repository_pass(capsys):
    assert CW.main() == 0
    assert "check_workflows ok" in capsys.readouterr().out


def test_the_workflows_of_the_repository_say_where_they_run():
    for name in ("tests.yml", "build.yml"):
        head = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")[:300]
        assert "GitHub-hosted machines only" in head and "07/11/2026" in head, name
    assert "07/11/2026" in (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
