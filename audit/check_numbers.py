import sys
import csv
sys.stdout.reconfigure(encoding='utf-8')

NUMBER_MAP = {
    'صفر': 0, '0': 0,
    'واحد': 1, 'واحده': 1, '1': 1,
    'اتنين': 2, 'تنين': 2, 'سنتين': 2, '2': 2,
    'تلاته': 3, 'تلات': 3, 'تلت': 3, 'ثلاثه': 3, 'ثلاث': 3, '3': 3,
    'اربعه': 4, 'اربع': 4, '4': 4,
    'خمسه': 5, 'خمس': 5, '5': 5,
    'سته': 6, 'ست': 6, '6': 6,
    'سبعه': 7, 'سبع': 7, '7': 7,
    'تمانيه': 8, 'تمن': 8, 'ثمانيه': 8, '8': 8,
    'تسعه': 9, 'تسع': 9, '9': 9,
    'عشره': 10, 'عشر': 10, '10': 10,
    'احداشر': 11, 'احد عشر': 11, '11': 11,
    'اتناشر': 12, 'اثنا عشر': 12, '12': 12,
    'عشرين': 20, '20': 20,
    'تلاتين': 30, 'ثلاثين': 30, '30': 30,
    'اربعين': 40, '40': 40,
    'خمسين': 50, '50': 50,
    'ستين': 60, '60': 60,
    'سبعين': 70, '70': 70,
    'تمانين': 80, 'ثمانين': 80, '80': 80,
    'تسعين': 90, '90': 90,
    'ميه': 100, 'مائه': 100, '100': 100,
    'الف': 1000, '1000': 1000,
    'الفين': 2000, '2000': 2000
}

def get_numbers(text):
    tokens = text.split()
    found = []
    for t in tokens:
        if t.isdigit():
            found.append((t, int(t)))
        elif t in NUMBER_MAP:
            found.append((t, NUMBER_MAP[t]))
        elif t.startswith('و') and len(t) > 1 and t[1:] in NUMBER_MAP:
            found.append((t, NUMBER_MAP[t[1:]]))
    return found

with open('audit/mgb3_clips/labels.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        nums = get_numbers(r['reference_cleaned'])
        if nums:
            print(f"{r['id']} ({r['genre']}): {nums}")
