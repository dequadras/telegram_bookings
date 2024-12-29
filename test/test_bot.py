import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from telegram import Update, User, Message
from telegram.ext import ContextTypes

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from src.bot import TenisBookingBot

@pytest.fixture
def bot():
    return TenisBookingBot()

@pytest.fixture
def mock_update():
    update = Mock(spec=Update)
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 123456789
    update.effective_user.username = "test_user"
    update.effective_user.first_name = "Test"
    update.effective_user.last_name = "User"
    update.message = Mock(spec=Message)
    update.callback_query = Mock()
    return update

@pytest.fixture
def context():
    context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    context.user_data = {}
    return context

@pytest.mark.asyncio
async def test_start_command(bot, mock_update, context):
    await bot.start(mock_update, context)
    
    mock_update.message.reply_text.assert_called_once()
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "¡Bienvenido/a Test!" in call_args
    assert "/book" in call_args
    assert "/mybookings" in call_args

@pytest.mark.asyncio
async def test_book_command(bot, mock_update, context):
    await bot.book(mock_update, context)
    
    mock_update.message.reply_text.assert_called_once()
    assert mock_update.message.reply_text.call_args[1]['reply_markup'] is not None

@pytest.mark.asyncio
async def test_select_date(bot, mock_update, context):
    mock_update.callback_query.data = "sport_tenis"
    # Mock the answer method
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    
    await bot.select_date(mock_update, context)
    
    assert context.user_data["sport"] == "tenis"
    mock_update.callback_query.edit_message_text.assert_called_once()

@pytest.mark.parametrize("nif,expected", [
    ("12345678Z", True),   # Valid NIF
    ("00000000T", True),   # Valid NIF
    ("X0000000T", True),   # Valid NIE starting with X (0)
    ("Y0000000Z", True),   # Valid NIE starting with Y (1)
    ("Z0000000M", True),   # Valid NIE starting with Z (2)
    ("ABCD1234Z", False),  # Invalid format
    ("", False),           # Empty string
    ("1234567", False),    # Too short
    ("123456789Z", False), # Too long
    ("12345678A", False),  # Invalid check digit
])
def test_validate_nif(bot, nif, expected):
    result = bot.validate_nif(nif)
    assert result == expected, f"Failed for NIF: {nif}, expected {expected} but got {result}"

@pytest.mark.asyncio
async def test_collect_id_valid(bot, mock_update, context):
    mock_update.message.text = "00000000T"
    
    result = await bot.collect_id(mock_update, context)
    
    assert context.user_data["user_id"] == "00000000T"
    mock_update.message.reply_text.assert_called_once_with("Por favor, introduce tu contraseña:")

@pytest.mark.asyncio
async def test_collect_id_invalid(bot, mock_update, context):
    mock_update.message.text = "invalid_nif"
    
    result = await bot.collect_id(mock_update, context)
    
    assert "user_id" not in context.user_data
    mock_update.message.reply_text.assert_called_once_with("El NIF introducido no es válido. Por favor, introduce un NIF válido:")

@pytest.mark.asyncio
async def test_collect_player2_tenis(bot, mock_update, context):
    # Setup required context data
    mock_update.message.text = "00000000T"
    context.user_data.update({
        "sport": "tenis",
        "date": "2024-03-20",
        "time": "09:00",
        "user_id": "12345678Z"
    })
    mock_update.message.reply_text = AsyncMock()
    
    await bot.collect_player2(mock_update, context)
    
    assert context.user_data["player2_nif"] == "00000000T"

@pytest.mark.asyncio
async def test_collect_player2_padel(bot, mock_update, context):
    mock_update.message.text = "00000000T"
    context.user_data["sport"] = "padel"
    mock_update.message.reply_text = AsyncMock()
    
    await bot.collect_player2(mock_update, context)
    
    assert context.user_data["player2_nif"] == "00000000T"
    mock_update.message.reply_text.assert_called_once_with("Por favor, introduce el NIF del tercer jugador:") 