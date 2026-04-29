import hashlib
import pdfplumber
import re

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    BIDI_AVAILABLE = True
except ImportError:
    BIDI_AVAILABLE = False


# ─────────────────────────────────────────────
# Arabic text fix
# ─────────────────────────────────────────────

def _is_arabic(text):
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    return arabic_chars > len(text) * 0.2


def _fix_arabic_line(line):
    """
    يصلح الخط المقلوب:
    1. arabic_reshaper يُعيد تشكيل الحروف المتصلة
    2. get_display يُعيد الترتيب من البصري إلى المنطقي
    """
    if not BIDI_AVAILABLE or not line.strip():
        return line
    try:
        reshaped = arabic_reshaper.reshape(line)
        return get_display(reshaped)
    except Exception:
        return line


def fix_arabic_text(text):
    if not text:
        return text
    if not _is_arabic(text):
        return text

    lines = text.split('\n')
    fixed_lines = []
    for line in lines:
        if line.strip():
            fixed_lines.append(_fix_arabic_line(line))
        else:
            fixed_lines.append(line)
    return '\n'.join(fixed_lines)


# ─────────────────────────────────────────────
# Core functions
# ─────────────────────────────────────────────

def sha256_bytes( bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_valid_pdf_bytes( bytes) -> bool:
    return data[:4] == b'%PDF'


def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    pages_text = []

    with pdfplumber.open(file_bytes if hasattr(file_bytes, 'read') else __import__('io').BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # استخراج النص مع الحفاظ على ترتيب القراءة
            text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if text and text.strip():
                pages_text.append(text.strip())

    full_text = '\n\n'.join(pages_text)

    # إصلاح النص العربي المقلوب
    full_text = fix_arabic_text(full_text)

    return full_text
