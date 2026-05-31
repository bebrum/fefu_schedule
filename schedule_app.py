import argparse
import datetime
import json
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


DB_PATH = Path(__file__).with_name("database.db")
SOURCE_TZ = ZoneInfo("Asia/Vladivostok")
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def get_date_timestamp(y, m, d):
    """Переводит дату в timestamp. В расписании даты хранятся как полночь по Владивостоку."""
    date_obj = datetime.datetime(int(y), int(m), int(d), tzinfo=SOURCE_TZ)
    return int(date_obj.timestamp())


def get_date(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, SOURCE_TZ).date()


def get_weekday_name(date):
    year, month, day = date
    date_obj = datetime.datetime(year, month, day)
    return WEEKDAYS[date_obj.weekday()]


def get_today_date():
    today = datetime.datetime.now(SOURCE_TZ)
    return [today.year, today.month, today.day]


def get_tomorrow_date():
    tomorrow = datetime.datetime.now(SOURCE_TZ) + datetime.timedelta(days=1)
    return [tomorrow.year, tomorrow.month, tomorrow.day]


def time_to_timestamp(time_str):
    """Переводит время HH:MM в количество минут от начала дня."""
    try:
        hours, minutes = map(int, time_str.split(":"))
    except ValueError as error:
        raise ValueError("Неверный формат времени. Нужно 'HH:MM'.") from error

    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ValueError("Время должно быть в диапазоне 00:00–23:59.")

    return hours * 60 + minutes


def timestamp_to_time(timestamp):
    """Переводит количество минут от начала дня в строку HH:MM."""
    if not isinstance(timestamp, int) or timestamp < 0 or timestamp >= 1440:
        raise ValueError("timestamp должен быть целым числом от 0 до 1439.")

    hours = timestamp // 60
    minutes = timestamp % 60
    return f"{hours:02d}:{minutes:02d}"


def process_element(element):
    """Приводит один элемент из ответа API к формату таблицы schedule."""

    def convert_time_format(time_str):
        dt = datetime.datetime.fromisoformat(time_str)
        return dt.strftime("%H:%M")

    return {
        "title": element["title"],
        "start": convert_time_format(element["start"]),
        "end": convert_time_format(element["end"]),
        "date": datetime.datetime.fromisoformat(element["start"]).strftime("%Y-%m-%d"),
        "classroom": element.get("classroom") or None,
        "order": element["order"],
        "pps_load": element["pps_load"],
        "subgroup": element.get("subgroup") or None,
        "teacher": element["teacher"],
    }


def create_schedule_dict(elements):
    schedule_dict = {}

    for element in elements:
        date = element["date"]
        order = element["order"]

        if date not in schedule_dict:
            schedule_dict[date] = {}
        if order not in schedule_dict[date]:
            schedule_dict[date][order] = []

        schedule_dict[date][order].append(element)

    return schedule_dict


def load_request_config(config_path):
    """
    Читает cookies и headers из отдельного json-файла.
    Сам файл с реальными значениями лучше не коммитить в GitHub.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Не найден {config_path}. Скопируй request_config.example.json в request_config.json "
            "и добавь свои актуальные cookies/headers."
        )

    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_agenda(start_date, end_date, group_id="5560", config_path="request_config.json"):
    """Загружает расписание за период из univer.dvfu.ru/schedule/get."""
    config = load_request_config(config_path)

    params = {
        "type": "agendaWeek",
        "start": f"{start_date}T14:00:00.000Z",
        "end": f"{end_date}T14:00:00.000Z",
        "groups[]": group_id,
        "ppsId": "",
        "facilityId": "0",
    }

    response = requests.get(
        "https://univer.dvfu.ru/schedule/get",
        params=params,
        cookies=config.get("cookies", {}),
        headers=config.get("headers", {}),
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()
    return [process_element(item) for item in data.get("events", [])]


def insert_data(s, db_path=DB_PATH):
    """Добавляет одну пару в SQLite."""
    values = (
        s["title"],
        time_to_timestamp(s["start"]),
        time_to_timestamp(s["end"]),
        get_date_timestamp(*s["date"].split("-")),
        s.get("classroom") or None,
        s["order"],
        s["pps_load"],
        s.get("subgroup") or None,
        s["teacher"],
    )

    with sqlite3.connect(db_path) as db:
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO schedule (
                title, start_time, end_time, date, classroom, class_order,
                class_type, subgroup, teacher
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        db.commit()


def add_week_to_date(date_str):
    date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    new_date_obj = date_obj + datetime.timedelta(days=7)
    return new_date_obj.strftime("%Y-%m-%d")


def check_for_none(txt):
    return "" if txt is None else txt


def get_schedule(date, subgroup, db_path=DB_PATH):
    """Возвращает расписание на день для выбранной подгруппы."""
    query = """
        SELECT title, start_time, end_time, classroom, class_type, class_order, teacher
        FROM schedule
        WHERE (subgroup = ? OR subgroup IS NULL)
          AND date = ?
        ORDER BY class_order, start_time
    """

    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        cursor = db.cursor()
        cursor.execute(query, (subgroup, get_date_timestamp(*date)))
        return cursor.fetchall()


def print_schedule(date, subgroup, db_path=DB_PATH):
    schedule = get_schedule(date, subgroup, db_path=db_path)

    print(f"{date[0]}-{date[1]:02d}-{date[2]:02d} ({get_weekday_name(date)}) | подгруппа {subgroup}")

    if not schedule:
        print("Пар не найдено")
        return

    for item in schedule:
        print("___________________________________")
        print(f"{item['class_order']}. {item['title']}")
        print(
            f"{timestamp_to_time(item['start_time'])} - {timestamp_to_time(item['end_time'])}"
            f"    {check_for_none(item['classroom'])}"
        )
        print(f"{item['teacher']}\n{item['class_type']}")


def parse_date(date_str):
    year, month, day = map(int, date_str.split("-"))
    return [year, month, day]


def main():
    parser = argparse.ArgumentParser(description="Показать расписание занятий из SQLite-базы.")
    parser.add_argument("--date", help="Дата в формате YYYY-MM-DD. По умолчанию сегодня.")
    parser.add_argument("--subgroup", type=int, default=1, help="Номер подгруппы. По умолчанию 1.")
    parser.add_argument("--db", default=str(DB_PATH), help="Путь к SQLite-базе.")
    args = parser.parse_args()

    date = parse_date(args.date) if args.date else get_today_date()
    print_schedule(date, args.subgroup, db_path=args.db)


if __name__ == "__main__":
    main()
