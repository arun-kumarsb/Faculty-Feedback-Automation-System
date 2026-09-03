
import argparse
import os
import re
import time
from dataclasses import dataclass

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    UnexpectedAlertPresentException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


# ------------------- CONFIGURATION -------------------
USER_USN = os.getenv("USER_USN", "YOUR_USN_HERE")
BIRTH_DAY = os.getenv("BIRTH_DAY", "01")
BIRTH_MONTH = os.getenv("BIRTH_MONTH", "01")
BIRTH_YEAR = os.getenv("BIRTH_YEAR", "2000")

# "highest" selects the most positive visible option. "lowest" selects the most negative.
FEEDBACK_RATING = "highest"
COMMON_FEEDBACK = "Thank you for your efforts and teaching!"

HEADLESS = False
DELAY = 1.5
FAST_RADIO_SELECTION = True

BASE_URL = "https://niefeedback.contineo.in"
LOGIN_URL = f"{BASE_URL}/"
STAFF_FEEDBACK_URL = (
    f"{BASE_URL}/index.php?option=com_feedback&controller=feedbackentry"
    "&task=feedback&Itemid=200217"
)
COURSE_END_SURVEY_URL = (
    f"{BASE_URL}/index.php?option=com_coursefeedback&controller=feedbackentry"
    "&task=feedback&Itemid=200218"
)
# -----------------------------------------------------


@dataclass
class Dashboard:
    name: str
    menu_text: str
    fallback_url: str


DASHBOARDS = [
    Dashboard("Course End Survey", "Course End Survey", COURSE_END_SURVEY_URL),
]

POSITIVE_OPTION_LABELS = [
    "strongly agree",
    "excellent",
    "very good",
    "good",
    "fully",
    "always",
    "frequently",
    "satisfactorily",
]

NEGATIVE_OPTION_LABELS = [
    "strongly disagree",
    "disagree",
    "needs improvement",
    "difficult to understand",
    "does not provide",
    "partially",
    "rarely",
    "unsatisfactorily",
]


def wait_for_element(driver, by, value, timeout=15):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )


def safe_get(driver, url, timeout=15, retries=3):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            driver.get(url)
            break
        except TimeoutException as error:
            last_error = error
            driver.execute_script("window.stop();")
            break
        except WebDriverException as error:
            last_error = error
            if "ERR_CONNECTION_TIMED_OUT" not in str(error) or attempt == retries:
                raise
            print(f"Page load timed out, retrying ({attempt}/{retries})...")
            time.sleep(DELAY)
    else:
        raise last_error

    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )


def select_dropdown_value(element, value):
    dropdown = Select(element)
    value = str(value).strip()
    candidates = {value, value.zfill(2)}

    for option in dropdown.options:
        option_value = (option.get_attribute("value") or "").strip()
        option_text = option.text.strip()
        if option_value in candidates or option_text in candidates:
            dropdown.select_by_visible_text(option.text)
            return

    raise NoSuchElementException(f"Cannot locate dropdown option matching: {value}")


def click_with_js(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(0.2)
    driver.execute_script("arguments[0].click();", element)


def select_radio(driver, radio):
    driver.execute_script(
        """
        arguments[0].checked = true;
        arguments[0].dispatchEvent(new MouseEvent('click', {
            bubbles: true,
            cancelable: true,
            view: window
        }));
        arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
        arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
        """,
        radio,
    )


def login(driver):
    if USER_USN == "YOUR_USN_HERE":
        raise ValueError(
            "Please configure USER_USN and Date of Birth in feedback_automation.py "
            "or via environment variables (USER_USN, BIRTH_DAY, BIRTH_MONTH, BIRTH_YEAR) before running."
        )

    safe_get(driver, LOGIN_URL)

    wait_for_element(driver, By.ID, "username").send_keys(USER_USN)
    select_dropdown_value(wait_for_element(driver, By.ID, "dd"), BIRTH_DAY)
    select_dropdown_value(wait_for_element(driver, By.ID, "mm"), BIRTH_MONTH)
    select_dropdown_value(wait_for_element(driver, By.ID, "yyyy"), BIRTH_YEAR)
    time.sleep(DELAY)

    login_button = wait_for_element(
        driver, By.XPATH, "//input[@type='image' and @name='submit']"
    )
    try:
        click_with_js(driver, login_button)
    except TimeoutException:
        pass

    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    if driver.find_elements(By.ID, "username"):
        raise RuntimeError("Login did not complete. Check USER_USN and DOB.")

    print("Logged in successfully.")
    time.sleep(DELAY)


def absolute_url(href):
    if not href:
        return None
    if href.startswith("/"):
        return f"{BASE_URL}{href}"
    return href


def get_menu_url(driver, link_text, fallback_url):
    links = driver.find_elements(By.PARTIAL_LINK_TEXT, link_text)
    for link in links:
        href = absolute_url(link.get_attribute("href"))
        if href:
            return href
    return fallback_url


def get_feedback_buttons(driver):
    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located(
                (By.XPATH, "//a[img[contains(@src, 'give-feedback.png')]]")
            )
        )
    except TimeoutException:
        return []

    return driver.find_elements(
        By.XPATH, "//a[img[contains(@src, 'give-feedback.png')]]"
    )


