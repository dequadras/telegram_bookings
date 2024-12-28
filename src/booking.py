from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
import time
import os
from datetime import datetime, timedelta
import asyncio
import sqlite3
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# todo manage multiple bookings at once
# todo check that I can book in the most wanted spots (eg do my own telegram bookings)

async def handle_many_bookings():
    """
    Handle all pending bookings for tomorrow. Executed at 7am each day.
    Processes multiple bookings concurrently using asyncio.
    """
    # Connect to the database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Get tomorrow's date in YYYY-MM-DD format
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Get all pending bookings for tomorrow
    cursor.execute("""
        SELECT b.id, b.telegram_id, b.booking_time, u.username, u.first_name
        FROM bookings b
        JOIN users u ON b.telegram_id = u.telegram_id
        WHERE b.booking_date = ? AND b.status = 'pending'
    """, (tomorrow,))
    
    bookings = cursor.fetchall()
    conn.close()
    
    # Create tasks for each booking
    tasks = []
    for booking_id, telegram_id, booking_time, username, first_name in bookings:
        # Create task for each booking
        task = asyncio.create_task(
            process_booking(
                booking_id=booking_id,
                telegram_id=telegram_id,
                booking_time=booking_time,
                username=username,
                first_name=first_name
            )
        )
        tasks.append(task)
    
    # Wait for all bookings to complete
    if tasks:
        await asyncio.gather(*tasks)

async def process_booking(booking_id, telegram_id, booking_time, username, first_name):
    """
    Process a single booking asynchronously.
    """
    try:
        # Convert the synchronous make_booking function to run in a separate thread
        # since it uses Selenium which is not async-friendly
        result = await asyncio.to_thread(
            make_booking,
            sport='padel',  # You might want to add this to the bookings table
            day='Mañana',
            hour=booking_time,
            credentials=credentials,  # You'll need to get this from a secure source
            player_nifs=player_nifs,  # You'll need to get this from a secure source
            record=True
        )
        
        # Update booking status in database
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE bookings 
            SET status = ?, executed_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, ('completed', booking_id))
        conn.commit()
        conn.close()
        
        print(f"Booking completed for user {username} ({first_name}) at {booking_time}")
        
    except Exception as e:
        # Update booking status to failed
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE bookings 
            SET status = ?, executed_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, ('failed', booking_id))
        conn.commit()
        conn.close()
        
        print(f"Booking failed for user {username} ({first_name}): {str(e)}")

def make_booking(sport, day, hour, credentials, player_nifs, record=True):
    """
    Make a booking at RC Polo
    
    Args:
        sport (str): Sport to book
        day (str): Day to book ('Hoy' or 'Mañana')
        hour (str): Hour slot to book (format: 'HH:MM')
        credentials (dict): Dictionary with 'username' and 'password'
        player_nifs (list): List of player NIFs as strings
        record (bool): Whether to record the booking process
    """
    assert sport in ['padel', 'tennis']
    assert len(player_nifs) == 3 if sport == 'padel' else 1
    chrome_options = Options()
    if record:
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--window-size=1920,1080")  # Set window size for recording
        chrome_options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    if record:
        # Create a directory for screenshots if it doesn't exist
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        recording_dir = f"booking_recording_{timestamp}"
        os.makedirs(recording_dir, exist_ok=True)
        screenshot_count = 0

    try:
        wait = WebDriverWait(driver, 10)
        
        # Open website
        driver.get("https://rcpolo.com/")
        
        # Take screenshots at key moments
        def take_screenshot(description):
            nonlocal screenshot_count
            if record:
                screenshot_count += 1
                driver.save_screenshot(f"{recording_dir}/{screenshot_count:03d}_{description}.png")

        # Add screenshots at key moments throughout the process
        take_screenshot("initial_page")
        
        # Click accept all cookies button
        cookie_button = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
        cookie_button.click()
        take_screenshot("after_cookies")
        
        # Click acceso socio
        login_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.acceso-socios")))
        login_button.click()
        
        # Login
        username_field = wait.until(EC.presence_of_element_located((By.ID, "txtUsername")))
        password_field = driver.find_element(By.ID, "txtPassword")
        
        username_field.send_keys(credentials['username'])
        password_field.send_keys(credentials['password'])
        
        submit_button = driver.find_element(By.ID, "btnLogin")
        submit_button.click()
            
        # Navigate to booking page
        driver.get("https://rcpolo.com/areasocios/es/ov")

        # Select day in dropdown
        day_dropdown = Select(wait.until(EC.presence_of_element_located((By.ID, "lstDate"))))
        day_dropdown.select_by_value("1" if day == "Mañana" else "0")
        
        # Select hour
        if sport == 'padel':
            hour_element = wait.until(EC.element_to_be_clickable((By.XPATH, f"//div[contains(@class, 'hour') and .//div[contains(@class, 'time') and text()='{hour}']]")))
            hour_element.click()
        elif sport == 'tennis':
            # Find tennis hour slot that matches the requested time
            hour_element = wait.until(EC.element_to_be_clickable((
                By.XPATH,
                f"//div[contains(@class, 'category') and text()='Tenis']"
                f"/following-sibling::div[contains(@class, 'hour') and contains(@data-original-title, '{hour} - ')]"
            )))
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
        
        if sport == 'padel':
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
        elif sport == 'tennis':
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
        reserve_button.click()
        
        # Wait a bit to ensure the booking is completed
        time.sleep(2)
        if sport == 'padel':
            return {"success": True, "players": [
                {"name": name1, "nif": player_nifs[0]},
                {"name": name2, "nif": player_nifs[1]}, 
                {"name": name3, "nif": player_nifs[2]}
            ]}
        elif sport == 'tennis':
            return {"success": True, "players": [
                {"name": name1, "nif": player_nifs[0]}
            ]}
        
    except Exception as e:
        if record:
            take_screenshot("error_state")
        raise e
    finally:
        driver.quit()

async def start_scheduler():
    """
    Sets up and runs the scheduler to execute bookings at 7am daily
    """
    scheduler = AsyncIOScheduler()
    
    # Add the job - will run at 7am daily
    scheduler.add_job(
        handle_many_bookings,  # Note: no need for asyncio.run() here
        CronTrigger(hour=7, minute=0),
        id='daily_bookings',
        name='Process daily bookings',
        replace_existing=True
    )
    
    scheduler.start()
    
    # Keep the scheduler running
    try:
        while True:
            await asyncio.sleep(1)  # Sleep for a second between checks
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

# Example usage:
credentials = {
    'username': '46151293E',
    'password': 'luis1992'
}

player_nifs = ['60105994W', '60432112A', "46152627E"]  # Add actual NIFs

if __name__ == "__main__":
    asyncio.run(start_scheduler())

    # make_booking(
    #     sport='padel',
    #     day='Mañana',
    #     hour='10:00',
    #     credentials=credentials,
    #     player_nifs=player_nifs
    # )
    # make_booking(
    #     sport='tennis',
    #     day='Mañana',
    #     hour='10:00',
    #     credentials=credentials,
    #     player_nifs=player_nifs[:1]
    # )
