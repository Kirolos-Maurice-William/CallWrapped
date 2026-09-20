import re

ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
WESTERN_DIGITS = "0123456789"
DIGIT_MAP = str.maketrans(ARABIC_INDIC_DIGITS, WESTERN_DIGITS)

def clean_arabic_text(text: str) -> str:
    if not text:
        return ""
    
    # 1. Remove bracketed tags like [laughter], [music], <hes>, etc.
    text = re.sub(r'\[.*?\]', ' ', text)
    text = re.sub(r'<.*?>', ' ', text)
    
    # 2. Remove symbols like #, _, etc.
    text = text.replace('#', ' ').replace('_', ' ')
    
    # 3. Strip diacritics (tashkeel): fathatan, dammatan, kasratan, fatha, damma, kasra, shadda, sukun, etc.
    text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
    
    # 4. Remove tatweel / kashida (\u0640)
    text = re.sub(r'\u0640', '', text)
    
    # 5. Unify alef forms (أ, إ, آ, ٱ -> ا)
    text = re.sub(r'[إأآٱ]', 'ا', text)
    
    # 6. Unify ta-marbuta (ة -> ه)
    text = re.sub(r'ة', 'ه', text)
    
    # 7. Unify alif maqsura (ى -> ي)
    text = re.sub(r'ى', 'ي', text)
    
    # 8. Convert Arabic-Indic digits to ASCII 0-9
    text = text.translate(DIGIT_MAP)
    
    # 9. Punctuation & symbols removal (keep unicode word characters: letters and digits)
    # Also replace dots, commas, question marks, exclamation, quotes, dashes with space
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # 10. Lowercase English characters if any
    text = text.lower()
    
    # 11. Collapse multiple whitespace to a single space
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

if __name__ == "__main__":
    import csv
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    
    with open("audit/mgb3_clips/labels.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = row["reference_text"]
            cleaned = clean_arabic_text(raw)
            print(f"[{row['id']}]")
            print(f"  RAW:     {raw}")
            print(f"  CLEANED: {cleaned}\n")
