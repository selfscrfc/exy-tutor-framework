#!/usr/bin/env python3
"""Create an isolated learning workspace using the shared framework runtime."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def create(destination, objective):
    destination = destination.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Destination must be absent or empty; existing work will not be overwritten')
    python = ROOT / '.venv/bin/python'
    if not python.exists():
        raise ValueError('Install framework dependencies in .venv before creating an instance')
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'init', '-b', 'main', str(destination)], check=True, capture_output=True)
    (destination / '.gitignore').write_text('.DS_Store\n__pycache__/\n*.py[cod]\n.env\n.env.*\nprivate/\nstate/.lock\nstate/.exy-write-*\nstate/plans/.exy-write-*\nstate/weekly-reviews/.exy-write-*\n')
    relative = os.path.relpath(ROOT, destination)
    revision = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    (destination / 'instance.json').write_text(json.dumps({'schema_version': 1, 'framework_path': relative,
                                                         'created_from_commit': revision}, indent=2)+'\n')
    (destination / 'tutor.py').write_text('''#!/usr/bin/env python3
"""Use this workspace's state with the shared framework runtime."""
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
config = json.loads((HERE / 'instance.json').read_text())
framework = Path(os.environ.get('EXY_FRAMEWORK_ROOT', str(HERE / config['framework_path']))).expanduser().resolve()
python = framework / '.venv/bin/python'
if not python.exists():
    sys.exit('Framework environment missing. Install its requirements in .venv or set EXY_FRAMEWORK_ROOT.')
if any(arg == '--state' or arg.startswith('--state=') for arg in sys.argv[1:]):
    sys.exit('This wrapper always uses its own state; use the framework CLI to inspect another instance.')
os.execv(str(python), [str(python), str(framework / 'scripts/tutor.py'), '--state', str(HERE / 'state'), *sys.argv[1:]])
''')
    (destination / 'README.md').write_text(f'''# {destination.name}

An isolated Exy Tutor learning workspace. Intended objective: **{objective}**.

The objective is an initial intent. Scope, target roles, deadline, available hours, starting level, and the curriculum remain unconfirmed until the user supplies their plans and completes goal clarification.

## Start here

Ask the agent to use `$exy-clarify-goal` with your goals and plans. It will preserve existing answers, ask focused questions, and save a proposed agreement in `state/foundation.json`. Confirm that agreement before scheduling a learning week. No proficiency or diagnostic results have been invented.

```sh
python3 tutor.py status
python3 tutor.py template foundation
python3 tutor.py check
```

Use `python3 tutor.py --help` for commands. The wrapper always targets this workspace's `state/`. It uses the shared runtime at `{relative}` and its `.venv`; dependencies are installed once in the framework repository. `instance.json` records the source commit and relative runtime path. Set `EXY_FRAMEWORK_ROOT` if the framework moves.

## Workspace

- `state/`: objective, clarification record, outcomes, plans, cards, and history.
- `.agents/skills/exy-clarify-goal/`: the goal-clarification skill.
- `intake/`: goals, plans, and materials provided for initial planning.
- `materials/`: learning references; PDF ingestion is not implemented yet.
- `work/`: exercise solutions and assessment artifacts.
- `private/`: ignored local information that should not be committed.

The curriculum will be prepared after clarification and any diagnostic work that materially affects placement. The first two weeks will receive detailed activities and completion criteria; later work will remain progressively less detailed.

The full [CLI guide]({relative}/docs/cli.md) and [learning workflow]({relative}/docs/workflow.md) live in the shared framework. Commit meaningful state changes locally. Do not publish personal learning materials without the user's instruction.
''')
    (destination / 'AGENTS.md').write_text(f'''# Working in {destination.name}

Use English for repository content and Git messages. Do not add tool signatures or co-author trailers. Use ordinary hyphens.

Read `README.md`, `instance.json`, and the shared framework's `AGENTS.md` and `docs/cli.md` at `{relative}` before operating. Use `python3 tutor.py` from this directory; it isolates all writes to this instance. Do not populate the framework repository's shared `state/` with this learner's data.

The known intent is: {objective}. The user will provide their specific goals and plans. Use `.agents/skills/exy-clarify-goal/SKILL.md` for intake. Preserve unknowns as null. Do not invent target roles, dates, available hours, current proficiency, diagnostic answers, or confirmation. Save partial clarification and wait for the missing material.

Once the foundation is confirmed, assess placement as needed and prepare the initial roadmap and two-week plan as a separate change. Resume each session through the CLI, record actual work and evidence, and save a continuation note before ending.

Run `python3 tutor.py check` and inspect the diff before committing. Keep personal materials local unless publication is explicitly requested.
''')
    skill = '.agents/skills/exy-clarify-goal'
    shutil.copytree(ROOT / skill, destination / skill)
    for folder in ('intake', 'materials', 'work'):
        (destination / folder).mkdir()
        (destination / folder / '.gitkeep').touch()
    subprocess.run([str(python), str(ROOT / 'scripts/tutor.py'), '--state', str(destination / 'state'), 'init'],
                   check=True, capture_output=True, text=True)
    for folder in ('plans', 'weekly-reviews'):
        (destination / 'state' / folder / '.gitkeep').touch()
    sys.path.insert(0, str(ROOT))
    from exy.store import Store
    with Store(destination / 'state') as store:
        foundation = store.get('foundation.json')
        foundation['objective'] = objective
        foundation['open_questions'] = ['User-provided goals and plans', 'Target roles and scope',
                                       'Success criteria and application timing', 'Sustainable weekly study time and time zone',
                                       'Current experience and evidence for diagnostic placement']
        store.put('foundation.json', foundation)
        settings = store.get('objective.json')
        settings['title'] = objective
        store.put('objective.json', settings)
        store.commit()
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--objective', required=True)
    args = parser.parse_args()
    try:
        result = create(args.destination, args.objective)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f'ERROR: {error}')
    print(f'Created {result}; foundation is a draft and curriculum is awaiting clarification.')


if __name__ == '__main__':
    main()
