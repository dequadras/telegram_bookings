import asyncio
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta

import cv2
import numpy as np
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# todo manage multiple bookings at once
# todo check that I can book in the most wanted spots (eg do my own telegram bookings)
# todo retry booking if it fails
# todo payments should be handled on a token basis (not subscription)

# Add at the top of the file, after imports
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S")


async def handle_many_bookings(test=False):
    """
    Handle all pending bookings for tomorrow. Executed at 7am each day.
    Processes multiple bookings concurrently using asyncio.
    """
    bookings = get_todays_bookings(test=test)
    logging.info(f"Processing {len(bookings)} bookings: {bookings}")
    # Create tasks for each booking
    tasks = []
    for booking_id, telegram_id, booking_time, username, password, sport, player_nifs in bookings:
        # Create task for each booking
        player_nifs = json.loads(player_nifs)
        task = asyncio.create_task(
            process_booking(
                booking_id=booking_id,
                telegram_id=telegram_id,
                booking_time=booking_time,
                username=username,
                password=password,
                sport=sport,
                player_nifs=player_nifs,
                test=test,
            )
        )
        tasks.append(task)
    # Wait for all bookings to complete
    if tasks:
        await asyncio.gather(*tasks)


def get_todays_bookings(test=False):
    if not test:
        # Connect to the database
        conn = sqlite3.connect("bookings.db")
        cursor = conn.cursor()

        # Get tomorrow's date in YYYY-MM-DD format
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Get all pending bookings for tomorrow
        cursor.execute(
            """
            SELECT b.id, b.telegram_id, b.booking_time, u.username, u.password, b.sport, b.player_nifs
        FROM bookings b
        JOIN users u ON b.telegram_id = u.telegram_id
            WHERE b.booking_date = ? AND b.status = 'pending'
        """,
            (tomorrow,),
        )

        bookings = cursor.fetchall()
        conn.close()
    else:
        bookings = [
            # booking_id, telegram_id, booking_time, username, password,, sport, player_nifs
            (1, "123456", "10:00", "46151293E", "Luis1992", "tenis", '["60105994W"]'),
            (2, "789012", "11:00", "46152627E", "Lucas1994", "tenis", '["60432112A"]'),
        ]
    return bookings


async def process_booking(booking_id, telegram_id, booking_time, username, password, sport, player_nifs, test=False):
    """Process a single booking asynchronously."""
    logging.info(f"Starting booking process - ID: {booking_id}, User: {username}, Time: {booking_time}")
    try:
        # Convert the synchronous make_booking function to run in a separate thread
        await asyncio.to_thread(
            make_booking,
            booking_id=booking_id,
            sport=sport,
            day="Mañana",
            hour=booking_time,
            credentials={"username": username, "password": password},
            player_nifs=player_nifs,
            record=True,
            test=test,
        )

        if not test:
            logging.info(f"Updating booking status to completed - ID: {booking_id}")
            # Update booking status in database
            conn = sqlite3.connect("bookings.db")
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bookings
                SET status = ?, executed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                ("completed", booking_id),
            )
            conn.commit()
            conn.close()

        logging.info(f"Booking completed successfully - ID: {booking_id}, User: {username}, Time: {booking_time}")

    except Exception as e:
        logging.error(f"Booking failed - ID: {booking_id}, User: {username}, Error: {str(e)}")
        if not test:
            logging.info(f"Updating booking status to failed - ID: {booking_id}")
            # Update booking status to failed
            conn = sqlite3.connect("bookings.db")
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE bookings
                SET status = ?, executed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                ("failed", booking_id),
            )
            conn.commit()
            conn.close()

        print(f"Booking failed for user {username}: {str(e)}")


