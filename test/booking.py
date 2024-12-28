import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.booking import handle_many_bookings, process_booking


@pytest.fixture
def mock_bookings():
    """Mock booking data that would normally come from the database"""
    return [
        # booking_id, telegram_id, booking_time, username, password,, sport, player_nifs
        (1, "123456", "10:00", "46151293E", "Luis1992", "tenis", "60105994W"),
        (2, "789012", "11:00", "46152627E", "Lucas1994", "tenis", "60432112A"),
    ]


@pytest.mark.asyncio
async def test_handle_many_bookings(mock_bookings):
    # Mock the database connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = mock_bookings
    mock_conn.cursor.return_value = mock_cursor

    # Mock the process_booking function
    async def mock_process_booking(*args, **kwargs):
        return True

    with patch("sqlite3.connect", return_value=mock_conn), patch(
        "src.booking.process_booking", side_effect=mock_process_booking
    ):
        await handle_many_bookings()

        # Verify that process_booking was called for each booking
        assert mock_cursor.execute.call_count == 1
        assert mock_conn.close.call_count == 1
