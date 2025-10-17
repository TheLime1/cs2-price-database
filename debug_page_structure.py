"""
Debug script to examine AWP Asiimov HTML structure
"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time


def debug_page():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=chrome_options)

    try:
        url = "https://csgoskins.gg/items/awp-asiimov"
        print(f"Loading: {url}")
        driver.get(url)

        # Wait for wear range section
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.XPATH, "//h2[contains(text(), 'Wear Range')]"))
        )

        time.sleep(2)  # Let everything load

        # Find the wear range section
        wear_section = driver.find_element(
            By.XPATH, "//h2[contains(text(), 'Wear Range')]/..")

        print("\n" + "="*80)
        print("WEAR RANGE SECTION HTML")
        print("="*80)
        html = wear_section.get_attribute('innerHTML')
        if html:
            print(html[:5000])  # First 5000 chars

        print("\n" + "="*80)
        print("SEARCHING FOR 'NOT POSSIBLE' TEXT")
        print("="*80)

        # Find all elements containing "Not possible"
        not_possible_elements = driver.find_elements(
            By.XPATH, "//*[contains(text(), 'Not possible')]")
        print(
            f"\nFound {len(not_possible_elements)} elements with 'Not possible' text")

        for i, elem in enumerate(not_possible_elements[:10]):  # First 10
            print(f"\n--- Element {i+1} ---")
            print(f"Tag: {elem.tag_name}")
            print(f"Text: {elem.text}")
            parent_html = elem.find_element(
                By.XPATH, './..').get_attribute('outerHTML')
            if parent_html:
                print(f"Parent HTML: {parent_html[:500]}")

        print("\n" + "="*80)
        print("CONDITION SPANS")
        print("="*80)

        condition_spans = driver.find_elements(By.XPATH,
                                               "//span[@class='whitespace-nowrap' and (contains(text(), 'Factory New') or contains(text(), 'Minimal Wear'))]")

        for span in condition_spans[:4]:  # First 4
            print(f"\n--- Condition: {span.text} ---")
            parent = span.find_element(By.XPATH, "./..")
            grandparent = parent.find_element(By.XPATH, "./..")
            print(f"Parent tag: {parent.tag_name}, text: {parent.text[:100]}")
            gp_html = grandparent.get_attribute('outerHTML')
            if gp_html:
                print(f"Grandparent HTML: {gp_html[:500]}")

    finally:
        driver.quit()


if __name__ == "__main__":
    debug_page()
