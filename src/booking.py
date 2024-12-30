import asyncio
import json
import logging
import random
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

import cv2
import numpy as np
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from telegram import Bot

from config import CONFIG

# todo not allow access with num socio
# todo check that I can book in the most wanted spots (eg do my own telegram bookings)
# todo retry booking if it fails
# todo payments should be handled on a token basis (not subscription)
# ability to cancel booking

# Add at the top of the file, after imports
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S")

CHROMEDRIVER_PATH = "/root/.wdm/drivers/chromedriver/linux64/131.0.6778.204/chromedriver-linux64/chromedriver"


# Add this connection manager function
@contextmanager
def get_db_connection():
    conn = sqlite3.connect("bookings.db")
    try:
        yield conn
    finally:
        conn.close()


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
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        with get_db_connection() as conn:
            cursor = conn.cursor()
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
        return bookings
    else:
        bookings = [
            # booking_id, telegram_id, booking_time, username, password,, sport, player_nifs
            (1, "123456", "10:00", "46151293E", "Luis1992", "tenis", '["60105994W"]'),
            (2, "789012", "09:00", "46152627E", "Lucas1994", "tenis", '["60432112A"]'),
        ]
    return bookings


async def process_booking(booking_id, telegram_id, booking_time, username, password, sport, player_nifs, test=False):
    """Process a single booking asynchronously."""
    logging.info(f"Starting booking process - ID: {booking_id}, User: {username}, Time: {booking_time}")
    bot = Bot(token=CONFIG["bot"].TOKEN)

    try:
        # Convert the synchronous make_booking function to run in a separate thread
        booking_result = await asyncio.to_thread(
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
            with get_db_connection() as conn:
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

            # Format success message with player details
            players_text = "\n".join([f"- {player['name']} ({player['nif']})" for player in booking_result["players"]])
            success_message = (
                f"✅ ¡Reserva completada con éxito!\n\n"
                f"Deporte: {sport}\n"
                f"Día: Mañana\n"
                f"Hora: {booking_time}\n\n"
                f"Jugadores:\n{players_text}"
            )

            await bot.send_message(chat_id=telegram_id, text=success_message)

        logging.info(f"Booking completed successfully - ID: {booking_id}, User: {username}, Time: {booking_time}")

    except Exception as e:
        error_message = (
            f"❌ Error al procesar tu reserva de {sport} para las {booking_time}\n\n"
            f"Error: {str(e)}\n\n"
            "Por favor, intenta de nuevo más tarde o contacta con soporte."
        )

        logging.error(f"Booking failed - ID: {booking_id}, User: {username}, Error: {str(e)}", exc_info=True)
        if not test:
            await bot.send_message(chat_id=telegram_id, text=error_message)
            logging.info(f"Updating booking status to failed - ID: {booking_id}")
            with get_db_connection() as conn:
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

        print(f"Booking failed for user {username}: {str(e)}")


def get_available_port():
    """Get a random available port between 9222 and 9999"""
    return random.randint(9222, 9999)


def get_driver(booking_id=None):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--start-maximized")

    # Basic Chrome options for stability
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")

    # Assign unique debugging port for this instance
    debug_port = get_available_port()
    chrome_options.add_argument(f"--remote-debugging-port={debug_port}")

    # Add these for better concurrent handling
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-logging")
    if booking_id:
        chrome_options.add_argument(f"--user-data-dir=/tmp/chrome-profile-{booking_id}")

    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


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

    driver = get_driver()
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
        time.sleep(3)
        # Take a screenshot after loading the website
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"polo_website_{booking_id}_{timestamp}.png"
        driver.save_screenshot(screenshot_path)
        logging.info(f"Saved website screenshot to {screenshot_path}")

        logging.info("Handling cookie consent")
        # Click accept all cookies button
        cookie_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        )
        cookie_button.click()

        logging.info("Logging in to RC Polo")
        # Click acceso socio
        login_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.acceso-socios")))
        login_button.click()

        # Login
        username_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtUsername")))
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
            hour_element = WebDriverWait(driver, 10).until(
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
            hour_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//div[contains(@class, 'category') and text()='Tenis']"
                        "/following-sibling::div[contains(@class, 'hour') "
                        f"and contains(@data-original-title, '{hour} - ')]",
                    )
                )
            )
            hour_element.click()  # todo output error saying time is not available
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
            nif1_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtNIF1")))
            nif1_field.click()
            nif1_field.send_keys(player_nifs[0])
            nif1_field.send_keys(Keys.TAB)
            time.sleep(2)
            # Wait for and get the name that appears after NIF validation
            name1_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtName1")))
            name1 = name1_field.get_attribute("value")
            print(f"First player name: {name1}")

            # Input second player NIF
            nif2_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtNIF2")))
            nif2_field.send_keys(player_nifs[1])
            nif2_field.send_keys(Keys.TAB)
            time.sleep(2)
            # Get second player name
            name2_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtName2")))
            name2 = name2_field.get_attribute("value")
            print(f"Second player name: {name2}")

            # Input third player NIF
            nif3_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtNIF3")))
            nif3_field.send_keys(player_nifs[2])
            nif3_field.send_keys(Keys.TAB)
            time.sleep(2)
            # Get third player name
            name3_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtName3")))
            name3 = name3_field.get_attribute("value")
            print(f"Third player name: {name3}")
        elif sport == "tenis":
            nif1_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtNIF")))
            nif1_field.click()
            nif1_field.send_keys(player_nifs[0])
            nif1_field.send_keys(Keys.TAB)
            time.sleep(2)
            # Wait for and get the name that appears after NIF validation
            name1_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtName")))
            name1 = name1_field.get_attribute("value")
            print(f"First player name: {name1}")
        # Accept conditions
        conditions_checkbox = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "chkAccept")))
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
        logging.error(f"Error during booking process - ID: {booking_id}, Error: {str(e)}", exc_info=True)
        raise e
    finally:
        if record:
            logging.info("Finalizing recording")
            # Stop the recording thread
            stop_recording = True
            recording_thread.join(timeout=2)  # Wait up to 2 seconds for thread to finish
            out.release()  # Release the video writer

        logging.info("Closing Chrome driver")
        driver.quit()

        # Cleanup the temporary profile
        import shutil

        try:
            shutil.rmtree(f"/tmp/chrome-profile-{booking_id}")
        except OSError as e:
            logging.warning(f"Failed to remove Chrome profile directory: {e}")


