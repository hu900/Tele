import json
import re
import random
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_FALLBACK_MODEL, MAX_CHUNK_TEXT_CHARS

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

MAX_Q_LEN = 400
MIN_Q_LEN = 10
MAX_OPT_LEN = 300
MIN_OPT_LEN = 1
OPTION_KEYS = ["A", "B", "C", "D"]


# ─────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────

def build_system_prompt():
    return """أنت أداة استخراج أسئلة اختبار من نصوص تجميعات أكاديمية.

النص الذي ستستقبله يحتوي أسئلة اختبار حقيقية موجودة بالفعل مع خياراتها وإجاباتها.

مهمتك الوحيدة:
- اقرأ النص وحدد الأسئلة الموجودة فيه.
- استخرج كل سؤال مع خياراته وإجابته الصحيحة كما هي في النص حرفيًا.
- لا تُولِّد ولا تُعدِّل ولا تُضف أي شيء من عندك.
- إذا كانت الإجابة الصحيحة مُحددة في النص (بعلامة، أو بذكر الإجابة، أو بأي طريقة)، استخرجها.
- إذا لم تجد إجابة محددة في النص، استنتجها من السياق فقط إذا كانت واضحة جدًا.
- إذا لم تستطع تحديد الإجابة، تجاهل هذا السؤال ولا تُدرجه."""


def build_system_prompt_en():
    return """You are an exam question extractor from academic past paper collections.

The text you receive contains real exam questions that already exist with their choices and answers.

Your only task:
- Read the text and identify existing questions.
- Extract each question with its choices and correct answer exactly as they appear in the text verbatim.
- Do not generate, modify, or add anything from your own knowledge.
- If the correct answer is marked in the text (by symbol, mention, or any method), extract it.
- If no answer is explicitly marked, infer it from context only if it is very obvious.
- If you cannot determine the answer, skip this question entirely."""


def build_user_prompt_ar(chunk_text):
    return f"""النص التالي مأخوذ من تجميعات اختبارات أكاديمية:
---
{chunk_text}
---

المطلوب:
استخرج جميع الأسئلة الموجودة في هذا النص مع خياراتها وإجاباتها الصحيحة.

قواعد الاستخراج:
- السؤال: انسخه كما هو من النص بالكامل.
- الخيارات: انسخ الخيارات الأربعة كما هي. إذا كانت أقل من أربعة، أكملها بخيارات منطقية من النص فقط.
- الإجابة الصحيحة: انسخها كما هي. إذا كانت محددة بحرف (أ، ب، ج، د أو A، B، C، D) اجعل correct هو الحرف الإنجليزي المقابل.
- لا تُبدّل ولا تُعدّل أي نص.

أرجع JSON فقط بهذا الشكل:
{{
  "questions": [
    {{
      "question": "نص السؤال كاملًا كما في المصدر",
      "choices": {{
        "A": "نص الخيار الأول كما في المصدر",
        "B": "نص الخيار الثاني كما في المصدر",
        "C": "نص الخيار الثالث كما في المصدر",
        "D": "نص الخيار الرابع كما في المصدر"
      }},
      "correct": "A",
      "source_quote": "الجملة أو الرمز الذي حدد الإجابة في النص"
    }}
  ]
}}

إذا لم يوجد أي سؤال قابل للاستخراج في هذا النص، أرجع:
{{"questions": []}}"""


