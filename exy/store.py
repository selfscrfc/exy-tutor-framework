"""Locked JSON storage with validated, recoverable multi-file commits (POSIX)."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SINGLE_FILES = ('objective.json', 'goals.json', 'cards.json', 'assessment-log.jsonl',
                'card-review-log.jsonl', 'sessions.json', 'session-log.jsonl', 'settings.json', 'foundation.json')


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest() if text is not None else None


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.exy-write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_dir(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def allowed(name):
    p = Path(name)
    return name in SINGLE_FILES or (len(p.parts) == 2 and p.parts[0] in {'plans', 'weekly-reviews'}
                                    and p.suffix == '.json' and '..' not in p.parts)


class Store:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.files = {}
        self.original = {}

    def __enter__(self):
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock = (self.path / '.lock').open('a+')
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        try:
            self.recover()
            for name in SINGLE_FILES:
                if (self.path / name).exists():
                    self.files[name] = (self.path / name).read_text()
            for directory in ('plans', 'weekly-reviews'):
                for p in sorted((self.path / directory).glob('*.json')):
                    self.files[str(p.relative_to(self.path))] = p.read_text()
            self.original = dict(self.files)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.lock.close()

    def get(self, name, default=None):
        if name not in self.files:
            return default
        if name.endswith('.jsonl'):
            return [json.loads(line) for line in self.files[name].splitlines() if line.strip()]
        return json.loads(self.files[name])

    def put(self, name, value):
        if not allowed(name):
            raise ValueError(f'Unsupported state path: {name}')
        if name.endswith('.jsonl'):
            self.files[name] = ''.join(json.dumps(v, ensure_ascii=False, allow_nan=False) + '\n' for v in value)
        else:
            self.files[name] = encode(value)

    def append(self, name, value):
        # Keep existing bytes, including historical formatting, intact.
        previous = self.files.get(name, '')
        separator = '\n' if previous and not previous.endswith('\n') else ''
        self.files[name] = previous + separator + json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n'

    def apply_file(self, name, content):
        atomic_write(self.path / name, content)

    def recover(self):
        journal = self.path / '.pending-transaction.json'
        if not journal.exists():
            return
        data = json.loads(journal.read_text())
        if data.get('version') != 1:
            raise ValueError('Unknown pending transaction version')
        for name, entry in data['files'].items():
            if not allowed(name):
                raise ValueError('Unsafe path in pending transaction')
            path = self.path / name
            current = path.read_text() if path.exists() else None
            if digest(current) not in {entry['before'], digest(entry['after'])}:
                raise ValueError(f'Recovery conflict at {name}; preserve the pending journal and inspect external edits')
        for name, entry in data['files'].items():
            self.apply_file(name, entry['after'])
        journal.unlink()
        sync_dir(self.path)

    def validate(self):
        from scripts.check import check
        with tempfile.TemporaryDirectory(prefix='exy-validate-') as name:
            stage = Path(name)
            for folder in ('plans', 'weekly-reviews'):
                (stage / folder).mkdir()
            for relative, content in self.files.items():
                p = stage / relative
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
            return check(stage)

    def commit(self):
        changes = {name: content for name, content in self.files.items() if self.original.get(name) != content}
        for name, content in changes.items():
            old = self.original.get(name)
            if old is not None and name.startswith(('plans/', 'weekly-reviews/')):
                raise ValueError('Published plans and reports are immutable; create a new revision')
            if old is not None and name.endswith('.jsonl') and not content.startswith(old):
                raise ValueError('Historical events are append-only')
        self.validate()
        if not changes:
            return
        journal = {'version': 1, 'files': {name: {'before': digest(self.original.get(name)), 'after': content}
                                         for name, content in changes.items()}}
        atomic_write(self.path / '.pending-transaction.json', encode(journal))
        # After the journal is durable, recovery finishes the commit after any interruption.
        self.recover()
        self.original = dict(self.files)
