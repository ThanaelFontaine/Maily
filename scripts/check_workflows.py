r"""Guard of the workflows: runners hosted by GitHub only, actions pinned by a full commit SHA.

Maily is a public repository: a pull request from anyone can change a workflow, so every
workflow of .github/workflows runs on the disposable machines hosted by GitHub, never on a
machine of the maintainer (rule of 07/11/2026). An `if: github.actor == ...` would not be
enough, the workflow file is the pull request author's to change. The check-text job of
.github/workflows/tests.yml runs this script on every pull request and every push to main.

Scope: who runs a job (runs-on) and what code a step pulls in (uses). The images of
containers are not checked: the clean-system test of build.yml follows the latest tag of each
distribution on purpose.

Every workflow goes through two checks, and each one alone fails the run.

A. A text check, line by line, with the YAML escapes \x, \u and \U decoded. It refuses every
   YAML form it cannot follow:
   - a line ending with "\", a quoted string still open at the end of the line, a flow mapping
     or sequence ("{", "[") not closed on the same line, an unclosed "${{" expression;
   - an explicit key "?", an anchor "&", an alias "*" or a tag "!" where a value starts, a
     document marker ("---", "...") or a "%" directive;
   - the word "self-hosted" anywhere, comments included (only the option
     "--deny-self-hosted-runners" of `gh attestation verify` is let through);
   - the words runs-on or uses in a comment, or on a line that is not exactly one of the known
     forms: "runs-on: <label>" (plain value, one item list, or a block of one "- <label>"
     item) or "uses: <target>";
   - a label outside the closed list HOSTED_LABELS (standard runners hosted by GitHub), except
     "${{ matrix.<key> }}", which check B resolves; an action not pinned by a full commit SHA
     of 40 lowercase hex characters ("docker://" actions and reusable workflows of another
     repository are refused; only a local workflow "./.github/workflows/<name>.yml" is allowed).
   The content of a block scalar ("run: |") is only searched for "self-hosted".

B. A structure check: the file is parsed by PyYAML (version pinned by uv.lock, dev group), with
   duplicate keys and "<<" merge keys refused. Every job is checked: "runs-on" is one label of
   HOSTED_LABELS (a string, or a one item list), or "${{ matrix.<key> }}" where every value of
   that key in strategy.matrix (the list, and the "include" entries) is a label of
   HOSTED_LABELS; the "uses" of a job is a local workflow "./.github/workflows/...", a step
   never uses a local path, every "steps[].uses" is pinned by a full commit SHA, and no string
   of the file holds "self-hosted". A parse error, an unexpected type or a missing PyYAML fail
   the check (fail closed).

Tests: tests/test_check_workflows.py.
Usage: python3 scripts/check_workflows.py [folder]   (exit code 1 when something is found)
"""
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # fail closed: check B reports it for every workflow
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = ROOT / ".github" / "workflows"
SELF_HOSTED = re.compile("self-hosted", re.IGNORECASE)
# The one place where the word is legitimate: the option of `gh attestation verify` that refuses
# an attestation made on such a runner (release.yml). It is blanked before the search; it cannot
# make a runner label, and "runs-on" only takes a label of HOSTED_LABELS.
DENY_FLAG = "--deny-self-hosted-runners"
# The labels of the standard runners hosted by GitHub: a closed list, copied from the tables of
# the official documentation (docs.github.com, Actions, "GitHub-hosted runners", read on
# 2026-11-08). A made-up label (macos-mini...) is refused; a new GitHub image is added here
# after reading that page.
HOSTED_LABELS = {
    "ubuntu-slim", "ubuntu-latest", "ubuntu-26.04", "ubuntu-24.04", "ubuntu-22.04",
    "ubuntu-26.04-arm", "ubuntu-24.04-arm", "ubuntu-22.04-arm",
    "windows-latest", "windows-2025", "windows-2025-vs2026", "windows-2022",
    "windows-11-arm", "windows-11-vs2026-arm",
    "macos-latest", "macos-26", "macos-15", "macos-26-intel", "macos-15-intel", "xcode-27",
}
_LEFT, _RIGHT = r"(?<![A-Za-z0-9_-])", r"(?![A-Za-z0-9_-])"
KEYWORD = re.compile(_LEFT + r"(runs-on|uses)" + _RIGHT, re.IGNORECASE)
KEYWORD_OR_SELF_HOSTED = re.compile(_LEFT + r"(runs-on|uses|self-hosted)" + _RIGHT, re.IGNORECASE)
RUNS_ON = re.compile(r"^(\s*)(?:-\s+)?runs-on:(?:\s+(.*))?$")
USES = re.compile(r"^\s*(?:-\s+)?uses:\s+(\S+)$")
ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?@([0-9a-f]{40})$")
LOCAL_WORKFLOW = re.compile(r"^\./\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml$")
ESCAPE = re.compile(r"\\x([0-9A-Fa-f]{2})|\\u([0-9A-Fa-f]{4})|\\U([0-9A-Fa-f]{8})")
# Start of a block scalar: "key: |", "- key: >-", "- |" (a plain key, nothing else).
BLOCK = re.compile(r"^( *)((?:- +)*)([A-Za-z0-9_.-]+: +)?[|>][+-]?$")
# A YAML indicator (? & * !) where a value starts: start of line, after "- ", ": ", "? ", or
# after "[", "{", ",".
INDICATOR = re.compile(r"(?:^\s*(?:-\s+)*|:\s+|\?\s+|[\[{,]\s*)[?&*!]")
NOT_CHECKABLE = "workflow form not checkable"
MATRIX_REF = re.compile(r"^\$\{\{\s*matrix\.([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}$")


