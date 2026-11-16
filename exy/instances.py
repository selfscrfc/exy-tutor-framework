"""Shared registered-instance access for local MCP and HTTP clients."""
from datetime import datetime, timezone
import json
from pathlib import Path

from exy import engine, timekeeping
from exy.store import Store


class InstanceService:
    def __init__(self, registry):
        self.registry = Path(registry).expanduser().resolve()

    def mapping(self):
        value = json.loads(self.registry.read_text())
        engine.need(value.get('schema_version') == 1 and isinstance(value.get('instances'), dict), 'Invalid instance registry')
        return value['instances']

    def state_for(self, instance):
        instances = self.mapping()
        engine.need(instance in instances, 'Unknown instance; an operator must register it locally first')
        path = Path(instances[instance]).expanduser().resolve()
        engine.need(path.is_dir() and (path / 'settings.json').is_file(), 'Registered instance is not initialized')
        return path

    @staticmethod
    def revision(store):
        return engine.fingerprint(store.files)

    def mutate(self, instance, request_id, operation, data, expected_revision, fn):
        engine.need(request_id.strip(), 'A stable request_id is required')
        request_hash = engine.fingerprint({'operation': operation, 'data': data, 'expected_revision': expected_revision})
        with Store(self.state_for(instance)) as store:
            store.validate()
            for event in store.get('rpc-log.jsonl', []):
                if event['request_id'] == request_id:
                    engine.need(event['request_hash'] == request_hash, 'request_id was used with different arguments')
                    return {'result': event['result'], 'state_revision': self.revision(store), 'replayed': True}
            engine.need(expected_revision is None or expected_revision == self.revision(store),
                        'Stale state_revision; refresh context and reconsider the change')
            timekeeping.initialize(store)
            now = datetime.now(timezone.utc)
            result = fn(store, now)
            store.append('rpc-log.jsonl', {'request_id': request_id, 'request_hash': request_hash,
                                          'operation': operation, 'occurred_at': now.isoformat(), 'result': result})
            store.commit()
            return {'result': result, 'state_revision': self.revision(store), 'replayed': False}
