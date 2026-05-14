from datetime import datetime


def datetimeformat(value):
    """Фильтр для форматирования дат в шаблонах"""
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    now = datetime.now()
    diff = now - value

    if diff.days == 0:
        return f"Сегодня, {value.strftime('%H:%M')}"
    elif diff.days == 1:
        return f"Вчера, {value.strftime('%H:%M')}"
    elif diff.days == 2:
        return f"Позавчера, {value.strftime('%H:%M')}"
    else:
        return value.strftime('%d %B, %H:%M')
