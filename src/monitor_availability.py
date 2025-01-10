import logging
import time
from datetime import datetime
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

# Setup logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S")

# Credentials
CREDENTIALS = {"username": "46151293E", "password": "Luis1992"}

# Add this constant at the top with other constants
CHROMEDRIVER_PATH = "/root/.wdm/drivers/chromedriver/linux64/131.0.6778.204/chromedriver-linux64/chromedriver"


def setup_driver():
    """Setup and return Chrome driver with basic options"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--start-maximized")

    # Add these important stability options
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-logging")

    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def login_and_navigate(driver):
    """Login to RC Polo and navigate to reservations page"""
    wait = WebDriverWait(driver, 10)

    # Open website
    driver.get("https://rcpolo.com/")

    # Accept cookies
    cookie_button = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
    cookie_button.click()

    # Click acceso socio
    login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.acceso-socios")))
    login_button.click()

    # Login
    username_field = wait.until(EC.presence_of_element_located((By.ID, "txtUsername")))
    password_field = driver.find_element(By.ID, "txtPassword")

    username_field.send_keys(CREDENTIALS["username"])
    password_field.send_keys(CREDENTIALS["password"])

    submit_button = driver.find_element(By.ID, "btnLogin")
    submit_button.click()

    # Navigate to booking page
    driver.get("https://rcpolo.com/areasocios/es/ov")


def select_tomorrow(driver):
    """Select 'Mañana' in the dropdown"""
    wait = WebDriverWait(driver, 10)
    day_dropdown = Select(wait.until(EC.presence_of_element_located((By.ID, "lstDate"))))
    day_dropdown.select_by_value("1")  # 1 for "Mañana"
    time.sleep(1)  # Small delay to let the page update


def extract_availability(availability_element) -> Dict[str, List[Tuple[str, int]]]:
    """
    Extract availability information for tennis and padel courts.

    Args:
        availability_element: Selenium WebElement containing the availability information

    Returns:
        Dictionary with sport types as keys and lists of (time, available_courts) tuples as values
    """
    # Get the HTML content
    html_content = availability_element.get_attribute("innerHTML")
    soup = BeautifulSoup(html_content, "html.parser")

    # Initialize result dictionary
    availability = {"Padel": [], "Tenis": []}

    # Process each sport category
    for category_div in soup.find_all("div", recursive=False):
        category_name = category_div.find(class_="category")
        if not category_name:
            continue

        sport = category_name.text
        if sport not in availability:
            continue

        # Find all hour slots
        for hour_div in category_div.find_all(class_="hour"):
            # Skip slots marked as closed/unavailable
            if "closed" in hour_div.get("class", []):
                continue

            # Extract time - handle both Padel and Tenis cases
            time_div = hour_div.find(class_="time")
            if time_div:
                time = time_div.text
            else:
                # For tennis, extract time from the title attribute
                title = hour_div.get("data-original-title", "")
                if title:
                    # Extract time from format like "<div>Tenis</div><div>09:00 - 10:00</div>..."
                    time_match = title.split("</div><div>")[1].split(" - ")[0]
                    time = time_match
                else:
                    continue

            # Extract available courts
            places_span = hour_div.find(class_="places")
            if places_span:
                try:
                    available = int(places_span.text)
                except ValueError:
                    continue

                availability[sport].append((time, available))

    return availability


def get_availability_info(driver):
    """Get availability information from the specified element"""
    wait = WebDriverWait(driver, 10)
    availability_element = wait.until(
        EC.presence_of_element_located((By.XPATH, "//div[@class='book-calendar']//div[@class='body']"))
    )

    # Extract and format availability information
    availability = extract_availability(availability_element)

    # Log the formatted information
    for sport, times in availability.items():
        logging.info(f"\n{sport} Availability:")
        for time_, courts in times:
            logging.info(f"  {time_}: {courts} courts available")

    return availability_element


def monitor_availability():
    """Main function to monitor availability"""
    driver = setup_driver()
    try:
        login_and_navigate(driver)

        for iteration in range(1):  # 180 iterations = 1 hour with 20-second intervals
            current_time = datetime.now().strftime("%H:%M:%S")
            logging.info(f"\nIteration {iteration + 1}/180 at {current_time}")

            select_tomorrow(driver)
            availability_info = get_availability_info(driver)

            logging.info(f"Availability Information:\n{availability_info}\n")

            if iteration < 179:  # Don't wait on the last iteration
                time.sleep(20)
                driver.refresh()

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        raise
    finally:
        driver.quit()


if __name__ == "__main__":
    monitor_availability()
