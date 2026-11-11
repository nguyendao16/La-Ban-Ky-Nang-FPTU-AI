"""The public contract is a projection, never a private engine snapshot."""
import re
import unicodedata
from functools import lru_cache
from app.engines.errors import ComparisonError


def words(text):
    return re.findall(r'\w+', text.casefold())


def _policy_text(text):
    text = unicodedata.normalize('NFKD', text.casefold()).replace('đ', 'd')
    text = ''.join(c for c in text if unicodedata.category(c) not in {'Mn', 'Cf'})
    return ' '.join(text.split())


_POLICY_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r'\b(?:gia dinh|mac dinh|boi canh|doi tuong|assum\w*|default|audience|user is)\b.{0,80}\b(?:sinh vien|students?|duoi (?:1|mot) nam|less than (?:1|one) year)\b',
    r'\b(?:sinh vien|students?)\b.{0,60}\b(?:gia dinh|mac dinh|duoi (?:1|mot) nam|less than (?:1|one) year|under (?:1|one) year)\b',
    r'\b(?:gia dinh|mac dinh|assum\w*|default)\b.{0,60}\b(?:kinh nghiem|experience)\b',
    r'\b(?:nguoi dung|ban)\s+la\s+sinh vien\b',
    r'\b(?:tran diem|score ceiling|scoring ceiling|diem tran|nguong diem noi bo)\b',
    r'\b(?:diem|scores?|overall_score|muc phu hop)\b.{0,65}(?:<=|≤|\b(?:bi gioi han|gioi han o|khong vuot|capped|limited to)\b)',
    r'\b(?:diem|scores?|overall_score|muc phu hop)\b[^.!?;]{0,45}\b(?:toi da|at most)\s*(?:la\s*)?[0-5](?:[.,]\d+)?\b(?![\d.,])(?!\s*(?:nam|years?|months?|thang)\b)',
    r'\b(?:toi da|gioi han(?: o)?|khong vuot(?: qua)?|at most|capped at|limited to)\s*(?:muc\s*)?[0-5](?:[.,]\d+)?\s*(?:/|tren|out of)\s*5\b',
    r'\b(?:truc|axis|axes|diem|scores?)\b.{0,110}\b(?:chiu tac dong|bi anh huong|bi dieu chinh|duoc dieu chinh|bi tru|bi giam|affected|adjusted|penalized|penalised|experience penalty)\b',
    r'\b(?:kinh nghiem|experience|sinh vien|student)\b.{0,150}\b(?:(?:nen|khien|vi vay).{0,20}(?:diem|muc phu hop)|(?:diem|score|muc phu hop).{0,25}(?:bi giam|chi o|bi gioi han|capped|limited))\b',
    r'\b(?:yeu cau|dieu kien|kinh nghiem|experience|requirement)\b.{0,120}\b(?:ap vao|ap dung cho|ap len|ap tran|affects?|limits?)\b.{0,30}\b(?:truc|diem|axis|axes|scores?)\b',
    r'\b(?:bang quy doi|quy tac cham diem|cong thuc cham diem|scoring (?:rubric|rules?|policy|table))\b.{0,100}(?:\d|\b(?:ap dung|quy dinh|sinh vien|cap|ceiling)\b)',
    r'\b\d+(?:[.,]\d+)?\s*(?:[-–]\s*\d+)?\s*(?:nam|years?)\b.{0,25}(?:=>|->|→|:)\s*[0-5](?:[.,]\d+)?\s*(?:diem|points?|/\s*5)\b',
    r'\b(?:radar_scoring_rules|source_rules|comparison_instructions|chat_instructions|strict student.context comparison|mandatory experience ceilings|depth ceilings|you are skillbridge)\b',
))


