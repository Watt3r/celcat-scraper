#!/usr/bin/env python

import datetime
import os
import re
import sys
import time
from typing import Dict, List, NamedTuple, Optional

import requests
from requests.exceptions import JSONDecodeError, RequestException
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from statsd import StatsClient

# Set up statsd client
statsd = StatsClient(
    os.getenv("STATSD_SERVER", "localhost"), 8125, prefix="celcat_scraper"
)


class ClassInfo(NamedTuple):
    """
    Represents the information about a class and its associated rooms.
    """

    class_name: str
    rooms: List[str]


def measure_time(func):
    """
    Decorator to measure execution time of a function.
    Sends the timing metric to StatsD.
    """

    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        statsd.timing(f"{func.__name__}.time", elapsed)
        return result

    return wrapper


@measure_time
def login_to_website(driver: WebDriver, username: str, password: str) -> None:
    """
    Logs into the website using Selenium.
    """
    try:
        driver.get("https://timetable.nulondon.ac.uk/cal?vt=month")
        driver.find_element(By.ID, "Name").send_keys(username)
        driver.find_element(By.ID, "Password").send_keys(password)
        driver.find_element(By.ID, "Password").send_keys(Keys.RETURN)
        statsd.incr("login.success")
    except NoSuchElementException as err:
        statsd.incr("login.failure")
        raise err


@measure_time
def fetch_calendar_data(
    session: requests.Session, headers: Dict[str, str], person: Dict[str, str]
) -> Optional[List[Dict[str, str]]]:
    """
    Fetches calendar data for a given person and date.
    """
    today = datetime.date.today()

    data = {
        "start": today,
        "end": today,
        "resType": "104",
        "calView": "month",
        "federationIds[]": person["fedId"],
    }

    try:
        response = session.post(
            "https://timetable.nulondon.ac.uk/Home/GetCalendarData",
            headers=headers,
            data=data,
        )
    except RequestException as err:
        statsd.incr("fetch_calendar_data.failure")
        raise err

    if response.status_code != 200:
        statsd.incr("fetch_calendar_data.failure")
        return None

    try:
        json_data = response.json()
    except JSONDecodeError:
        statsd.incr("fetch_calendar_data.invalid_json")
        return None

    statsd.incr("fetch_calendar_data.success")
    return json_data


@measure_time
def extract_class_and_rooms(data: List[Dict[str, str]]) -> List[ClassInfo]:
    """
    Extracts class and room information from calendar data.
    """
    class_and_rooms = []
    room_regex = re.compile(r"\d+\s\[[\d\sCap]+\]")

    for entry in data:
        description = entry["description"]
        class_name = description.split("_")[0]
        rooms = room_regex.findall(description)

        class_and_rooms.append(ClassInfo(class_name, rooms))

    return class_and_rooms


@measure_time
def send_notifications(
    classes: List[ClassInfo], ntfy_key: str, person: Dict[str, str]
) -> None:
    """
    Sends notifications for each class and room combination.
    """
    for item in classes:
        try:
            requests.post(
                f"https://ntfy.sh/{ntfy_key}-{person['name']}",
                data=f"Class: {item.class_name}, Rooms: {', '.join(item.rooms)}".encode(
                    encoding="utf-8"
                ),
                timeout=10,
            )
            statsd.incr("notification.sent")
        except RequestException as err:
            statsd.incr("notification.failure")
            raise err


def main():
    """
    Main function.
    """
    try:
        ntfy_key = os.getenv("NTFY_KEY")
        username = os.getenv("USERNAME")
        password = os.getenv("PASSWORD")

        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(options=chrome_options)
        login_to_website(driver, username, password)

        cookies = driver.get_cookies()
        driver.quit()

        s = requests.Session()
        for cookie in cookies:
            s.cookies.set(cookie["name"], cookie["value"])

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

        people = [
            {
                "name": "Lucas",
                "fedId": "02267113",
            },
            {
                "name": "Tanay",
                "fedId": "02256085",
            },
        ]

        for person in people:
            data = fetch_calendar_data(s, headers, person)
            if data:
                classes = extract_class_and_rooms(data)
                send_notifications(classes, ntfy_key, person)

        statsd.incr("success")
    except Exception as err:
        statsd.incr("failure")
        raise err


if __name__ == "__main__":
    main()
