"""Opt-in server cache of validated comparison/recommendation content, never sessions."""

import os
import re
import tempfile
from pathlib import Path

from app.json_utils import digest, json_read, json_text
from app.services.errors import StorageIntegrityError


def jd_cache_text(text):
    """Match copied prose across Markdown and rendered text without changing its words."""
    lines = []
    for line in text.splitlines():
        line = re.sub(r'^\s*#{1,6}\s+', '', line)
        line = re.sub(r'^\s*[-*+•]\s+', '', line)
        line = re.sub(r'(?<!\w)(\*\*|__)(?=\S)(.+?)(?<=\S)\1(?!\w)', r'\2', line)
        lines.append(line)
    return ' '.join(' '.join(lines).split())


class ResultCache:
    def __init__(self, directory):
        self.directory = Path(directory)
        root = Path(__file__).resolve().parents[1] / 'engines'
        self.policy = digest({name: (root / name).read_text() for name in
                              ('prompts.py', 'career.py', 'career_targets.py', 'models.py', 'recommendations.py')})

    def key(self, stage, snapshot, settings):
        return digest({'stage': stage, 'policy': self.policy,
            'source': snapshot['clo_set'],
            'target': snapshot['career_profile'] if 'career_profile' in snapshot else jd_cache_text(snapshot['job_description']),
            'comparison': snapshot['comparison'] if stage == 'recommendations' else None,
            'model': settings.model, 'reasoning_effort': settings.reasoning_effort,
            'max_output_tokens': settings.max_output_tokens, 'temperature': settings.temperature})

    def get(self, key):
        try:
            raw = (self.directory / f'{key}.json').read_text()
        except FileNotFoundError:
            return None
        try:
            record = json_read(raw)
            if (record['key'] != key or not isinstance(record['value'], dict)
                    or digest(record['value']) != record['digest']):
                raise ValueError('Cache fingerprint mismatch')
            return record['value']
        except (ValueError, TypeError, KeyError) as error:
            raise StorageIntegrityError('Stored result cache failed integrity validation') from error

    def put(self, key, value):
        # shortcut: concurrent cache misses may both infer; add a lease if parallel warming is needed.
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                                             prefix='.result-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json_text({'key': key, 'value': value, 'digest': digest(value)}))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / f'{key}.json')
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