@lru_cache(maxsize=1)
def _private_prompt_spans():
    # Lazy imports keep projection independent of engine initialization.
    from app.engines.prompts import COMPARISON_INSTRUCTIONS, CHAT_INSTRUCTIONS
    from app.engines.career import CAREER_INSTRUCTIONS
    from app.engines.chat import CAREER_CHAT_INSTRUCTIONS
    from app.engines.recommendations import RECOMMENDATION_INSTRUCTIONS, RECOMMENDATION_CHAT_RULES
    return frozenset(tuple(tokens[i:i+20])
        for prompt in (COMPARISON_INSTRUCTIONS, CAREER_INSTRUCTIONS, CHAT_INSTRUCTIONS, CAREER_CHAT_INSTRUCTIONS,
                       RECOMMENDATION_INSTRUCTIONS, RECOMMENDATION_CHAT_RULES)
        for tokens in [words(_policy_text(prompt))]
        for i in range(max(0, len(tokens)-19)))


def discloses_policy(text):
    # shortcut: heuristic patterns and verbatim overlap, not a semantic secrecy guarantee.
    normalized = _policy_text(text)
    if any(pattern.search(normalized) for pattern in _POLICY_PATTERNS):
        return True
    tokens = words(normalized)
    return any(tuple(tokens[i:i+20]) in _private_prompt_spans()
               for i in range(max(0, len(tokens)-19)))


def discloses_source(text, source):
    tokens = words(text)
    spans = {tuple(tokens[i:i+12]) for i in range(max(0, len(tokens)-11))}
    normalized = ' '.join(tokens)
    for course in source['courses']:
        for clo in course['clos']:
            secret = words(clo['description'])
            if len(secret) >= 4 and len(' '.join(secret)) >= 24 and ' '.join(secret) in normalized:
                return True
            if any(tuple(secret[i:i+12]) in spans for i in range(max(0, len(secret)-11))):
                return True
    return False


def protect_text(text, source):
    if discloses_policy(text):
        return 'Tham khảo các mục đối chiếu và môn học được dẫn chứng trong kết quả.'
    if discloses_source(text, source):
        return 'Nội dung phản hồi không thể hiển thị. Bạn có thể hỏi về yêu cầu công việc và môn học liên quan.'
    text = re.sub(r'\bCLO\s*[-_]?\s*\d+\b', '', text, flags=re.I)
    text = re.sub(r'\b(?:enriched\s+CLOs?|CLOs?(?:\s+enriched)?)\b', 'nội dung học phần', text, flags=re.I)
    return text


def evidence(refs):
    return [{'course_code': code} for code in dict.fromkeys(e['course_code'] for e in refs)]


def public_radar(value, source):
    return {'overall_score': value['overall_score'],
        'overall_comment': protect_text(value['overall_comment'], source),
        'axes': [{'name': protect_text(axis['name'], source),
            'description': protect_text(axis['description'], source), 'score': axis['score'],
            'comment': protect_text(axis['comment'], source), 'evidence': evidence(axis['evidence'])}
            for axis in value['axes']]}


def comparison(value, source):
    if value is None:
        return None
    if value.get('comparison_type') == 'career_comparison':
        result = {'comparison_type': 'career_comparison',
                'overview': protect_text(value['overview'], source),
                **{key: [{'title': protect_text(row['title'], source), 'comment': protect_text(row['comment'], source),
                         'evidence': evidence(row['evidence'])} for row in value[key]] for key in ('related_content','gaps')},
                'conclusion': protect_text(value['conclusion'], source)}
        if value.get('radar') is not None:
            result['radar'] = public_radar(value['radar'], source)
        return result
    result = {'comparison_type': 'course_jd_comparison',
            'overview': protect_text(value['overview'], source),
            'requirement_reviews': [{'jd_requirement': protect_text(row['jd_requirement'], source), 'coverage': row['coverage'],
                'comment': protect_text(row['comment'], source), 'evidence': evidence(row['evidence'])}
                for row in value['requirement_reviews']],
            'conclusion': protect_text(value['conclusion'], source)}
    if value.get('radar') is not None:
        result['radar'] = public_radar(value['radar'], source)
    return result


def message(value, source):
    return {**value, 'reply': protect_text(value['reply'], source), 'evidence': evidence(value['evidence'])}


def check_generated_text(texts, source, *, check_policy=False):
    if any(discloses_source(text, source) for text in texts):
        raise ComparisonError('Generated response disclosed private source text', code='private_source_disclosure')
    if check_policy and any(discloses_policy(text) for text in texts):
        raise ComparisonError('Generated response failed privacy validation', code='private_policy_disclosure')
