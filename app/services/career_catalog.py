"""Eight application targets backed by six unchanged CWA source summaries."""
import hashlib
import re
from pathlib import Path

from app.config import ROOT
from app.engines.career import CareerProfile
from app.engines.career_targets import career_target
from app.engines.models import parse_model
from .errors import ResourceNotFoundError, BackendUnavailableError

PROFILES = {
    'data-scientist': '1_Data_Scientist_CWA_18398_2026.txt',
    'data-analyst': '2_Data_Analyst_CWA_18398_2026.txt',
    'ai-ml-engineer': '3_AI_ML_Engineer_CWA_18398_2026.txt',
    'computer-vision-engineer': '3_AI_ML_Engineer_CWA_18398_2026.txt',
    'nlp-llm-engineer': '3_AI_ML_Engineer_CWA_18398_2026.txt',
    'mlops-engineer': '4_MLOps_Engineer_CWA_18398_2026.txt',
    'ai-researcher': '5_Algorithm_Research_Engineer_AI_Researcher_CWA_18398_2026.txt',
    'ai-data-platform-engineer': '6_AI_and_Data_Platform_Engineer_CWA_18398_2026.txt',
}


class CareerCatalog:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else ROOT / 'data/AI_Roles_CWA_18398_2026'

    def get(self, profile_id):
        if profile_id not in PROFILES:
            raise ResourceNotFoundError('Career profile is not in the configured catalog')
        try:
            content = (self.directory / PROFILES[profile_id]).read_bytes().decode('utf-8')
            title = re.search(r'^VỊ TRÍ:\s*(.+)$', content, re.M).group(1).strip()
            codes = re.search(r'^MÃ VỊ TRÍ:\s*(.+)$', content, re.M).group(1)
            return parse_model(CareerProfile, {'profile_id': profile_id, 'title': title,
                'standard': 'CWA 18398:2026', 'role_codes': re.findall(r'\d+\.\d+', codes),
                'content': content, 'fingerprint': hashlib.sha256(content.encode('utf-8')).hexdigest(),
                'target': career_target(profile_id).model_dump()}).model_dump()
        except (OSError, ValueError, AttributeError) as exc:
            raise BackendUnavailableError('Career source is unavailable or invalid') from exc

    def list_profiles(self):
        return [self.get(identifier) for identifier in PROFILES]
