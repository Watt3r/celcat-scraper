#!/usr/bin/env python

import datetime
import os
import re
import sys

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

today = datetime.date.today() + datetime.timedelta(days=3)

ntfy_key = os.getenv("NTFY_KEY")
username = os.getenv("USERNAME")
password = os.getenv("PASSWORD")

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-dev-shm-usage")

# Specify the path to Chromium binary
chrome_options.binary_location = "/usr/bin/chromium"

driver = webdriver.Chrome(options=chrome_options)

# Go to the login page and login
driver.get("https://timetable.nulondon.ac.uk/cal?vt=month")

# Fill in username and password
driver.find_element(By.ID, "Name").send_keys(username)
driver.find_element(By.ID, "Password").send_keys(password)
driver.find_element(By.ID, "Password").send_keys(Keys.RETURN)

# Capture cookies from Selenium and use them in requests
cookies = driver.get_cookies()

s = requests.Session()
for cookie in cookies:
    s.cookies.set(cookie["name"], cookie["value"])

# Close the browser
driver.quit()

headers = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# TODO: Loop through all federationIds if others want to use this
data = {
    "start": today,
    "end": today,
    "resType": "104",
    "calView": "month",
    "federationIds[]": "02267113",
}

# Now you can use `s` to make requests with the same session as Selenium
response = s.post(
    "https://timetable.nulondon.ac.uk/Home/GetCalendarData", headers=headers, data=data
)

if response.status_code != 200:
    print("Error: Could not get calendar data")
    print(response.status_code)
    print(response.text)
    sys.exit()

data = response.json()  # Parse JSON data

class_and_rooms = []

# Regular expression to extract room details
room_regex = re.compile(r"\d+\s\[[\d\sCap]+\]")

for entry in data:
    description = entry["description"]

    # Extract the class name (first line of the description)
    class_name = description.split("_")[0]

    # Find all room numbers using regex
    rooms = room_regex.findall(description)

    # Add class name and room numbers to the list
    class_and_rooms.append({"class": class_name, "rooms": rooms})

# Print the extracted information
for item in class_and_rooms:
    requests.post(
        f"https://ntfy.sh/{ntfy_key}",
        data=f"Class: {item['class']}, Rooms: {', '.join(item['rooms'])}".encode(
            encoding="utf-8"
        ),
        timeout=10,
    )
