"""
services/quiz_service.py — توليد الأسئلة عبر OpenAI

إصلاحات:
  - AsyncOpenAI بدلاً من OpenAI المتزامن (ضروري مع asyncio)
  - قراءة الإعدادات من config.py بدلاً من os.getenv مباشرة
  - البرومبت يُرجع correct_index (رقم) بدلاً من answer (نص) للتوافق مع handler
  - retry تلقائي عند فشل الـ API
  - logging بدلاً من print
  - دعم اللغتين العربية والإنجليزية في البرومبت
  - [FIX] تغيير max_tokens → max_completion_tokens (مطلوب في o-series والموديلات الجديدة)
"""
import json
import logging

from openai import AsyncOpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_FALLBACK_MODEL

logger = logging.getLogger(__name__)

# ─── Client (مشترك على مستوى الـ module) ─────────────────────────────────────
_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ─── البرومبتات ──────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = "You are a precise exam question extractor. Return only valid JSON."

_USER_PROMPT_TEMPLATE = """
أنت محرك استخراج أسئلة من اختبارات سابقة.
النص التالي مستخرج من ملف اختبار سابق باللغة {language_label}.

المطلوب: استخرج بالضبط {count} سؤالاً اختيار من متعدد موجودة فعلياً في النص.

القواعد الصارمة:
1. انقل السؤال والخيارات حرفياً كما وردت في النص — لا تعدّل ولا تُبسّط.
2. حدّد correct_index: رقم الخيار الصحيح (0 = الأول، 1 = الثاني، ...).
3. إذا لم تجد الإجابة صراحةً، استنتجها من السياق.
4. إذا لم يكن هناك {count} سؤالاً، أرجع ما وجدته فقط (قائمة فارغة مقبولة).
5. أرجع JSON فقط بدون أي نص إضافي.

صيغة JSON المطلوبة:
{{
  "questions": [
    {{
      "question": "نص السؤال كاملاً",
      "options": ["الخيار 1", "الخيار 2", "الخيار 3", "الخيار 4"],
      "correct_index": 0
    }}
  ]
}}

النص:
{text_content}
"""

# ─── الدالة الرئيسية ──────────────────────────────────────────────────────────

async def generate_questions(
    text_content: str,
    count: int = 5,
    language: str = "arabic",
    max_retries: int = 2,
) -> list[dict]:
    """
    توليد أسئلة اختيار من متعدد من النص المُدخَل.

    Args:
        text_content: النص المستخرج من PDF
        count:        عدد الأسئلة المطلوبة
        language:     "arabic" أو "english"
        max_retries:  عدد محاولات إعادة الطلب عند الفشل

    Returns:
        قائمة من الأسئلة، كل سؤال:
        {"question": str, "options": list[str], "correct_index": int}
    """
    if not text_content or not text_content.strip():
        logger.warning("generate_questions: النص فارغ")
        return []

    # اقتطاع النص للحد الآمن (تقريباً 6000 كلمة)
    trimmed_text = text_content[:8000]

    language_label = "العربية" if language == "arabic" else "English"
    prompt = _USER_PROMPT_TEMPLATE.format(
        count=count,
        language_label=language_label,
        text_content=trimmed_text,
    )

    model_to_use = OPENAI_MODEL

    for attempt in range(1, max_retries + 2):  # +2 = محاولات أصلية + retries
        try:
            response = await _client.chat.completions.create(
                model=model_to_use,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_completion_tokens=4096,  # ✅ FIX: كان max_tokens (غير مدعوم في الموديلات الجديدة)
            )

            raw = response.choices[0].message.content or ""
            data = json.loads(raw)
            questions = data.get("questions", [])

            # التحقق من صحة البنية وتنظيف النتائج
            valid_questions = []
            for q in questions:
                if not isinstance(q, dict):
                    continue
                question_text = q.get("question", "").strip()
                options       = q.get("options", [])
                correct_index = q.get("correct_index", 0)

                # التحقق الأساسي
                if not question_text:
                    continue
                if not isinstance(options, list) or len(options) < 2:
                    continue
                if not isinstance(correct_index, int):
                    # محاولة تحويل للرقم إذا أتى كنص
                    try:
                        correct_index = int(correct_index)
                    except (ValueError, TypeError):
                        correct_index = 0
                # التأكد أن الـ index ضمن النطاق
                correct_index = max(0, min(correct_index, len(options) - 1))

                valid_questions.append({
                    "question":      question_text,
                    "options":       [str(o).strip() for o in options],
                    "correct_index": correct_index,
                })

            logger.info(
                "✅ تم توليد %d سؤال (طُلب %d) — المحاولة %d",
                len(valid_questions), count, attempt,
            )
            return valid_questions

        except json.JSONDecodeError as e:
            logger.warning("JSON parsing error (محاولة %d): %s", attempt, e)

        except Exception as e:
            logger.error("OpenAI API error (محاولة %d): %s", attempt, e)

            # في حالة الفشل المتكرر جرّب الموديل الاحتياطي
            if attempt == 1 and OPENAI_FALLBACK_MODEL:
                logger.info("🔄 جاري التبديل للموديل الاحتياطي: %s", OPENAI_FALLBACK_MODEL)
                model_to_use = OPENAI_FALLBACK_MODEL

    logger.error("❌ فشل توليد الأسئلة بعد %d محاولات", max_retries + 1)
    return []
