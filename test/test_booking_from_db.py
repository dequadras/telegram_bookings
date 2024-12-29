import asyncio
import sqlite3
from datetime import datetime, timedelta
import pytest
from src.booking import handle_many_bookings

DAYS_FROM_NOW=2

pytestmark = pytest.mark.asyncio(scope="function")

def mock_get_todays_bookings(test=False):
    print("Inside mock_get_todays_bookings")
    date = (datetime.now() + timedelta(days=DAYS_FROM_NOW)).strftime("%Y-%m-%d")
    print(f"Date: {date}")
    # Connect to the database
    conn = sqlite3.connect("bookings.db")
    cursor = conn.cursor()

    # Get all pending bookings for tomorrow
    cursor.execute(
        """
        SELECT b.id, b.telegram_id, b.booking_time, u.username, u.password, b.sport, b.player_nifs
        FROM bookings b
        JOIN users u ON b.telegram_id = u.telegram_id
        WHERE b.booking_date = ? AND b.status = 'pending'
        """,
        (date,),
    )

    bookings = cursor.fetchall()
    print(f"Found {len(bookings)} bookings")
    conn.close()
    return bookings

@pytest.mark.asyncio
async def test_handle_many_bookings(monkeypatch):
    print("\n=== Starting test_handle_many_bookings ===")
    # Patch get_todays_bookings with our mock function
    monkeypatch.setattr('src.booking.get_todays_bookings', mock_get_todays_bookings)
    
    # Run handle_many_bookings in test mode
    await handle_many_bookings(test=True)
    print("=== Finished test_handle_many_bookings ===")

