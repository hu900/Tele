import json
import re
import random
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_FALLBACK_MODEL, MAX_CHUNK_TEXT_CHARS

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

MAX_Q_LEN = 220
MIN_Q_LEN = 12
MAX_OPT_LEN = 90
MIN_OPT_LEN = 1
OPTION_KEYS = ["A", "B", "C", "D"]


# ─────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────

def build_system_prompt():
    return """أنت أداة نسخ ومطابقة من نص أكاديمي — لا تُعدِّل ولا تُبدع.

مهمتك: انسخ سؤالاً وإجابته من النص كما هما حرفيًا.

قواعد صارمة:
1. السؤال يجب أن يكون منسوخًا حرفيًا من النص — لا تصغ سؤالاً من عندك أبدًا.
2. الإجابة الصحيحة منسوخة حرفيًا من النص بدون تغيير أي كلمة.
3. المشتتات الثلاثة مأخوذة حرفيًا من نفس النص لكن في سياق مختلف.
4. لا تُضف كلمة واحدة من عندك — كل كلمة في السؤال والخيارات يجب أن تكون موجودة في النص.
5. إذا لم يوجد في النص سؤال صريح، اصنع جملة سؤالية فقط بتحويل جملة خبرية من النص إلى استفهام.
6. ضع الإجابة الصحيحة في موضع عشوائي من A إلى D — ليس دائمًا A."""


def build_system_prompt_en():
    return """You are a copy-and-match tool from academic text — no creativity, no modification.

Your task: copy a question and its answer from the text verbatim.

Strict rules:
1. The question must be copied verbatim from the text — never compose a question from your own words.
2. The correct answer is copied verbatim from the text without changing any word.
3. The three distractors are taken verbatim from the same text but in a different context.
4. Do not add a single word of your own — every word in the question and options must exist in the text.
5. If no explicit question exists in the text, convert an existing declarative sentence into a question form only.
6. Place the correct answer in a random position from A to D — not always A."""


def build_user_prompt_ar(chunk_text):
    correct_position = random.choice(OPTION_KEYS)
    return f"""النص المصدر:
---
{chunk_text}
---

التعليمات:
1. ابحث في النص عن جملة تحتوي معلومة واضحة (رقم، تعريف، اسم، شرط، خطوة).
2. انسخ الجملة كما هي واحوّلها إلى سؤال باستبدال المعلومة بفراغ أو علامة استفهام.
3. الإجابة الصحيحة = المعلومة المحذوفة من الجملة — منسوخة حرفيًا.
4. الخيارات الخاطئة = معلومات مشابهة من نفس النص في سياق آخر — منسوخة حرفيًا.
5. ضع الإجابة الصحيحة في الموضع {correct_position}.
6. لا تضف ولا تعدّل أي كلمة من عندك.

أرجع JSON فقط:
{{
  "question": "الجملة من النص مع فراغ أو سؤال مباشر",
  "choices": {{
    "A": "نص من النص حرفيًا",
    "B": "نص من النص حرفيًا",
    "C": "نص من النص حرفيًا",
    "D": "نص من النص حرفيًا"
  }},
  "correct": "{correct_position}",
  "source_quote": "الجملة الحرفية الكاملة من النص"
}}"""


def build_user_prompt_en(chunk_text):
    correct_position = random.choice(OPTION_KEYS)
    return f"""Source text:
---
{chunk_text}
---

Instructions:
1. Find a sentence in the text that contains a clear fact (number, definition, name, condition, step).
2. Copy the sentence as-is and convert it into a question by replacing the fact with a blank or question form.
3. Correct answer = the removed fact from the sentence — copied verbatim.
4. Wrong choices = similar facts from the same text in a different context — copied verbatim.
5. Place the correct answer at position {correct_position}.
6. Do not add or modify any word of your own.

Return JSON only:
{{
  "question": "the sentence from the text with a blank or direct question",
  "choices": {{
    "A": "verbatim text from source",
    "B": "verbatim text from source",
    "C": "verbatim text from source",
    "D": "verbatim text from source"
  }},
  "correct": "{correct_position}",
  "source_quote": "the complete verbatim sentence from the text"
}}"""


def build_verifier_prompt_ar(question, chunk_text):
    correct_letter = question["correct"]
    correct_text = question["choices"].get(correct_letter, "")
    return f"""تحقق من سؤال واحد فقط:

النص المصدر:
---
{chunk_text}
---

السؤال: {question["question"]}
الإجابة المختارة: {correct_letter}) {correct_text}
الاقتباس المرجعي: {question.get("source_quote", "")}

هل هذه الإجابة موجودة في النص بشكل مباشر أو ضمني واضح؟

أرجع JSON فقط:
{{
  "verdict": "PASS",
  "reason": ""
}}"""


