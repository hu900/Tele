import hashlib
import re
from collections import Counter
from config import CHUNK_TARGET_CHARS, CHUNK_MIN_CHARS, CHUNK_MAX_CHARS

AR_STOPWORDS = {
    "في", "من", "على", "إلى", "عن", "هذا", "هذه", "ذلك", "تلك", "كان", "كانت",
    "هو", "هي", "ثم", "كما", "أو", "و", "ف", "ب", "ل", "أن", "إن", "قد", "تم",
    "ما", "مع", "بعد", "قبل", "بين", "إذا", "كل", "أي", "أحد", "هناك", "هنا",
    "عند", "ضمن", "حول", "حتى", "لم", "لن", "لا", "غير", "بعض", "أكثر", "أقل"
}

EN_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "from", "with",
    "by", "at", "as", "is", "are", "was", "were", "be", "been", "being", "that",
    "this", "these", "those", "it", "its", "if", "then", "than", "into", "about",
    "over", "under", "between", "during", "before", "after", "such", "can", "could",
    "may", "might", "will", "would", "should", "not", "no", "yes", "more", "most"
}

def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def split_into_sentences(text: str):
    text = normalize_text(text)
    parts = re.split(r'(?<=[\.\!\?؟])\s+|\n+', text)
    return [p.strip() for p in parts if p.strip()]

def build_chunks(text: str, target_chars=CHUNK_TARGET_CHARS, min_chars=CHUNK_MIN_CHARS, max_chars=CHUNK_MAX_CHARS):
    sentences = split_into_sentences(text)
    if not sentences:
        text = normalize_text(text)
        return [text] if text else []

    chunks = []
    current = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        parts = [sentence]
        if len(sentence) > max_chars:
            parts = [p.strip() for p in re.split(r'[،,;؛]\s*', sentence) if p.strip()]

        for part in parts:
            part_len = len(part) + 1
            if current and (current_len + part_len > target_chars) and current_len >= min_chars:
                chunks.append(" ".join(current).strip())
                current = [part]
                current_len = len(part)
            else:
                current.append(part)
                current_len += part_len

    if current:
        final_chunk = " ".join(current).strip()
        if chunks and len(final_chunk) < min_chars:
            chunks[-1] = f"{chunks[-1]} {final_chunk}".strip()
        else:
            chunks.append(final_chunk)

    return [c for c in chunks if len(c) >= 120]

def _extract_words(text: str, language: str):
    if language == "arabic":
        return re.findall(r'[\u0600-\u06FF]{3,}', text)
    return re.findall(r'[A-Za-z]{3,}', text.lower())

def extract_keywords(text: str, language: str, top_n=8):
    words = _extract_words(text, language)
    stopwords = AR_STOPWORDS if language == "arabic" else EN_STOPWORDS
    words = [w for w in words if w.lower() not in stopwords]
    freq = Counter(words)
    return [word for word, _ in freq.most_common(top_n)]

def extract_learning_points(text: str, language: str, max_points=4):
    sentences = split_into_sentences(text)
    points = []
    for s in sentences:
        s = s.strip()
        if len(s) < 40:
            continue
        if s in points:
            continue
        points.append(s)
        if len(points) >= max_points:
            break
    return points

def prepare_chunks(file_hash: str, text: str, language: str):
    text = normalize_text(text)
    raw_chunks = build_chunks(text)
    result = []

    for idx, chunk_text in enumerate(raw_chunks):
        chunk_hash = hashlib.sha256(f"{file_hash}:{idx}:{chunk_text}".encode("utf-8")).hexdigest()
        result.append({
            "chunk_index": idx,
            "chunk_hash": chunk_hash,
            "chunk_text": chunk_text,
            "keywords": extract_keywords(chunk_text, language),
            "learning_points": extract_learning_points(chunk_text, language),
        })

    return result
