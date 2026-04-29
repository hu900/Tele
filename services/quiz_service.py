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
    return """أنت أداة استخراج أسئلة من نصوص أكاديمية.

مهمتك الوحيدة: استخرج معلومة واحدة محددة من النص وحوّلها إلى سؤال اختياري.

قواعد غير قابلة للكسر:
1. السؤال يجب أن يكون حفظيًا مباشرًا — المستخدم يحتاج يتذكر المعلومة كما هي في النص.
2. الإجابة الصحيحة يجب أن تكون مأخوذة حرفيًا أو بتصرف طفيف جدًا من النص.
3. المشتتات الثلاثة تكون أرقام أو مصطلحات مشابهة موجودة في النص ذاته لكنها تنتمي لسياق مختلف.
4. إذا كانت المعلومة في النص تحتمل إجابة "جميع ما سبق" اجعلها خيارًا طبيعيًا ضمن الخيارات.
5. لا تُبسّط ولا تُعيد صياغة — اسحب المعلومة كما هي.
6. لا تضع تلميحات في صياغة السؤال تكشف الإجابة."""


def build_system_prompt_en():
    return """You are an extraction tool for academic text questions.

Your only task: extract one specific fact from the text and convert it into a multiple-choice question.

Non-negotiable rules:
1. The question must test direct recall — the user needs to remember the information as it appears in the text.
2. The correct answer must be taken verbatim or with very minor rewording from the text.
3. The three distractors must be similar numbers or terms that actually appear in the same text but belong to a different context.
4. If the information logically supports "All of the above" as a correct answer, include it as a normal choice.
5. Do not simplify or rephrase — extract the information as-is.
6. Do not add hints in the question wording that reveal the answer."""


def build_user_prompt_ar(chunk_text):
    return f"""النص:
---
{chunk_text}
---

المطلوب باللغة العربية:
- اختر حقيقة واحدة محددة من النص (رقم، تعريف، خطوة، شرط، اسم، تاريخ...).
- اصنع منها سؤالًا يختبر الحفظ المباشر.
- الإجابة الصحيحة مأخوذة من النص حرفيًا.
- المشتتات من نفس النص لكن في سياق مختلف.
- إذا كان منطقيًا أن تكون "جميع ما سبق" إجابةً صحيحة، ضعها خيارًا عاديًا.

أرجع JSON فقط بهذا الشكل الحرفي:
{{
  "question": "...",
  "choices": {{
    "A": "...",
    "B": "...",
    "C": "...",
    "D": "..."
  }},
  "correct": "A",
  "explanation": "مذكور في النص: \\"...\\"",
  "source_quote": "الجملة الحرفية من النص"
}}"""


def build_user_prompt_en(chunk_text):
    return f"""Text:
---
{chunk_text}
---

Required in English:
- Pick one specific fact from the text (number, definition, step, condition, name, date...).
- Create a question that tests direct recall.
- The correct answer is taken verbatim from the text.
- Distractors come from the same text but in a different context.
- If "All of the above" is logically correct, include it as a normal choice.

Return JSON only in this exact format:
{{
  "question": "...",
  "choices": {{
    "A": "...",
    "B": "...",
    "C": "...",
    "D": "..."
  }},
  "correct": "A",
  "explanation": "Mentioned in the text: \\"...\\"",
  "source_quote": "exact sentence from the text"
}}"""


def build_verifier_prompt_ar(question, chunk_text):
    correct_letter = question["correct"]
    correct_text = question["choices"].get(correct_letter, "")
    return f"""تحقق فقط من سؤال واحد:

النص المصدر:
---
{chunk_text}
---

السؤال: {question["question"]}
الإجابة المختارة: {correct_letter}) {correct_text}

سؤال واحد فقط: هل هذه الإجابة موجودة في النص بشكل مباشر أو ضمني واضح؟

أرجع JSON فقط:
{{
  "verdict": "PASS",
  "reason": ""
}}

أو إذا فشل:
{{
  "verdict": "FAIL",
  "reason": "السبب"
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

One question only: Is this answer directly or clearly implicitly supported by the text?

Return JSON only:
{{
  "verdict": "PASS",
  "reason": ""
}}

Or if failed:
{{
  "verdict": "FAIL",
  "reason": "reason"
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


def _verify_question(question, chunk_text, language, model_name):
    try:
        if language == "arabic":
            system_msg = "أنت مدقق جودة. أرجع JSON فقط."
            user_msg = build_verifier_prompt_ar(question, chunk_text)
        else:
            system_msg = "You are a quality verifier. Return JSON only."
            user_msg = build_verifier_prompt_en(question, chunk_text)

        raw = _call_openai(system_msg, user_msg, model_name, temperature=0.0)
        data = _parse_json(raw)
        verdict = _normalize(data.get("verdict", "")).upper()
        return verdict == "PASS"
    except Exception:
        return False


def _to_output_format(question):
    options = [question["choices"][k] for k in OPTION_KEYS]
    correct_idx = OPTION_KEYS.index(question["correct"])
    answer = options[correct_idx]
    return {
        "question": question["question"],
        "options": options,
        "answer": answer,
    }


def _pick_chunks(chunks, needed):
    sorted_chunks = sorted(chunks, key=lambda c: (c.get("used_count", 0), c.get("last_used_at") or ""))
    return sorted_chunks[:needed]


def _models_to_try():
    models = []
    if OPENAI_MODEL:
        models.append(OPENAI_MODEL)
    if OPENAI_FALLBACK_MODEL and OPENAI_FALLBACK_MODEL != OPENAI_MODEL:
        models.append(OPENAI_FALLBACK_MODEL)
    return models


# ─────────────────────────────────────────────
# Core: توليد سؤال واحد من chunk واحد
# ─────────────────────────────────────────────

def _generate_one(chunk, language, model_name):
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

        verified = _verify_question(question, chunk_text, language, model_name)
        if not verified:
            return None

        return _to_output_format(question)

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
        selected = _pick_chunks(chunks, max(num_q * 2, num_q + 4))
        random.shuffle(selected)

        for chunk in selected:
            if len(results) >= num_q:
                break

            question_result = _generate_one(chunk, language, model_name)
            if not question_result:
                continue

            key = question_result["question"].lower().strip()
            if key in seen_questions:
                continue

            seen_questions.add(key)
            results.append(question_result)

        if len(results) >= max(2, num_q // 2):
            break

    random.shuffle(results)
    return results[:num_q]
