# cardio.py — логика кардио
# Исправления:
# 1) Добавлен тип 'Скакалка' (jump rope) и тип ввода 'time_distance' и 'reps_or_time'
# 2) Унифицирован парсинг ввода: пользователь может вводить 'time distance' или 'reps' в зависимости от типа
import re

CARDIO_TYPES = {
    'run': {'name': 'Бег', 'input_mode': 'time_distance'},
    'bike': {'name': 'Велотренажер', 'input_mode': 'time_distance'},
    'jump_rope': {'name': 'Скакалка', 'input_mode': 'reps_or_time'},
}

def parse_cardio_input(cardio_type_key: str, text: str):
    """Парсит ввод в зависимости от типа.
    - time_distance: ожидает 'MM:SS 3.5km' или '30:00 5km' или '30' (минуты)
    - reps_or_time: ожидает '120' (прыжков) или '5:00' (время в мин:сек)
    Возвращает dict или None если не распознал.
    """
    cfg = CARDIO_TYPES.get(cardio_type_key)
    if not cfg:
        return None

    mode = cfg['input_mode']
    text = text.strip().lower()
    if mode == 'time_distance':
        # пробуем найти время и дистанцию
        # время форматы: MM:SS или M:SS или integer minutes
        time_match = re.search(r'(\d{1,2}:\d{2})', text)
        dist_match = re.search(r'(\d+(?:[\.,]\d+)?\s*(km|км|m|м))', text)
        minutes_match = re.search(r'^(\d{1,3})$', text)
        result = {}
        if time_match:
            result['time'] = time_match.group(1)
        if dist_match:
            result['distance'] = dist_match.group(1)
        if minutes_match and not (time_match or dist_match):
            result['time_minutes'] = minutes_match.group(1)
        return result if result else None
    else:
        # reps_or_time
        time_match = re.search(r'(\d{1,2}:\d{2})', text)
        reps_match = re.search(r'^(\d{1,6})$', text)
        if reps_match:
            return {'reps': int(reps_match.group(1))}
        if time_match:
            return {'time': time_match.group(1)}
        return None

if __name__ == '__main__':
    tests = [
        ('run', '30:00 5km'),
        ('run', '30 5km'),
        ('jump_rope', '120'),
        ('jump_rope', '5:00')
    ]
    for t in tests:
        print(t, '->', parse_cardio_input(t[0], t[1]))