def build_verifier_prompt_en(question, chunk_text):
    correct_letter = question["correct"]
    correct_text = question["choices"].get(correct_letter, "")
    return f"""Verify one question only:

Source text:
---
{chunk_text}
---

Question: {question["question"]}
Marked answer: {correct_letter}) {correct_text}
Reference quote: {question.get("source_quote", "")}

Is this answer directly or clearly implicitly supported by the text?

Return JSON only:
{{
  "verdict": "PASS",
  "reason": ""
}}"""


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _normalize(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _call_openai(system_msg, user_msg, model_name, temperature=0.2):
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


def _validate_raw_question(data):
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

    if len(set(v.lower() for v in choices.values())) != 4:
        return None

    if correct not in OPTION_KEYS:
        return None

    if not source_quote or len(source_quote) < 5:
        return None

    return {
        "question": question,
        "choices": choices,
        "correct": correct,
        "source_quote": source_quote,
    }


def _shuffle_options(question):
    """
    يخلط الخيارات عشوائيًا بعد التوليد بغض النظر عن موضعها الأصلي،
    ويحفظ الإجابة كنص حرفي لا كحرف، حتى لا يتأثر بالخلط.
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


def _verify_question(question, chunk_text, language, model_name, strict=True):
    try:
        if language == "arabic":
            system_msg = "أنت مدقق جودة. أرجع JSON فقط."
            user_msg = build_verifier_prompt_ar(question, chunk_text)
        else:
            system_msg = "You are a quality verifier. Return JSON only."
            user_msg = build_verifier_prompt_en(question, chunk_text)

        temp = 0.0 if strict else 0.1
        raw = _call_openai(system_msg, user_msg, model_name, temperature=temp)
        data = _parse_json(raw)
        verdict = _normalize(data.get("verdict", "")).upper()
        return verdict == "PASS"
    except Exception:
        return not strict


def _models_to_try():
    models = []
    if OPENAI_MODEL:
        models.append(OPENAI_MODEL)
    if OPENAI_FALLBACK_MODEL and OPENAI_FALLBACK_MODEL != OPENAI_MODEL:
        models.append(OPENAI_FALLBACK_MODEL)
    return models


# ─────────────────────────────────────────────
# توليد سؤال واحد من chunk واحد
# ─────────────────────────────────────────────

def _generate_one(chunk, language, model_name, strict_verify=True):
    chunk_text = _normalize(chunk.get("chunk_text", ""))[:MAX_CHUNK_TEXT_CHARS]
    if not chunk_text or len(chunk_text) < 80:
        return None

    try:
        if language == "arabic":
            system_msg = build_system_prompt()
            user_msg = build_user_prompt_ar(chunk_text)
        else:
            system_msg = build_system_prompt_en()
            user_msg = build_user_prompt_en(chunk_text)

        raw = _call_openai(system_msg, user_msg, model_name, temperature=0.2)
        data = _parse_json(raw)
        question = _validate_raw_question(data)
        if not question:
            return None

        verified = _verify_question(
            question, chunk_text, language, model_name, strict=strict_verify
        )
        if not verified:
            return None

        return _shuffle_options(question)

    except Exception:
        return None


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def generate_quiz_from_chunks(chunks, num_q=5, language="arabic"):
    if not client or not chunks:
        return []

    results = []
    seen_questions = set()

    for model_name in _models_to_try():

        shuffled_chunks = list(chunks)
        random.shuffle(shuffled_chunks)

        # المرحلة الأولى: تحقق صارم
        for chunk in shuffled_chunks:
            if len(results) >= num_q:
                break

            question_result = _generate_one(
                chunk, language, model_name, strict_verify=True
            )
            if not question_result:
                continue

            key = question_result["question"].lower().strip()
            if key in seen_questions:
                continue

            seen_questions.add(key)
            results.append(question_result)

        # المرحلة الثانية: إذا لم نصل للعدد المطلوب، نُكمل بدون verifier
        if len(results) < num_q:
            random.shuffle(shuffled_chunks)
            for chunk in shuffled_chunks:
                if len(results) >= num_q:
                    break

                question_result = _generate_one(
                    chunk, language, model_name, strict_verify=False
                )
                if not question_result:
                    continue

                key = question_result["question"].lower().strip()
                if key in seen_questions:
                    continue

                seen_questions.add(key)
                results.append(question_result)

        if results:
            break

    random.shuffle(results)
    return results[:num_q]
