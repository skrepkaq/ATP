"""
Извиняюсь за код, писал cursor
"""

import asyncio
import random
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from TikTokApi import TikTokApi
from TikTokApi.exceptions import EmptyResponseException


def get_tiktok_ms_token():
    options = Options()
    options.add_argument("--lang=en_US")
    options.add_argument("--mute-audio")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument('--disable-infobars')
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-site-isolation-trials")
    user_agent = ("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 "
                  "Safari/537.36")
    options.add_argument(user_agent)

    print("Connecting to Selenium Grid...")
    driver = webdriver.Remote(
        command_executor="http://localhost:4444/wd/hub",
        options=options
    )
    try:
        print("Navigating to TikTok...")
        driver.get("https://www.tiktok.com")

        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        driver.get("https://www.tiktok.com")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        action = ActionChains(driver)
        sz = driver.get_window_size()
        x = random.randint(0, sz["width"])
        y = random.randint(0, sz["height"])
        action.move_by_offset(x, y).perform()
        print(f"Moved mouse to ({x}, {y})")
        time.sleep(2)

        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight/4);"
        )
        time.sleep(1)
        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight/2);"
        )
        time.sleep(1)
        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);"
        )
        time.sleep(1)

        print("Page loaded, waiting 10 more seconds...")
        time.sleep(10)

        cookies = driver.get_cookies()
        for cookie in cookies:
            if cookie['name'] == 'msToken':
                print('getfromcookie')
                return cookie['value']

        ms_token = driver.execute_script(
            "return localStorage.getItem('msToken') || ''"
        )

        if not ms_token:
            cookies = driver.get_cookies()
            for cookie in cookies:
                if cookie['name'] == 'msToken':
                    ms_token = cookie['value']
                    break

        if not ms_token:
            print("ms_token not found directly, checking all storage...")
            all_cookies = driver.get_cookies()
            local_storage_script = (
                "return Object.keys(localStorage).reduce("
                "(obj, k) => { obj[k] = localStorage.getItem(k); "
                "return obj; }, {});"
            )
            local_storage = driver.execute_script(local_storage_script)

            print("Cookies:")
            for cookie in all_cookies:
                cookie_value = (f"{cookie['value'][:30]}..."
                               if len(cookie['value']) > 30
                               else cookie['value'])
                print(f"  {cookie['name']}: {cookie_value}")
                if 'token' in cookie['name'].lower():
                    ms_token = cookie['value']
                    print(f"Potential ms_token found in cookie: "
                          f"{cookie['name']}")

            print("LocalStorage:")
            for key, value in local_storage.items():
                display_value = (
                    f"{value[:30]}..."
                    if value and len(value) > 30
                    else value
                )
                print(f"  {key}: {display_value}")
                if 'token' in key.lower() and not ms_token:
                    ms_token = value
                    print(f"Potential ms_token found in localStorage: {key}")

        return ms_token

    finally:
        driver.quit()


async def test_token(ms_token):
    async with TikTokApi() as api:
        await api.create_sessions(ms_tokens=[ms_token], num_sessions=1, sleep_after=5, browser="chromium", headless=True)
        ms_token = api._get_session()[1].ms_token

        print("Generated token:")
        print(ms_token)

        print("Checking token...")
        try:
            await api.user("therock").info()
        except EmptyResponseException as e:
            print("Token is bad(")
            print(e)
        else:
            print("Token is ok!")


if __name__ == "__main__":
    ms_token = get_tiktok_ms_token()
    if ms_token:
        print(f"\nms_token: {ms_token}")
        asyncio.run(test_token(ms_token))
    else:
        print("\nms_token not found")