def build_user_prompt_en(chunk_text):
    return f"""The following text is taken from academic past exam paper collections:
---
{chunk_text}
---

Required:
Extract all questions that exist in this text along with their choices and correct answers.

Extraction rules:
- Question: copy it exactly as it appears in the text.
- Choices: copy all four choices as they are. If fewer than four exist, fill in with logical options from the same text only.
- Correct answer: copy it as-is. If marked by a letter (A, B, C, D), set correct to that letter.
- Do not alter or modify any text.

Return JSON only in this format:
{{
  "questions": [
    {{
      "question": "full question text exactly as in source",
      "choices": {{
        "A": "first choice text as in source",
        "B": "second choice text as in source",
        "C": "third choice text as in source",
        "D": "fourth choice text as in source"
      }},
      "correct": "A",
      "source_quote": "the sentence or symbol that marked the answer in the text"
    }}
  ]
}}

If no extractable question exists in this text, return:
{{"questions": []}}"""


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _normalize(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _call_openai(system_msg, user_msg, model_name, temperature=0.0):
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    return response.choices[0].message.content


def _parse_json(raw):
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _validate_question(data):
    question = _normalize(data.get("question", ""))
    choices_raw = data.get("choices", {})
    correct = _normalize(data.get("correct", "")).upper()
    source_quote = _normalize(data.get("source_quote", ""))

    if not question or len(question) < MIN_Q_LEN or len(question) > MAX_Q_LEN:
        return None

    if not isinstance(choices_raw, dict):
        return None

    choices = {}
    for key in OPTION_KEYS:
        val = _normalize(choices_raw.get(key, ""))
        if not val or len(val) < MIN_OPT_LEN or len(val) > MAX_OPT_LEN:
            return None
        choices[key] = val

    # لا تكرار في الخيارات
    if len(set(v.lower() for v in choices.values())) != 4:
        return None

    if correct not in OPTION_KEYS:
        return None

    return {
        "question": question,
        "choices": choices,
        "correct": correct,
        "source_quote": source_quote,
    }


def _to_output_format(question):
    """
    يحول السؤال إلى الشكل الذي يتوقعه handlers/quiz.py:
    - options: قائمة مرتبة A→D
    - answer: النص الحرفي للإجابة الصحيحة
    يخلط الخيارات عشوائيًا حتى لا تكون الإجابة دائمًا في نفس الموضع.
    """
    correct_letter = question["correct"]
    correct_text = question["choices"][correct_letter]

    options = list(question["choices"].values())
    random.shuffle(options)

    return {
        "question": question["question"],
        "options": options,
        "answer": correct_text,
    }


def _models_to_try():
    models = []
    if OPENAI_MODEL:
        models.append(OPENAI_MODEL)
    if OPENAI_FALLBACK_MODEL and OPENAI_FALLBACK_MODEL != OPENAI_MODEL:
        models.append(OPENAI_FALLBACK_MODEL)
    return models


# ─────────────────────────────────────────────
# الاستخراج من chunk واحد
# ─────────────────────────────────────────────

def _extract_from_chunk(chunk, language, model_name):
    chunk_text = _normalize(chunk.get("chunk_text", ""))[:MAX_CHUNK_TEXT_CHARS]
    if not chunk_text or len(chunk_text) < 40:
        return []

    try:
        if language == "arabic":
            system_msg = build_system_prompt()
            user_msg = build_user_prompt_ar(chunk_text)
        else:
            system_msg = build_system_prompt_en()
            user_msg = build_user_prompt_en(chunk_text)

        # temperature=0 لأن المهمة استخراج لا توليد
        raw = _call_openai(system_msg, user_msg, model_name, temperature=0.0)
        data = _parse_json(raw)
        raw_questions = data.get("questions", [])

        if not isinstance(raw_questions, list):
            return []

        results = []
        for raw_q in raw_questions:
            validated = _validate_question(raw_q)
            if validated:
                results.append(_to_output_format(validated))

        return results

    except Exception:
        return []


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def generate_quiz_from_chunks(chunks, num_q=5, language="arabic"):
    if not client or not chunks:
        return []

    all_extracted = []
    seen_questions = set()

    for model_name in _models_to_try():

        shuffled_chunks = list(chunks)
        random.shuffle(shuffled_chunks)

        for chunk in shuffled_chunks:
            extracted = _extract_from_chunk(chunk, language, model_name)

            for item in extracted:
                key = item["question"].lower().strip()
                if key in seen_questions:
                    continue
                seen_questions.add(key)
                all_extracted.append(item)

            if len(all_extracted) >= num_q * 2:
                break

        if all_extracted:
            break

    random.shuffle(all_extracted)
    return all_extracted[:num_q]