def make_booking(booking_id, sport, day, hour, credentials, player_nifs, record=True, test=True):
    """
    Make a booking at RC Polo.

    Args:
        booking_id (int): Booking ID
        sport (str): Sport to book
        day (str): Day to book ('Hoy' or 'Mañana')
        hour (str): Hour slot to book (format: 'HH:MM')
        credentials (dict): Dictionary with 'username' and 'password'
        player_nifs (list): List of player NIFs as strings
        record (bool): Whether to record the booking process
        test (bool): If True, don't submit the final booking
    """
    assert sport in ["padel", "tenis"]
    assert len(player_nifs) == 3 if sport == "padel" else 1
    chrome_options = Options()
    if record:
        chrome_options.add_argument("--headless=new")  # Use new headless mode
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")
    # Add these options for running in Linux VM
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    # Update the driver initialization
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    if record:
        # Set up video recording
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{booking_id}"
        output_path = f"booking_recording_{timestamp}.mp4"
        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_path, fourcc, 20.0, (1920, 1080))

    try:
        logging.info(f"Starting make_booking - ID: {booking_id}, Sport: {sport}, Day: {day}, Hour: {hour}")
        wait = WebDriverWait(driver, 10)

        if record:
            # Start a separate thread for continuous frame capture
            stop_recording = False

            def record_continuously():
                while not stop_recording:
                    try:
                        screenshot = driver.get_screenshot_as_png()
                        nparr = np.frombuffer(screenshot, np.uint8)
                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        img = cv2.resize(img, (1920, 1080))
                        out.write(img)
                        time.sleep(0.05)  # 20 FPS
                    except:
                        pass  # Ignore any screenshot errors

            # Start recording thread
            import threading

            recording_thread = threading.Thread(target=record_continuously)
            recording_thread.start()

        # Remove individual capture_frame() calls as we're now recording continuously

        logging.info("Navigating to RC Polo website")
        driver.get("https://rcpolo.com/")

        logging.info("Handling cookie consent")
        # Click accept all cookies button
        cookie_button = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
        cookie_button.click()

        logging.info("Logging in to RC Polo")
        # Click acceso socio
        login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.acceso-socios")))
        login_button.click()

        # Login
        username_field = wait.until(EC.presence_of_element_located((By.ID, "txtUsername")))
        password_field = driver.find_element(By.ID, "txtPassword")

        username_field.send_keys(credentials["username"])
        password_field.send_keys(credentials["password"])

        submit_button = driver.find_element(By.ID, "btnLogin")
        submit_button.click()

        # Navigate to booking page
        driver.get("https://rcpolo.com/areasocios/es/ov")

        logging.info(f"Selecting booking day: {day}")
        # Select day in dropdown
        day_dropdown = Select(wait.until(EC.presence_of_element_located((By.ID, "lstDate"))))
        day_dropdown.select_by_value("1" if day == "Mañana" else "0")

        logging.info(f"Selecting booking hour: {hour}")
        # Select hour
        if sport == "padel":
            hour_element = wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        f"//div[contains(@class, 'hour') and .//div[contains(@class, 'time') and text()='{hour}']]",
                    )
                )
            )
            hour_element.click()
        elif sport == "tenis":
            # Find tenis hour slot that matches the requested time
            hour_element = wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//div[contains(@class, 'category') and text()='Tenis']"
                        "/following-sibling::div[contains(@class, 'hour') "
                        f"and contains(@data-original-title, '{hour} - ')]",
                    )
                )
            )
            hour_element.click()
        # todo check there is availability
        # todo if not avialabl, select closest hour that is less than 30 mins away

        # Add this debug code before trying to interact with nif1_field
        # print("Current URL:", driver.current_url)

        # # Check if element exists
        # elements = driver.find_elements(By.ID, "txtNIF1")
        # print("Number of elements found:", len(elements))

        # # Check element properties
        # if elements:
        #     print("Element displayed:", elements[0].is_displayed())
        #     print("Element enabled:", elements[0].is_enabled())

        #     # Get element location and size
        #     location = elements[0].location
        #     size = elements[0].size
        #     print("Element location:", location)
        #     print("Element size:", size)

        if sport == "padel":
            # Input first NIF and press tab
            nif1_field = wait.until(EC.presence_of_element_located((By.ID, "txtNIF1")))
            nif1_field.click()
            nif1_field.send_keys(player_nifs[0])
            nif1_field.send_keys(Keys.TAB)
            time.sleep(2)
            # Wait for and get the name that appears after NIF validation
            name1_field = wait.until(EC.presence_of_element_located((By.ID, "txtName1")))
            name1 = name1_field.get_attribute("value")
            print(f"First player name: {name1}")

            # Input second player NIF
            nif2_field = wait.until(EC.presence_of_element_located((By.ID, "txtNIF2")))
            nif2_field.send_keys(player_nifs[1])
            nif2_field.send_keys(Keys.TAB)
            time.sleep(2)
            # Get second player name
            name2_field = wait.until(EC.presence_of_element_located((By.ID, "txtName2")))
            name2 = name2_field.get_attribute("value")
            print(f"Second player name: {name2}")

            # Input third player NIF
            nif3_field = wait.until(EC.presence_of_element_located((By.ID, "txtNIF3")))
            nif3_field.send_keys(player_nifs[2])
            nif3_field.send_keys(Keys.TAB)
            time.sleep(2)
            # Get third player name
            name3_field = wait.until(EC.presence_of_element_located((By.ID, "txtName3")))
            name3 = name3_field.get_attribute("value")
            print(f"Third player name: {name3}")
        elif sport == "tenis":
            nif1_field = wait.until(EC.presence_of_element_located((By.ID, "txtNIF")))
            nif1_field.click()
            nif1_field.send_keys(player_nifs[0])
            nif1_field.send_keys(Keys.TAB)
            time.sleep(2)
            # Wait for and get the name that appears after NIF validation
            name1_field = wait.until(EC.presence_of_element_located((By.ID, "txtName")))
            name1 = name1_field.get_attribute("value")
            print(f"First player name: {name1}")
        # Accept conditions
        conditions_checkbox = wait.until(EC.element_to_be_clickable((By.ID, "chkAccept")))
        conditions_checkbox.click()

        reserve_button = driver.find_element(By.XPATH, "//button[@id='btnSubmit' and contains(text(), 'Reservar')]")
        if not test:
            reserve_button.click()
            # Wait a bit to ensure the booking is completed
            time.sleep(2)

        if sport == "padel":
            return {
                "success": True,
                "players": [
                    {"name": name1, "nif": player_nifs[0]},
                    {"name": name2, "nif": player_nifs[1]},
                    {"name": name3, "nif": player_nifs[2]},
                ],
            }
        elif sport == "tenis":
            return {"success": True, "players": [{"name": name1, "nif": player_nifs[0]}]}

        logging.info(f"Booking process completed successfully - ID: {booking_id}")

    except Exception as e:
        logging.error(f"Error during booking process - ID: {booking_id}, Error: {str(e)}")
        raise e
    finally:
        if record:
            logging.info("Finalizing recording")
        logging.info("Closing Chrome driver")
        driver.quit()


