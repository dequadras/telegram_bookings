import asyncio
import json
import logging
import random
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
from database import DatabaseManager

# todo check that I can book in the most wanted spots (eg do my own telegram bookings)
# todo (later)retry booking if it fails
# Add at the top of the file, after imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Create a separate logger for booking-related logs
booking_logger = logging.getLogger("booking")
booking_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - [Booking %(booking_id)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
handler = logging.StreamHandler()
handler.setFormatter(booking_formatter)
booking_logger.addHandler(handler)
booking_logger.propagate = False  # Prevent duplicate logging

CHROMEDRIVER_PATH = "/root/.wdm/drivers/chromedriver/linux64/131.0.6778.204/chromedriver-linux64/chromedriver"

DB = DatabaseManager()


# Add this connection manager function
@contextmanager
def get_db_connection():
    conn = sqlite3.connect("bookings.db")
    try:
        yield conn
    finally:
        conn.close()


async def handle_many_bookings(test=False, is_premium=False):
    """
    Handle all pending bookings for tomorrow. Executed at 7am each day.
    Processes multiple bookings concurrently using asyncio.

    Args:
        test (bool): Whether this is a test run
        is_premium (bool): Whether to process premium or free bookings
    """
    bookings = get_todays_bookings(test=test, is_premium=is_premium)
    logging.info(f"Processing {len(bookings)} {'premium' if is_premium else 'free'} bookings: {bookings}")
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


def get_todays_bookings(test=False, is_premium=False):
    if not test:
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT b.id, b.telegram_id, b.booking_time, u.username, u.password, b.sport, b.player_nifs
                FROM bookings b
                JOIN users u ON b.telegram_id = u.telegram_id
                WHERE b.booking_date = ?
                AND b.status = 'pending'
                AND b.is_premium = ?
                """,
                (tomorrow, is_premium),
            )
            bookings = cursor.fetchall()
        logging.info(f"Query returned {len(bookings)} results: {bookings}")
        return bookings
    else:
        # For testing, you might want to add is_premium to your test data
        bookings = [
            # booking_id, telegram_id, booking_time, username, password, sport, player_nifs
            (1, "123456", "10:00", "46151293E", "Luis1992", "tenis", '["60105994W"]'),
            (2, "789012", "09:00", "46152627E", "Lucas1994", "tenis", '["60432112A"]'),
        ]
    return bookings


class BookingLogger:
    def __init__(self):
        self.db = DatabaseManager()

    async def log_conversation(self, telegram_id: int, message_type: str, message_text: str):
        """Log a conversation message"""
        query = """
        INSERT INTO conversation_logs (telegram_id, message_type, message_text)
        VALUES (?, ?, ?);
        """
        self.db.execute_query(query, (telegram_id, message_type, message_text))


# Rename the global instance of BookingLogger to avoid conflict
conversation_logger = BookingLogger()


async def process_booking(booking_id, telegram_id, booking_time, username, password, sport, player_nifs, test=False):
    """Process a single booking asynchronously."""
    # Add booking_id to logger's extra info
    logger = logging.LoggerAdapter(booking_logger, {"booking_id": booking_id})
    logger.info(f"Starting booking process - User: {username}, Time: {booking_time}")
    bot = Bot(token=CONFIG["bot"].TOKEN)
    admin_id = 249843154

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
            logger=logger,
        )

        if not test and telegram_id > 50:
            logger.info("Updating booking status to completed")
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

            # Log bot's response before sending
            await conversation_logger.log_conversation(telegram_id, "bot_response", success_message)
            await bot.send_message(chat_id=telegram_id, text=success_message)

        logger.info(f"Booking completed successfully - User: {username}, Time: {booking_time}")

    except Exception as e:
        error_message = (
            f"❌ Error al procesar tu reserva de {sport} para las {booking_time}\n\n"
            f"Es posible que no haya pistas disponibles a esa hora"
        )

        # Send detailed error notification to admin
        admin_error_message = (
            f"🚨 *Booking Failed*\n\n"
            f"Booking ID: `{booking_id}`\n"
            f"User: `{username}`\n"
            f"Sport: {sport}\n"
            f"Time: {booking_time}\n"
            f"Error: `{str(e)}`"
        )

        logger.error(f"Booking failed - User: {username}, Error: {str(e)}", exc_info=True)
        if not test and telegram_id > 50:
            # Log error messages before sending
            await conversation_logger.log_conversation(telegram_id, "bot_response", error_message)
            await bot.send_message(chat_id=telegram_id, text=error_message)

            await conversation_logger.log_conversation(admin_id, "bot_response", admin_error_message)
            await bot.send_message(chat_id=admin_id, text=admin_error_message, parse_mode="Markdown")
            logger.info(f"Updating booking status to failed - ID: {booking_id}")
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

        logger.info(f"Booking failed for user {username}: {str(e)}")


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


def make_booking(booking_id, sport, day, hour, credentials, player_nifs, record=True, test=True, logger=None):
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
        logger (Logger): Logger instance
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
        logger.info(f"Starting make_booking - Sport: {sport}, Day: {day}, Hour: {hour}")
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

                        # Add timestamp to frame
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        # Get text size and position it in center top
                        font = cv2.FONT_HERSHEY_SIMPLEX
                        font_scale = 1
                        thickness = 2
                        text_size = cv2.getTextSize(timestamp, font, font_scale, thickness)[0]
                        text_x = (img.shape[1] - text_size[0]) // 2
                        text_y = text_size[1] + 20  # 20 pixels padding from top

                        # Draw black background for better readability
                        cv2.rectangle(img, (text_x - 10, 0), (text_x + text_size[0] + 10, text_y + 10), (0, 0, 0), -1)

                        # Draw white text
                        cv2.putText(img, timestamp, (text_x, text_y), font, font_scale, (255, 255, 255), thickness)

                        out.write(img)
                        time.sleep(0.05)  # 20 FPS
                    except Exception as e:
                        logger.debug(f"Screenshot capture failed: {str(e)}")
                        continue

            # Start recording thread
            import threading

            recording_thread = threading.Thread(target=record_continuously)
            recording_thread.start()

        # Remove individual capture_frame() calls as we're now recording continuously

        logger.info("Navigating to RC Polo website")
        driver.get("https://rcpolo.com/")
        time.sleep(3)
        # Take a screenshot after loading the website
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"polo_website_{booking_id}_{timestamp}.png"
        driver.save_screenshot(screenshot_path)
        logger.info(f"Saved website screenshot to {screenshot_path}")

        logger.info("Handling cookie consent")
        # Click accept all cookies button
        cookie_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        )
        cookie_button.click()

        logger.info("Logging in to RC Polo")
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

        logger.info(f"Selecting booking day: {day}")
        # Select day in dropdown
        time.sleep(3)
        day_dropdown = Select(wait.until(EC.presence_of_element_located((By.ID, "lstDate"))))
        day_dropdown.select_by_value("1" if day == "Mañana" else "0")
        time.sleep(3)

        logger.info(f"Selecting booking hour: {hour}")
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
        if day == "Mañana":
            wait_until_7am(logger)
        hour_element.click()  # todo output error saying time is not available
        # todo check there is availability

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
            logger.info(f"First player name: {name1}")

            # Input second player NIF
            nif2_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtNIF2")))
            nif2_field.send_keys(player_nifs[1])
            nif2_field.send_keys(Keys.TAB)
            time.sleep(2)
            # Get second player name
            name2_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtName2")))
            name2 = name2_field.get_attribute("value")
            logger.info(f"Second player name: {name2}")

            # Input third player NIF
            nif3_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtNIF3")))
            nif3_field.send_keys(player_nifs[2])
            nif3_field.send_keys(Keys.TAB)
            time.sleep(2)
            # Get third player name
            name3_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtName3")))
            name3 = name3_field.get_attribute("value")
            logger.info(f"Third player name: {name3}")

            # After getting each player's name
            for nif, name in [(player_nifs[0], name1), (player_nifs[1], name2), (player_nifs[2], name3)]:
                DB.add_player(nif=nif, name=name)
        elif sport == "tenis":
            nif1_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtNIF")))
            nif1_field.click()
            nif1_field.send_keys(player_nifs[0])
            nif1_field.send_keys(Keys.TAB)
            time.sleep(2)
            # Wait for and get the name that appears after NIF validation
            name1_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "txtName")))
            name1 = name1_field.get_attribute("value")
            logger.info(f"First player name: {name1}")

            # After getting player's name
            DB.add_player(nif=player_nifs[0], name=name1)
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

        logger.info(f"Booking process completed successfully - ID: {booking_id}")

    except Exception as e:
        logger.error(f"Error during booking process - ID: {booking_id}, Error: {str(e)}", exc_info=True)
        raise e
    finally:
        if record:
            logger.info("Finalizing recording")
            # Stop the recording thread
            stop_recording = True
            recording_thread.join(timeout=2)  # Wait up to 2 seconds for thread to finish
            out.release()  # Release the video writer

        logger.info("Closing Chrome driver")
        driver.quit()

        # Cleanup the temporary profile
        import shutil

        try:
            shutil.rmtree(f"/tmp/chrome-profile-{booking_id}")
        except OSError as e:
            logger.warning(f"Failed to remove Chrome profile directory: {e}")


def wait_until_7am(logger=None):
    # Wait until exactly 7:00:00 before selecting "Mañana"
    current_time = datetime.now(ZoneInfo("Europe/Madrid")).time()
    target_time = datetime.strptime("07:00:00", "%H:%M:%S").replace(tzinfo=ZoneInfo("Europe/Madrid")).time()

    if current_time < target_time:
        wait_seconds = (
            datetime.combine(datetime.today(), target_time) - datetime.combine(datetime.today(), current_time)
        ).total_seconds()
        logger.info(f"Waiting {wait_seconds:.2f} seconds until 7:00:00")
        time.sleep(wait_seconds)


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
    # test_check_credentials_invalid()
    logging.info("done")
