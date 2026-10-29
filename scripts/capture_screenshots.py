import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

def main():
    os.makedirs("docs/screenshots", exist_ok=True)

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=375,812")

    driver = webdriver.Chrome(options=opts)
    driver.set_window_size(375, 812)

    try:
        # Load DIXON in dark mode
        print("Navigating to /c/DIXON...")
        driver.get("http://localhost:3000/c/DIXON")
        time.sleep(2)
        driver.execute_script("document.documentElement.classList.add('dark'); document.documentElement.classList.remove('light');")
        time.sleep(0.5)

        # 1. DIXON Promise List
        print("Capturing DIXON Promise List...")
        promise_section = driver.find_element(By.CSS_SELECTOR, "section[aria-labelledby='promise-list-heading']")
        driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", promise_section)
        time.sleep(0.5)
        promise_path = os.path.abspath("docs/screenshots/dixon_promise_list.png")
        promise_section.screenshot(promise_path)
        print(f"Saved: {promise_path}")

        # 2. DIXON Numbers Section
        print("Capturing DIXON Numbers Section...")
        numbers_section = driver.find_element(By.CSS_SELECTOR, "section[aria-labelledby='numbers-heading']")
        driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", numbers_section)
        time.sleep(0.5)
        numbers_path = os.path.abspath("docs/screenshots/dixon_numbers.png")
        numbers_section.screenshot(numbers_path)
        print(f"Saved: {numbers_path}")

        # 3. DIXON Bull vs Bear Section
        print("Capturing DIXON Bull vs Bear Section...")
        bull_bear_section = driver.find_element(By.CSS_SELECTOR, "section[aria-labelledby='bull-bear-heading']")
        driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", bull_bear_section)
        time.sleep(0.5)
        bull_bear_path = os.path.abspath("docs/screenshots/dixon_bull_bear.png")
        bull_bear_section.screenshot(bull_bear_path)
        print(f"Saved: {bull_bear_path}")

        # Also update whole page screenshots
        total_height = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")
        driver.set_window_size(375, total_height + 50)
        time.sleep(0.5)
        dixon_whole_path = os.path.abspath("docs/screenshots/dixon_dark_whole.png")
        driver.save_screenshot(dixon_whole_path)
        print(f"Saved: {dixon_whole_path}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
