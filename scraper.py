#!/usr/bin/env python

import datetime
import os
import re
import requests
import time
from typing import Dict, List, NamedTuple
from requests.exceptions import HTTPError, Timeout, JSONDecodeError
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from statsd import StatsClient

# Configuration
STATSD_SERVER = os.getenv("STATSD_SERVER", "localhost")
statsd = StatsClient(STATSD_SERVER, 8125, prefix="celcat_scraper")


class ClassInfo(NamedTuple):
    name: str
    rooms: List[str]


def measure_time(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        statsd.timing(f"{func.__name__}.time", elapsed_time)
        return result

    return wrapper


@measure_time
def login(driver: webdriver.Chrome, username: str, password: str):
    try:
        driver.get("https://timetable.nulondon.ac.uk/cal?vt=month")
        driver.find_element(By.ID, "Name").send_keys(username)
        driver.find_element(By.ID, "Password").send_keys(password)
        driver.find_element(By.ID, "Password").send_keys(Keys.RETURN)
        statsd.incr("login.success")
    except NoSuchElementException:
        statsd.incr("login.failure")
        raise


@measure_time
def fetch_calendar_data(
    session: requests.Session, headers: Dict[str, str], person_id: str
):
    today = datetime.date.today()
    endpoint = "https://timetable.nulondon.ac.uk/Home/GetCalendarData"
    data = {
        "start": today,
        "end": today,
        "resType": "104",
        "calView": "month",
        "federationIds[]": person_id,
    }

    try:
        response = session.post(endpoint, headers=headers, data=data)
        response.raise_for_status()
        return response.json()
    except (HTTPError, Timeout) as err:
        statsd.incr("fetch_calendar_data.failure")
        raise err
    except JSONDecodeError:
        statsd.incr("fetch_calendar_data.json_decode_failure")
        return []


@measure_time
def extract_class_and_rooms(calendar_data: List[Dict[str, str]]):
    class_info = []
    room_regex = re.compile(r"\d+\s\[[\d\sCap]+\]")

    for entry in calendar_data:
        class_name, *rest = entry["description"].split("_")
        rooms = room_regex.findall(entry["description"])
        class_info.append(ClassInfo(class_name, rooms))

    return class_info


@measure_time
def send_notifications(classes: List[ClassInfo], ntfy_key: str, person_name: str):
    endpoint = f"https://ntfy.sh/{ntfy_key}-{person_name}"
    for class_info in classes:
        message = f"Class: {class_info.name}, Rooms: {', '.join(class_info.rooms)}"
        try:
            requests.post(endpoint, data=message.encode("utf-8"), timeout=10)
            statsd.incr("notification.sent")
        except Timeout as err:
            statsd.incr("notification.failure")
            raise err


def main():
    try:
        ntfy_key = os.getenv("NTFY_KEY")
        username = os.getenv("USERNAME")
        password = os.getenv("PASSWORD")

        options = webdriver.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")

        with webdriver.Chrome(options=options) as driver:
            login(driver, username, password)
            cookies = driver.get_cookies()

        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(cookie["name"], cookie["value"])

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

        people = [
            {"name": "Lucas", "fedId": "02267113"},
            {"name": "Tanay", "fedId": "02256085"},
        ]
        for person in people:
            if calendar_data := fetch_calendar_data(
                session, headers, person["fedId"]
            ):
                classes = extract_class_and_rooms(calendar_data)
                send_notifications(classes, ntfy_key, person["name"])

        statsd.incr("success")
    except Exception as err:
        statsd.incr("failure")
        raise err


if __name__ == "__main__":
    main()
