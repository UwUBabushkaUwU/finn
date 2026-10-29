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
        # 1. /c/DIXON (whole page, dark mode)
        print("Navigating to /c/DIXON...")
        driver.get("http://localhost:3000/c/DIXON")
        time.sleep(2)

        # Force dark mode
        driver.execute_script("document.documentElement.classList.add('dark'); document.documentElement.classList.remove('light');")
        time.sleep(0.5)

        # Get total scroll height for whole page screenshot
        total_height = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")
        print(f"DIXON scroll height: {total_height}")
        driver.set_window_size(375, total_height + 50)
        time.sleep(1)

        dixon_whole_path = os.path.abspath("docs/screenshots/dixon_dark_whole.png")
        driver.save_screenshot(dixon_whole_path)
        print(f"Saved: {dixon_whole_path}")

        # 2. Expanded promise T12 in /c/DIXON (375 px)
        # Reset window size to standard phone height
        driver.set_window_size(375, 812)
        driver.get("http://localhost:3000/c/DIXON#T12")
        time.sleep(2)
        driver.execute_script("document.documentElement.classList.add('dark'); document.documentElement.classList.remove('light');")

        # Ensure T12 is expanded
        t12_el = driver.find_element(By.ID, "T12")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", t12_el)
        time.sleep(0.5)

        # If not expanded, click it
        is_expanded = driver.execute_script("return arguments[0].querySelector('blockquote') !== null;", t12_el)
        if not is_expanded:
            t12_el.click()
            time.sleep(0.5)

        dixon_t12_path = os.path.abspath("docs/screenshots/dixon_t12_expanded.png")
        driver.save_screenshot(dixon_t12_path)
        print(f"Saved: {dixon_t12_path}")

        # 3. /c/BAJFINANCE (light mode)
        print("Navigating to /c/BAJFINANCE...")
        driver.get("http://localhost:3000/c/BAJFINANCE")
        time.sleep(2)

        # Force light mode
        driver.execute_script("document.documentElement.classList.remove('dark'); document.documentElement.classList.add('light');")
        time.sleep(0.5)

        baj_height = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")
        print(f"BAJFINANCE scroll height: {baj_height}")
        driver.set_window_size(375, baj_height + 50)
        time.sleep(1)

        baj_path = os.path.abspath("docs/screenshots/bajfinance_light.png")
        driver.save_screenshot(baj_path)
        print(f"Saved: {baj_path}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