def normalized_label(text):
    return " ".join(text.lower().split())


def radio_label(radio):
    label_text = radio.get_attribute("aria-label") or ""
    radio_id = radio.get_attribute("id")

    if not label_text and radio_id:
        labels = radio.find_elements(By.XPATH, f"//label[@for='{radio_id}']")
        if labels:
            label_text = labels[0].text

    if not label_text:
        parent_text = radio.find_element(By.XPATH, "./..").text
        label_text = parent_text

    return normalized_label(label_text)


def rating_score(radio):
    value = radio.get_attribute("value") or ""
    match = re.search(r"(-?\d+(?:\.\d+)?)$", value)
    if match:
        return float(match.group(1))
    return 0.0


def find_radio_by_label(radios, preferred_labels):
    radio_labels = [(radio, radio_label(radio)) for radio in radios]
    for preferred_label in preferred_labels:
        for radio, label in radio_labels:
            if preferred_label in label:
                return radio
    return None


def choose_radio(radios):
    if FAST_RADIO_SELECTION:
        return radios[-1] if FEEDBACK_RATING.lower() == "lowest" else radios[0]

    if FEEDBACK_RATING.lower() == "lowest":
        return find_radio_by_label(radios, NEGATIVE_OPTION_LABELS) or radios[-1]
    return find_radio_by_label(radios, POSITIVE_OPTION_LABELS) or radios[0]


def get_radio_groups(driver):
    radios = driver.find_elements(
        By.XPATH,
        "//input[@type='radio' and (starts-with(@name, 'selectedchoice') or @required)]",
    )
    groups = {}
    for radio in radios:
        name = radio.get_attribute("name") or radio.get_attribute("id")
        if not name:
            continue
        groups.setdefault(name, []).append(radio)
    return list(groups.values())


def fill_feedback_form(driver):
    time.sleep(DELAY)
    selected_count = 0

    radio_groups = get_radio_groups(driver)
    print(f"Found {len(radio_groups)} question(s) on form.")

    for radios in radio_groups:
        selected_radio = choose_radio(radios)
        select_radio(driver, selected_radio)
        selected_count += 1

    if selected_count == 0:
        raise RuntimeError("No feedback radio questions found on this form.")

    for comment_box in driver.find_elements(By.XPATH, "//textarea[@name='sugg']"):
        comment_box.clear()
        comment_box.send_keys(COMMON_FEEDBACK)

    submit_buttons = driver.find_elements(
        By.XPATH, "//input[@type='submit' and normalize-space(@value)='Submit']"
    )
    if not submit_buttons:
        raise RuntimeError("Submit button not found on this form.")

    click_with_js(driver, submit_buttons[0])
    time.sleep(DELAY)

    try:
        WebDriverWait(driver, 3).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        print(f"Alert: {alert.text}")
        alert.accept()
    except TimeoutException:
        pass

    print(f"Feedback submitted ({selected_count} question(s)).")
    time.sleep(DELAY)


def process_feedback_dashboard(driver, dashboard):
    dashboard_url = get_menu_url(driver, dashboard.menu_text, dashboard.fallback_url)
    print(f"Checking {dashboard.name}...")
    safe_get(driver, dashboard_url)

    consecutive_errors = 0
    while True:
        buttons = get_feedback_buttons(driver)
        if not buttons:
            print(f"No more pending {dashboard.name}.")
            return

        print(f"{len(buttons)} {dashboard.name} item(s) pending.")
        try:
            click_with_js(driver, buttons[0])
            fill_feedback_form(driver)
            consecutive_errors = 0
        except UnexpectedAlertPresentException:
            try:
                alert = driver.switch_to.alert
                print(f"Alert: {alert.text}")
                alert.accept()
            except Exception:
                pass
        except Exception as error:
            consecutive_errors += 1
            print(f"Error during {dashboard.name}: {error}")
            if consecutive_errors >= 3:
                raise RuntimeError(
                    f"Stopped after 3 repeated errors on {dashboard.name}."
                ) from error
        finally:
            safe_get(driver, dashboard_url)
            time.sleep(DELAY)


def build_driver(headless):
    from selenium.webdriver.chrome.service import Service

    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"
    options.add_argument("--window-size=1200,900")
    if headless:
        options.add_argument("--headless=new")

    clear_webdriver_manager_lock()
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    driver.implicitly_wait(5)
    return driver


def clear_webdriver_manager_lock():
    lock_path = os.path.expanduser(r"~\.wdm\.wdm-lock-chromedriver-win64")
    if not os.path.exists(lock_path):
        return

    try:
        os.remove(lock_path)
        print("Removed stale webdriver-manager lock.")
    except OSError as error:
        print(f"Could not remove webdriver-manager lock: {error}")


def parse_args():
    parser = argparse.ArgumentParser(description="NIE feedback automation")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=HEADLESS,
        help="Run Chrome without opening a visible browser window.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    driver = build_driver(args.headless)

    try:
        login(driver)
        for dashboard in DASHBOARDS:
            process_feedback_dashboard(driver, dashboard)
    finally:
        driver.quit()
        print("Automation complete.")


if __name__ == "__main__":
    main()
