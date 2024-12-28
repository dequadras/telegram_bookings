import json
import logging
import re
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import CONFIG
from database import DatabaseManager

# todo NIF and password should only be asked once
# todo players should be saved (e.g. next time have the option to click on a person's name instead of typing nif), maybe prompt for name or maybe get it from the web , show options by most used
# todo check credentials work right away
# todo cehck that the booking would work (without actually booking, eg try dummy booking)
# todo prompt if we want to book at a different time if the exact hour is not available
# States for conversation handler
(
    SELECTING_SPORT,
    SELECTING_DATE,
    SELECTING_TIME,
    SELECTING_PREFERENCE,
    ENTERING_ID,
    ENTERING_PASSWORD,
    ENTERING_PLAYER2,
    ENTERING_PLAYER3,
    ENTERING_PLAYER4,
) = range(9)


class TenisBookingBot:
    def __init__(self):
        self.db = DatabaseManager()
        # Load schedule data
        with open("src/schedule.json", "r") as f:
            self.schedule = json.load(f)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command"""
        user = update.effective_user
        self.db.add_user(user.id, user.username, user.first_name, user.last_name)

        welcome_text = (
            f"¡Bienvenido/a {user.first_name}! 🎾\n\n"
            "Te puedo ayudar a reservar pistas. Esto es lo que puedes hacer:\n"
            "/book - Reservar una pista\n"
            "/mybookings - Ver tus reservas\n"
            "/subscribe - Obtener reservas ilimitadas\n"
            "/help - Obtener ayuda"
        )

        await update.message.reply_text(welcome_text)

    async def book(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the booking process by selecting sport"""
        keyboard = [
            [
                InlineKeyboardButton("Tenis 🎾", callback_data="sport_tenis"),
                InlineKeyboardButton("Padel 🏸", callback_data="sport_padel"),
            ]
        ]

        await update.message.reply_text("Please select a sport:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECTING_SPORT

    async def select_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle sport selection and show date options"""
        query = update.callback_query
        await query.answer()

        # Store selected sport in context
        context.user_data["sport"] = query.data.split("_")[1]

        # Create date selection keyboard (same as before)
        dates = []
        for i in range(7):
            date = datetime.now() + timedelta(days=i + 2)
            dates.append(date.strftime("%Y-%m-%d"))

        keyboard = [[InlineKeyboardButton(date, callback_data=f"date_{date}")] for date in dates]

        await query.edit_message_text("Por favor, selecciona una fecha:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECTING_DATE

    async def select_preference(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle time selection and ask for booking preference"""
        query = update.callback_query
        await query.answer()

        # Store selected time in context before moving to preference
        context.user_data["time"] = query.data.split("_")[1]

        # Store selected preference in context
        context.user_data["preference"] = query.data.split("_")[1]

        # Move to ID collection
        await query.edit_message_text("Por favor, introduce tu ID (NIF o número de socio del RCPolo):")
        return ENTERING_ID

    async def collect_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle ID input and ask for password"""
        user_id = update.message.text

        if not self.validate_nif(user_id):
            await update.message.reply_text("El NIF introducido no es válido. Por favor, introduce un NIF válido:")
            return ENTERING_ID

        context.user_data["user_id"] = user_id

        await update.message.reply_text("Por favor, introduce tu contraseña:")
        return ENTERING_PASSWORD

    async def collect_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle password input and ask for second player"""
        context.user_data["password"] = update.message.text

        await update.message.reply_text("Por favor, introduce el NIF del segundo jugador:")
        return ENTERING_PLAYER2

    async def collect_player2(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle second player input and either finish or ask for more players"""
        player2_nif = update.message.text

        if not self.validate_nif(player2_nif):
            await update.message.reply_text(
                "El NIF del segundo jugador no es válido. Por favor, introduce un NIF válido:"
            )
            return ENTERING_PLAYER2

        context.user_data["player2_nif"] = player2_nif

        if context.user_data["sport"] == "padel":
            await update.message.reply_text("Por favor, introduce el NIF del tercer jugador:")
            return ENTERING_PLAYER3
        else:
            return await self.confirm_booking(update, context)

    async def collect_player3(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle third player input and ask for fourth player"""
        player3_nif = update.message.text

        if not self.validate_nif(player3_nif):
            await update.message.reply_text(
                "El NIF del tercer jugador no es válido. Por favor, introduce un NIF válido:"
            )
            return ENTERING_PLAYER3

        context.user_data["player3_nif"] = player3_nif

        await update.message.reply_text("Por favor, introduce el NIF del cuarto jugador:")
        return ENTERING_PLAYER4

    async def collect_player4(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle fourth player input and proceed to booking confirmation"""
        player4_nif = update.message.text

        if not self.validate_nif(player4_nif):
            await update.message.reply_text(
                "El NIF del cuarto jugador no es válido. Por favor, introduce un NIF válido:"
            )
            return ENTERING_PLAYER4

        context.user_data["player4_nif"] = update.message.text
        return await self.confirm_booking(update, context)

    async def select_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle date selection and show time options"""
        query = update.callback_query
        await query.answer()

        # Store selected date in context
        context.user_data["date"] = query.data.split("_")[1]

        # Get time slots for selected sport
        sport = context.user_data["sport"]
        time_slots = self.schedule[sport]["time_slots"]
        times = [slot["start_time"] for slot in time_slots]

        keyboard = [[InlineKeyboardButton(time, callback_data=f"time_{time}")] for time in times]

        await query.edit_message_text("Por favor, selecciona una hora:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECTING_TIME

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel and end the conversation."""
        await update.message.reply_text("Booking process cancelled. You can start a new booking with /book")
        return ConversationHandler.END

    async def confirm_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the final booking confirmation"""
        # Compile booking details
        booking_details = (
            f"Resumen de la Reserva:\n"
            f"Deporte: {context.user_data['sport'].title()}\n"
            f"Fecha: {context.user_data['date']}\n"
            f"Hora: {context.user_data['time']}\n"
            f"Jugador 1 (Tú): {context.user_data['user_id']}\n"
            f"Jugador 2: {context.user_data['player2_nif']}"
        )

        # Add padel-specific players if applicable
        if context.user_data["sport"] == "padel":
            booking_details += f"\nJugador 3: {context.user_data['player3_nif']}"
            booking_details += f"\nJugador 4: {context.user_data['player4_nif']}"

        # Send confirmation message
        await update.message.reply_text(
            f"{booking_details}\n\n¡Tu reserva ha sido confirmada! ✅"  # todo mention it is schedule for booking and the hour
        )

        return ConversationHandler.END

    def validate_nif(self, nif: str) -> bool:
        """
        Validates a Spanish NIF/NIE/CIF
        Returns True if valid, False otherwise
        """
        # Remove any whitespace and convert to uppercase
        nif = nif.strip().upper()

        # Basic format validation
        nif_pattern = r"^[0-9XYZ]\d{7}[A-Z]$"
        if not re.match(nif_pattern, nif):
            return False

        # Letter validation
        letters = "TRWAGMYFPDXBNJZSQVHLCKE"

        # Handle NIE (X, Y, Z)
        if nif[0] in "XYZ":
            nif_number = str("XYZ".index(nif[0])) + nif[1:8]
        else:
            nif_number = nif[:8]

        # Calculate check letter
        check_letter = letters[int(nif_number) % 23]

        # Compare calculated letter with provided letter
        return nif[-1] == check_letter

    def run(self):
        """Run the bot"""
        application = Application.builder().token(CONFIG["bot"].TOKEN).build()

        # Update conversation handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("book", self.book)],
            states={
                SELECTING_SPORT: [CallbackQueryHandler(self.select_date, pattern="^sport_")],
                SELECTING_DATE: [CallbackQueryHandler(self.select_time, pattern="^date_")],
                SELECTING_TIME: [CallbackQueryHandler(self.select_preference, pattern="^time_")],
                SELECTING_PREFERENCE: [CallbackQueryHandler(self.select_preference, pattern="^pref_")],
                ENTERING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_id)],
                ENTERING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_password)],
                ENTERING_PLAYER2: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_player2)],
                ENTERING_PLAYER3: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_player3)],
                ENTERING_PLAYER4: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_player4)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )

        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(conv_handler)

        # Start the bot
        application.run_polling()


if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
    bot = TenisBookingBot()
    bot.run()
