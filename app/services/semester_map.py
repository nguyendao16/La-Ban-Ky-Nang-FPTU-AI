"""Presentation curriculum, independent of the private evidence catalog."""
from pathlib import Path

from app.config import ROOT
from app.json_utils import json_read
from .errors import CLOSetValidationError


class SemesterMap:
    TRACKS = ("Applied Data Science", "AI application")
    # Product decision: selectable presentation courses, never evidence sources.
    PRESENTATION_ONLY = frozenset({'OJT202', 'MLN111', 'MLN122', 'AIP491', 'HCM202', 'MLN131', 'VNR202'})

    def __init__(self, raw=None):
        self.raw = json_read((ROOT / 'semestermap.json').read_text()) if raw is None else raw
        expected = {f'Semester {n}' for n in range(1, 5)} | set(self.TRACKS)
        if not isinstance(self.raw, dict) or set(self.raw) != expected:
            raise ValueError('Invalid semester map structure')
        for track in self.TRACKS:
            if set(self.raw[track]) != {f'Semester {n}' for n in range(5, 10)}:
                raise ValueError('Invalid track semesters')
            rows = self.semesters(track)
            codes = [code for row in rows for code in row['course_codes']]
            if len(codes) != len(set(codes)):
                raise ValueError('Duplicate semester course')
        self.codes = set(code for track in self.TRACKS for row in self.semesters(track) for code in row['course_codes'])

    def semesters(self, track):
        rows = []
        for n in range(1, 10):
            codes = (self.raw if n < 5 else self.raw[track])[f'Semester {n}']
            if not isinstance(codes, list) or any(not isinstance(c, str) or not c.strip() for c in codes):
                raise ValueError('Invalid semester courses')
            rows.append({'semester': n, 'course_codes': list(codes)})
        return rows

    def public(self):
        return {'common': self.semesters(self.TRACKS[0])[:4],
                'combos': [{'name': t, 'semesters': self.semesters(t)[4:]} for t in self.TRACKS]}

    def validate_selection(self, selected, combo=None):
        if not selected or len(set(selected)) != len(selected) or any(c not in self.codes for c in selected):
            raise CLOSetValidationError([{'issue': 'invalid_course_selection'}])
        if combo is not None and combo not in self.TRACKS:
            raise CLOSetValidationError([{'issue': 'unknown_combo'}])
        choices = [combo] if combo else self.TRACKS
        if not any(set(selected) <= {c for row in self.semesters(t) for c in row['course_codes']} for t in choices):
            raise CLOSetValidationError([{'issue': 'inconsistent_combo_selection'}])