def check_credentials(credentials):
    driver = get_driver()
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

    # Check for error message indicating invalid credentials
    try:
        error_div = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".form-signin .alert.alert-danger"))
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"polo_website_{timestamp}.png"
        driver.save_screenshot(screenshot_path)
        logging.info(f"Saved website screenshot to {screenshot_path}")

        if "Usuario o password incorrecto" in error_div.text:
            return False
        else:
            return True  # todo check this
    except TimeoutException:
        # No error message found, credentials are valid
        return True


# Example usage:
credentials = {"username": "46151293E", "password": "luis1992"}

player_nifs = ["60105994W", "60432112A", "46152627E"]  # Add actual NIFs


def test_check_credentials_valid():
    credentials = {"username": "46151293E", "password": "Luis1992"}
    assert check_credentials(credentials) is True


def test_check_credentials_invalid():
    credentials = {"username": "46151293E", "password": "incorrect"}
    assert check_credentials(credentials) is False


if __name__ == "__main__":
    # asyncio.run(start_scheduler())
    # res = asyncio.run(handle_many_bookings(test=True))

    # make_booking(
    #     booking_id=1,
    #     sport='padel',
    #     day='Mañana',
    #     hour='10:00',
    #     credentials=credentials,
    #     player_nifs=player_nifs,
    #     test=True
    # )
    # make_booking(
    #     booking_id=1,
    #     sport='tenis',
    #     day='Mañana',
    #     hour='10:00',
    #     credentials=credentials,
    #     player_nifs=player_nifs[:1]
    # )
    # test_check_credentials_valid()
    test_check_credentials_invalid()
    print("done")