def names_self_hosted(text):
    """True when the text holds the word "self-hosted" (the DENY_FLAG option aside)."""
    return SELF_HOSTED.search(text.replace(DENY_FLAG, " ")) is not None


def decode_escapes(line):
    """The line with the YAML escapes \\xNN, \\uNNNN and \\UNNNNNNNN decoded."""
    def one(match):
        try:
            return chr(int(match.group(1) or match.group(2) or match.group(3), 16))
        except ValueError:
            return match.group(0)
    return ESCAPE.sub(one, line)


def value_start(before):
    """True when a quote right after `before` opens a YAML string (and is not a character of a plain value)."""
    p = before.rstrip()
    return p == "" or p[-1] in "[{,:" or re.search(r"(?:^|\s)[-?]$", p) is not None


def scan(line):
    r"""Reads one line the way YAML would, without parsing it.

    Returns (code, comment, mask, open_reason): code is the line without its comment, mask is the
    code with the content of quoted strings and of ${{ }} expressions blanked, open_reason says
    what is left open at the end of the line (a string, an expression, a flow collection), or is
    None. In a double quoted string the character after "\" is skipped.
    """
    mask, i, n, depth, open_reason = [], 0, len(line), 0, None
    while i < n:
        c = line[i]
        if c == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        if line.startswith("${{", i):
            end = line.find("}}", i + 3)
            if end < 0:
                open_reason = "${{ expression not closed on the line"
                mask.append(" " * (n - i))
                i = n
                break
            mask.append("$" + " " * (end + 1 - i))
            i = end + 2
            continue
        if c in "'\"" and value_start("".join(mask)):
            j = i + 1
            while j < n:
                if c == '"' and line[j] == "\\":
                    j += 2
                    continue
                if line[j] == c:
                    if c == "'" and j + 1 < n and line[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            if j >= n:
                open_reason = "quoted string not closed on the line"
                mask.append(c + " " * (n - i - 1))
                i = n
                break
            mask.append(c + " " * (j - i - 1) + c)
            i = j + 1
            continue
        if c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
            if depth < 0:
                open_reason = open_reason or "closing bracket without an opening one"
        mask.append(c)
        i += 1
    if depth > 0 and not open_reason:
        open_reason = "flow mapping or sequence not closed on the line"
    return line[:i].rstrip(), line[i:], "".join(mask).rstrip(), open_reason


def unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def hosted_label(value):
    """True when value is one label of HOSTED_LABELS, plain, quoted or in a one item list.
    "${{ matrix.<key> }}" passes here: check B resolves it against strategy.matrix."""
    if value.startswith("["):
        match = re.fullmatch(r"\[([^\[\]{},]*)\]", value)
        if not match:
            return False
        value = match.group(1)
    value = unquote(value)
    return value in HOSTED_LABELS or MATRIX_REF.match(value) is not None


def action_problem(target):
    """None when the target of a "uses" is a local workflow or an action pinned by a full commit SHA, else the problem."""
    if isinstance(target, str) and target.startswith("./"):
        return None if LOCAL_WORKFLOW.match(target) else "local path that is not a workflow of .github/workflows"
    if isinstance(target, str) and "/.github/workflows/" in target:
        return "reusable workflow of another repository"
    if isinstance(target, str) and ACTION.match(target):
        return None
    return "action not pinned by a full commit SHA"


def text_problems(text):
    """Check A on a workflow text: one "line N: problem" entry per problem."""
    problems = []
    lines = text.split("\n")
    block = None  # (column of the parent, indent of the content or None) inside a block scalar
    i = 0
    while i < len(lines):
        raw = lines[i]
        number = i + 1
        i += 1

        def problem(reason, number=number):
            problems.append(f"line {number}: {reason}")

        if names_self_hosted(decode_escapes(raw)):
            problem("self-hosted runner")
        if block is not None:
            if not raw.strip():
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            parent, content = block
            if content is None and indent > parent:
                block = (parent, indent)
                continue
            if content is not None and indent >= content:
                continue
            block = None
        if not raw.strip():
            continue

        code, comment, mask, open_reason = scan(raw)
        if open_reason:
            problem(f"{NOT_CHECKABLE} ({open_reason})")
        if KEYWORD_OR_SELF_HOSTED.search(decode_escapes(comment).replace(DENY_FLAG, " ")):
            problem(f"{NOT_CHECKABLE} (runs-on, uses or self-hosted in a comment)")
        if raw.rstrip().endswith("\\"):
            problem(f"{NOT_CHECKABLE} (line ending with a backslash)")
        if re.match(r"(---|\.\.\.|%)", raw):
            problem(f"{NOT_CHECKABLE} (YAML document marker or directive)")
        if INDICATOR.search(mask):
            problem(f"{NOT_CHECKABLE} (explicit key, anchor, alias or tag: ?, &, *, !)")
        match = BLOCK.match(code)
        if match:
            # Column of the parent: the key's, or the last "-" when there is no key.
            dashes = match.group(2) if match.group(3) else match.group(2).rstrip()[:-1]
            block = (len(match.group(1)) + len(dashes), None)

        if not KEYWORD.search(code) and not KEYWORD.search(decode_escapes(code)):
            continue
        match = RUNS_ON.match(code)
        if match and match.group(2) and MATRIX_REF.match(unquote(match.group(2))):
            continue  # "runs-on: ${{ matrix.<key> }}": check B resolves it
        if "{" in code or "\\" in code:
            problem(f"{NOT_CHECKABLE} (flow style, JSON or escape)")
            continue
        match = RUNS_ON.match(code)
        if match:
            indent, value = match.group(1), (match.group(2) or "").strip()
            if not value:
                # Block form: exactly one "- label" item, indented deeper.
                items = []
                while i < len(lines):
                    following = scan(lines[i])[0]
                    if following.strip() and len(following) - len(following.lstrip()) <= len(indent):
                        break
                    if following.strip():
                        items.append(following.strip())
                    i += 1
                value = items[0][2:].strip() if len(items) == 1 and items[0].startswith("- ") else ""
            if not hosted_label(value):
                problem("runner not hosted by GitHub")
            continue
        match = USES.match(code)
        if match:
            reason = action_problem(unquote(match.group(1)))
            if reason:
                problem(reason)
            continue
        problem(f"{NOT_CHECKABLE} (runs-on or uses in another form)")
    return problems


if yaml is not None:
    class StrictLoader(yaml.SafeLoader):
        """A SafeLoader that refuses duplicate keys and "<<" merge keys."""

    def _mapping(loader, node, deep=False):
        seen = set()
        for key, _ in node.value:
            if key.tag == "tag:yaml.org,2002:merge":
                raise yaml.constructor.ConstructorError(None, None, "merge key << refused", key.start_mark)
            value = loader.construct_object(key, deep=True)
            try:
                duplicate = value in seen
                seen.add(value)
            except TypeError:
                raise yaml.constructor.ConstructorError(None, None, "key that is not a scalar refused", key.start_mark)
            if duplicate:
                raise yaml.constructor.ConstructorError(None, None, f"duplicate key {value!r}", key.start_mark)
        return loader.construct_mapping(node, deep=deep)

    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def strings(obj, seen=None):
    """Every string (key or value) of a loaded YAML document."""
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        seen.add(id(obj))
        for key, value in obj.items():
            yield from strings(key, seen)
            yield from strings(value, seen)
    elif isinstance(obj, list):
        seen.add(id(obj))
        for value in obj:
            yield from strings(value, seen)


def structure_problems(text):
    """Check B: one "<place>: problem" entry per problem of a workflow, parsed by PyYAML."""
    if yaml is None:
        return ["PyYAML missing, the workflow cannot be parsed (fail closed): uv sync --locked"]
    doc, error = parse_yaml(text)
    if error:
        return [error]
    problems = []
    if any(names_self_hosted(s) for s in strings(doc)):
        problems.append("(file): self-hosted runner")
    if not isinstance(doc, dict):
        return problems + ["(file): the workflow is not a mapping"]
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return problems + ["jobs: missing, empty or not a mapping"]
    for job_id, job in jobs.items():
        place = f"jobs.{job_id}"
        if not isinstance(job, dict):
            problems.append(f"{place}: the job is not a mapping")
            continue
        if "uses" in job and not (isinstance(job["uses"], str) and LOCAL_WORKFLOW.match(job["uses"])):
            problems.append(f"{place}.uses: reusable workflow of another repository")
        if "runs-on" in job or "uses" not in job:
            if "runs-on" not in job:
                problems.append(f"{place}.runs-on: missing (key written another way, or job with no runner)")
            else:
                problems += [f"{place}.runs-on: {reason}" for reason in runner_problems(job)]
        if "steps" in job:
            problems += steps_problems(place, job["steps"])
    return problems


def matrix_labels(job, key):
    """(the values of `key` in strategy.matrix, the list and the include entries, or None when the matrix cannot be read)."""
    strategy = job.get("strategy")
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    if not isinstance(matrix, dict):
        return None
    values = []
    if key in matrix:
        if not isinstance(matrix[key], list):
            return None
        values += matrix[key]
    include = matrix.get("include", [])
    if not isinstance(include, list) or not all(isinstance(entry, dict) for entry in include):
        return None
    values += [entry[key] for entry in include if key in entry]
    return values


def runner_problems(job):
    """The problems of the "runs-on" of a job: one label of HOSTED_LABELS, or "${{ matrix.<key> }}" with every value of the matrix a label."""
    value = job["runs-on"]
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if isinstance(value, str) and value in HOSTED_LABELS:
        return []
    match = MATRIX_REF.match(value) if isinstance(value, str) else None
    if not match:
        return ["runner not hosted by GitHub"]
    values = matrix_labels(job, match.group(1))
    if not values:
        return [f"matrix.{match.group(1)} missing or not a list of labels"]
    return [f"matrix.{match.group(1)} holds {bad!r}: runner not hosted by GitHub"
            for bad in values if not (isinstance(bad, str) and bad in HOSTED_LABELS)]


def steps_problems(place, steps):
    """One "<place>.steps[n]...: problem" entry per problem of a list of steps."""
    if not isinstance(steps, list):
        return [f"{place}.steps: not a list"]
    problems = []
    for rank, step in enumerate(steps):
        if not isinstance(step, dict):
            problems.append(f"{place}.steps[{rank}]: the step is not a mapping")
        elif "uses" in step:
            reason = action_problem(step["uses"])
            if not reason and step["uses"].startswith("./"):
                reason = "a step cannot use a local path (not checkable)"
            if reason:
                problems.append(f"{place}.steps[{rank}].uses: {reason}")
    return problems


def parse_yaml(text):
    """(document, None) or (None, the message of the refusal) with the strict loader."""
    try:
        return yaml.load(text, Loader=StrictLoader), None
    except (yaml.YAMLError, ValueError, TypeError, RecursionError) as error:
        first = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
        return None, f"YAML refused by the structure check: {first}"


def main(folder=WORKFLOW_DIR):
    folder = Path(folder)
    files = sorted(p for p in folder.glob("*") if p.suffix in (".yml", ".yaml"))
    if not files:
        print(f"check_workflows: no workflow in {folder}")
        return 1
    problems = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        problems += [f"{file.name}: {hit}" for hit in text_problems(text) + structure_problems(text)]
    for problem in problems:
        print(problem)
    if problems:
        print(f"check_workflows: {len(problems)} problem(s), see the top of scripts/check_workflows.py")
        return 1
    print(f"check_workflows ok ({len(files)} workflows: GitHub-hosted runners only, actions pinned)")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