def check_credentials(credentials):
    driver = webdriver.Chrome()

    try:
        wait = WebDriverWait(driver, 10)

        # Open website
        driver.get("https://rcpolo.com/")

        # Click accept all cookies button
        cookie_button = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
        cookie_button.click()

        # Click acceso socio
        login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.acceso-socios")))
        login_button.click()

        # Login
        username_field = wait.until(EC.presence_of_element_located((By.ID, "txtUsername")))
        password_field = driver.find_element(By.ID, "txtPassword")

        username_field.send_keys(credentials["username"])
        password_field.send_keys(credentials["password"])

        submit_button = driver.find_element(By.ID, "btnLogin")
        submit_button.click()

        return True
    except:
        return False


# Example usage:
credentials = {"username": "46151293E", "password": "luis1992"}

player_nifs = ["60105994W", "60432112A", "46152627E"]  # Add actual NIFs

if __name__ == "__main__":
    # asyncio.run(start_scheduler())
    res = asyncio.run(handle_many_bookings(test=True))

    # make_booking(
    #     sport='padel',
    #     day='Mañana',
    #     hour='10:00',
    #     credentials=credentials,
    #     player_nifs=player_nifs,
    #     test=True
    # )
    # make_booking(
    #     sport='tenis',
    #     day='Mañana',
    #     hour='10:00',
    #     credentials=credentials,
    #     player_nifs=player_nifs[:1]
    # )
