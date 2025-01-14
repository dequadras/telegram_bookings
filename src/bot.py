import json
import logging
import re
from datetime import datetime, timedelta

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
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

# todo (later) check credentials work right away
# todo (later) check that the booking would work (without actually booking, eg try dummy booking)
# todo (later) prompt if we want to book at a different time if the exact hour is not available
# todo code that checks at 7am in the morning how many courts are available, every 20 seconds
# (later) todo remove warnings in the bot
# todo if i select one NIF for player 2, remove it from the options for player 3 and 4, same with player 3 removed 4

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
    SELECTING_BOOKING_TYPE,
    UPDATING_ID,
    UPDATING_PASSWORD,
) = range(12)


class TenisBookingBot:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.db = DatabaseManager()
        # Load schedule data
        with open("src/schedule.json", "r") as f:
            self.schedule = json.load(f)
        self.admin_id = 249843154  # Add admin telegram ID

    async def log_conversation(self, telegram_id: int, message_type: str, message_text: str):
        """Log a conversation message"""
        query = """
        INSERT INTO conversation_logs (telegram_id, message_type, message_text)
        VALUES (?, ?, ?);
        """
        self.db.execute_query(query, (telegram_id, message_type, message_text))

    async def notify_admin(self, message: str):
        """Send notification to admin"""
        try:
            await self.application.bot.send_message(chat_id=self.admin_id, text=message, parse_mode="Markdown")
        except Exception as e:
            self.logger.error(f"Failed to send admin notification: {e}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command"""
        # Log user's message
        await self.log_conversation(update.effective_user.id, "user_message", "Command: /start")

        user = update.effective_user
        self.logger.info(f"New user started bot: {user.id} ({user.username})")
        self.db.add_user(
            telegram_id=user.id,
            username=user.username,
            password=None,
            first_name=user.first_name,
            last_name=user.last_name,
        )

        welcome_text = (
            f"¡Bienvenido/a {user.first_name}! 🎾\n\n"
            "Te puedo ayudar a reservar pistas de tenis y padel. Esto es lo que puedes hacer:\n"
            "/book - Reservar una pista\n"
            "/mybookings - Ver tus reservas\n"
            "/getcredits - Obtener reservas premium\n"
            "/help - Obtener ayuda"
        )

        # Log bot's response
        await self.log_conversation(update.effective_user.id, "bot_response", welcome_text)

        await update.message.reply_text(welcome_text)

    async def book(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the booking process by selecting sport"""
        self.logger.info(f"Book command received from user {update.effective_user.id}")
        self.logger.debug(f"Update object: {update}")
        self.logger.info(f"User {update.effective_user.id} started booking process")

        # Clear any existing conversation data
        context.user_data.clear()

        keyboard = [
            [
                InlineKeyboardButton("Tenis 🎾", callback_data="sport_tenis"),
                InlineKeyboardButton("Padel 🏸", callback_data="sport_padel"),
            ]
        ]

        message_text = "Por favor, selecciona un deporte:"

        # Add error handling and logging
        try:
            # Log bot's response
            await self.log_conversation(update.effective_user.id, "bot_response", message_text)

            await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard))
            self.logger.debug("Sport selection keyboard sent successfully")
            return SELECTING_SPORT
        except Exception:
            error_message = "Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo."
            # Log error response
            await self.log_conversation(update.effective_user.id, "bot_response", error_message)
            await update.message.reply_text(error_message)
            return ConversationHandler.END

    async def select_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle sport selection and show date options"""
        query = update.callback_query
        await query.answer()
        sport = query.data.split("_")[1]
        self.logger.info(f"User {update.effective_user.id} selected sport: {sport}")
        context.user_data["sport"] = sport

        # Create date selection keyboard with formatted dates
        spanish_days = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
        spanish_months = {
            1: "enero",
            2: "febrero",
            3: "marzo",
            4: "abril",
            5: "mayo",
            6: "junio",
            7: "julio",
            8: "agosto",
            9: "septiembre",
            10: "octubre",
            11: "noviembre",
            12: "diciembre",
        }

        keyboard = []
        for i in range(7):
            date = datetime.now() + timedelta(days=i + 2)
            # Store date in YYYY-MM-DD format for internal use
            date_value = date.strftime("%Y-%m-%d")
            # Format display text as "Día DD de Mes"
            display_text = f"{spanish_days[date.weekday()]} {date.day} de {spanish_months[date.month]}"
            keyboard.append([InlineKeyboardButton(display_text, callback_data=f"date_{date_value}")])

        await query.edit_message_text("Por favor, selecciona una fecha:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECTING_DATE

    async def select_preference(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle time selection and ask for booking preference"""
        query = update.callback_query
        await query.answer()
        selected_time = query.data.split("_")[1]
        self.logger.info(f"User {update.effective_user.id} selected time: {selected_time}")
        context.user_data["time"] = selected_time

        # Store selected preference in context
        context.user_data["preference"] = query.data.split("_")[1]

        # Check if user already has credentials stored
        user_data = self.db.get_user_credentials(update.effective_user.id)
        if user_data and user_data["username"] and user_data["password"]:
            # If credentials exist, store them
            context.user_data["user_id"] = user_data["username"]
            context.user_data["password"] = user_data["password"]
            # Call prompt_player_selection directly with the query message
            keyboard = []
            # Get recent players for this user
            recent_players = self.db.get_frequent_partners(update.effective_user.id, limit=5)
            if recent_players:
                for player in recent_players:
                    display_text = f"{player['name']} ({player['nif']})" if player["name"] else player["nif"]
                    keyboard.append([KeyboardButton(display_text)])

            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            await query.message.reply_text(
                "Por favor, selecciona el jugador 2 o introduce un nuevo NIF:", reply_markup=reply_markup
            )
            return ENTERING_PLAYER2

        # If no credentials, ask for them
        await query.edit_message_text("Por favor, introduce tu usuario (NIF):")
        return ENTERING_ID

    async def collect_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle ID input and ask for password"""
        user_id = update.message.text.upper()
        if not self.validate_nif(user_id):
            self.logger.warning(f"User {update.effective_user.id} entered invalid NIF: {user_id}")
            await update.message.reply_text("El NIF introducido no es válido. Por favor, introduce un NIF válido:")
            return ENTERING_ID

        self.logger.info(f"User {update.effective_user.id} entered valid NIF")
        context.user_data["user_id"] = user_id

        await update.message.reply_text(
            "Por favor, introduce tu contraseña de rcpolo.com (por defecto es nombre y año de "
            "nacimiento. ej: Pedro1982):"
        )
        return ENTERING_PASSWORD

    async def collect_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle password input and ask for second player"""
        self.logger.info(f"User {update.effective_user.id} entered password")
        context.user_data["password"] = update.message.text

        # Instead of directly asking for NIF, use prompt_player_selection
        return await self.prompt_player_selection(update, context, 2)

    async def collect_player2(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle second player selection"""
        return await self.handle_player_input(update, context, 2)

    async def collect_player3(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle third player selection"""
        return await self.handle_player_input(update, context, 3)

    async def collect_player4(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle fourth player selection"""
        return await self.handle_player_input(update, context, 4)

    async def select_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle date selection and show time options"""
        query = update.callback_query
        await query.answer()
        selected_date = query.data.split("_")[1]
        self.logger.info(f"User {update.effective_user.id} selected date: {selected_date}")
        context.user_data["date"] = selected_date

        # Get time slots for selected sport
        sport = context.user_data["sport"]
        time_slots = self.schedule[sport]["time_slots"]
        times = [slot["start_time"] for slot in time_slots]

        keyboard = [[InlineKeyboardButton(time, callback_data=f"time_{time}")] for time in times]

        await query.edit_message_text("Por favor, selecciona una hora:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECTING_TIME

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel and end the conversation."""
        self.logger.info(f"User {update.effective_user.id} cancelled the booking process")
        await update.message.reply_text("Booking process cancelled. You can start a new booking with /book")
        return ConversationHandler.END

    async def confirm_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
        """Handle the final booking confirmation"""
        user = update.effective_user

        # Check if user has available credits (only for premium bookings)
        if context.user_data.get("is_premium", False):
            credits = self.db.get_user_credits(user.id)
            if credits <= 0:
                message = "❌ No tienes reservas disponibles.\n\n" "Puedes conseguir más reservas usando /getcredits"
                if query:
                    await query.edit_message_text(message)
                else:
                    await update.message.reply_text(message)
                return ConversationHandler.END

            # Deduct one credit only for premium bookings
            if not self.db.deduct_booking_credit(user.id):
                message = "❌ Error al procesar la reserva.\n" "Por favor, intenta de nuevo o contacta con soporte."
                if query:
                    await query.edit_message_text(message)
                else:
                    await update.message.reply_text(message)
                return ConversationHandler.END

        self.logger.info(
            f"Processing booking confirmation for user {user.id}:\n"
            f"Sport: {context.user_data['sport']}\n"
            f"Date: {context.user_data['date']}\n"
            f"Time: {context.user_data['time']}"
        )

        # Ensure user exists in database and update their credentials
        self.db.add_user(
            telegram_id=user.id,
            username=context.user_data["user_id"],  # NIF
            password=context.user_data["password"],
            first_name=user.first_name or "",
            last_name=user.last_name or "",
        )

        # Compile booking details
        booking_details = (
            f"Resumen de la Reserva:\n"
            f"Deporte: {context.user_data['sport'].title()}\n"
            f"Fecha: {context.user_data['date']}\n"
            f"Hora: {context.user_data['time']}\n"
            f"Jugador 1 (Tú): {context.user_data['user_id']}\n"
            f"Jugador 2: {context.user_data['player2_nif']}"
        )

        # Create list of player NIFs
        player_nifs = [context.user_data["player2_nif"]]

        # Add padel-specific players if applicable
        if context.user_data["sport"] == "padel":
            booking_details += f"\nJugador 3: {context.user_data['player3_nif']}"
            booking_details += f"\nJugador 4: {context.user_data['player4_nif']}"
            player_nifs.extend([context.user_data["player3_nif"], context.user_data["player4_nif"]])

        # Store booking in database
        self.db.add_booking(
            telegram_id=user.id,
            booking_date=context.user_data["date"],
            booking_time=context.user_data["time"],
            sport=context.user_data["sport"],
            player_nifs=json.dumps(player_nifs),
            is_premium=context.user_data["is_premium"],
        )

        # Send confirmation message with remaining credits
        message = (
            f"{booking_details}\n\n"
            f"¡Tu reserva ha sido programada! ✅\n"
            f"Se tramitará la reserva en rcpolo.com el día anterior a las "
            f"{' 7:00' if context.user_data['is_premium'] else ' 8:00'}am"
        )

        # Only add remaining credits info for premium bookings
        if context.user_data.get("is_premium", False):
            remaining_credits = self.db.get_user_credits(user.id)
            message += f"\n\nTe quedan {remaining_credits} reservas disponibles."

        if query:
            await query.edit_message_text(message)
        else:
            await update.message.reply_text(message)

        # After successful booking, notify admin
        admin_message = (
            "🎾 *Nueva Reserva externa*\n\n"
            f"Usuario: {user.first_name} (@{user.username})\n"
            f"Deporte: {context.user_data['sport'].title()}\n"
            f"Fecha: {context.user_data['date']}\n"
            f"Hora: {context.user_data['time']}"
        )
        await self.notify_admin(admin_message)

        return ConversationHandler.END

    async def prompt_player_selection(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, player_number: int
    ) -> int:
        """Handle player selection with option to choose from history or enter new NIF"""
        user_id = update.effective_user.id

        # Get recent players for this user
        recent_players = self.db.get_frequent_partners(user_id, limit=5)

        keyboard = []
        # Add recent players if any exist
        if recent_players:
            for player in recent_players:
                # Display name if available, otherwise just NIF
                display_text = f"{player['name']} ({player['nif']})" if player["name"] else player["nif"]
                keyboard.append([KeyboardButton(display_text)])

        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            f"Por favor, selecciona el jugador {player_number} o introduce un nuevo NIF:", reply_markup=reply_markup
        )

        # Return the appropriate state based on player number
        return {2: ENTERING_PLAYER2, 3: ENTERING_PLAYER3, 4: ENTERING_PLAYER4}[player_number]

    async def handle_player_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, player_number: int):
        """Handle player selection or NIF input"""
        text = update.message.text

        # Check if this is a selection from recent players
        if "(" in text and ")" in text:
            # Extract NIF from format "Name (NIF)"
            nif = text[text.find("(") + 1 : text.find(")")].strip()
        else:
            # Treat as new NIF input
            nif = text.upper()

        # Validate NIF
        if not self.validate_nif(nif):
            await update.message.reply_text(
                f"El NIF del jugador {player_number} no es válido. Por favor, introduce un NIF válido:",
                reply_markup=ReplyKeyboardRemove(),
            )
            return {2: ENTERING_PLAYER2, 3: ENTERING_PLAYER3, 4: ENTERING_PLAYER4}[player_number]

        # Store the NIF in context
        context.user_data[f"player{player_number}_nif"] = nif

        # Determine next step based on sport and player number
        if player_number < 4 and context.user_data["sport"] == "padel":
            return await self.prompt_player_selection(update, context, player_number + 1)
        else:
            # Instead of going to confirm_booking, go to select_booking_type
            return await self.select_booking_type(update, context)

    def validate_nif(self, nif: str) -> bool:
        """
        Validates a Spanish NIF/NIE/CIF
        Returns True if valid, False otherwise
        """
        self.logger.debug(f"Validating NIF: {nif}")
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

    async def info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's available booking credits"""
        user_id = update.effective_user.id
        credits = self.db.get_user_credits(user_id)

        await update.message.reply_text(
            f"🎾 Información de tu cuenta:\n\n"
            f"Reservas disponibles: {credits}\n\n"
            "Puedes conseguir 10 reservas adicionales usando /getcredits"
        )

    async def buy_credits_premium(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the purchase of additional booking credits"""
        paypal_link = "https://www.sandbox.paypal.com/ncp/payment/6MBDS94TBXXEA"

        await update.message.reply_text(
            "🎯 Comprar reservas adicionales:\n\n"
            "• 5 reservas por 5€\n"
            "• Pago seguro con PayPal\n\n"
            "Para completar tu compra:\n"
            f"1️⃣ [Haz click aquí para pagar]({paypal_link})\n"
            "2️⃣ Las reservas se añadirán automáticamente a tu cuenta\n\n"
            "_Las reservas no caducan_",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )

    async def buy_credits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the purchase of additional booking credits"""
        await update.message.reply_text(
            "🔜 *Reservas premium*\n\n"
            "Esta funcionalidad estará disponible próximamente.\n\n"
            "Por favor, vuelve a intentarlo en unas semanas.",
            parse_mode="Markdown",
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command"""
        help_text = (
            "🤖 *¿Qué puedo hacer?*\n\n"
            "Te ayudo a reservar pistas de tenis y pádel en el RCPolo. Estos son mis comandos:\n\n"
            "🎾 */book* - Reservar una pista\n"
            "📅 */mybookings* - Ver tus reservas actuales\n"
            "🔑 */password* - Actualizar credenciales\n"
            "⭐️ */getcredits* - Obtener reservas premium\n"
            "❓ */help* - Ver este mensaje de ayuda\n\n"
            "Para empezar una reserva, simplemente usa el comando /book\n\n"
            "📧 Si tienes problemas, escribe a autobooking6@gmail.com"
        )

        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def mybookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's current bookings"""
        user_id = update.effective_user.id
        self.logger.info(f"User {user_id} checking their bookings")
        bookings = self.db.get_user_bookings(user_id)

        if not bookings:
            await update.message.reply_text("No tienes reservas pendientes. Usa /book para hacer una nueva reserva.")
            return

        message = "📅 *Tus Reservas:*\n\n"
        keyboard = []

        for booking in bookings:
            # Convert player_nifs from JSON string to list
            players = json.loads(booking["player_nifs"])

            # Format the booking details
            message += (
                f"*{booking['sport'].title()}* - {booking['booking_date']} a las {booking['booking_time']}\n"
                f"Estado: {self._format_status(booking['status'])}\n"
                f"Jugadores: Tú + {len(players)} más\n"
                f"──────────────\n"
            )

            # Add cancel button if booking is pending
            if booking["status"] == "pending":
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"❌ Cancelar {booking['sport']} {booking['booking_date']} {booking['booking_time']}",
                            callback_data=f"cancel_{booking['id']}",
                        )
                    ]
                )

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)

    def _format_status(self, status: str) -> str:
        """Format booking status for display"""
        status_emojis = {
            "pending": "⏳ Pendiente",
            "completed": "✅ Confirmada",
            "failed": "❌ Fallida",
            "cancelled": "🚫 Cancelada",
        }
        return status_emojis.get(status, status)

    async def cancel_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle booking cancellation"""
        query = update.callback_query
        await query.answer()

        if query.data.startswith("confirm_cancel_"):
            # User confirmed cancellation
            booking_id = int(query.data.split("_")[2])
            user_id = update.effective_user.id

            # Update booking status in database
            if self.db.cancel_booking(booking_id, user_id):
                # Refund the booking credit
                self.db.add_booking_credit(user_id, 1)
                await query.edit_message_text(
                    "✅ Reserva cancelada correctamente.\n\nSe ha devuelto el crédito a tu cuenta.",
                    parse_mode="Markdown",
                )
            else:
                await query.edit_message_text(
                    "❌ No se pudo cancelar la reserva. Por favor, inténtalo de nuevo o contacta con soporte.",
                    parse_mode="Markdown",
                )
        else:
            # Show confirmation dialog
            booking_id = int(query.data.split("_")[1])
            keyboard = [
                [
                    InlineKeyboardButton("Sí, cancelar", callback_data=f"confirm_cancel_{booking_id}"),
                    InlineKeyboardButton("No, mantener", callback_data="keep_booking"),
                ]
            ]
            await query.edit_message_text(
                "¿Estás seguro de que quieres cancelar esta reserva?", reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def keep_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle when user decides not to cancel the booking"""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("✅ Tu reserva se ha mantenido sin cambios.")

    async def select_booking_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask user to select between premium and free booking"""
        keyboard = [
            [
                InlineKeyboardButton("Premium (7:00) - 1 crédito", callback_data="booking_premium"),
                InlineKeyboardButton("Básica (8:00)", callback_data="booking_free"),
            ]
        ]

        await update.message.reply_text(
            "Por favor, selecciona el tipo de reserva:\n\n"
            "🌟 *Premium*: Se intenta reservar a las 7:00 (coste: 1 crédito)\n"
            "🆓 *Básica*: Se intenta reservar a las 8:00 (sin coste, menor probabilidad)",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return SELECTING_BOOKING_TYPE

    async def process_booking_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle booking type selection"""
        query = update.callback_query
        await query.answer()

        is_premium = query.data == "booking_premium"
        context.user_data["is_premium"] = is_premium

        if is_premium:
            # Check credits only for premium bookings
            credits = self.db.get_user_credits(update.effective_user.id)
            if credits <= 0:
                await query.edit_message_text(
                    "❌ No tienes créditos disponibles para reservas premium.\n\n"
                    "Puedes conseguir más créditos usando /getcredits o hacer una reserva básica."
                )
                return ConversationHandler.END

        # Call confirm_booking with the query object
        return await self.confirm_booking(update, context, query)

    async def update_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /password command to update credentials"""
        self.logger.info(f"User {update.effective_user.id} updating credentials")
        await update.message.reply_text("Por favor, introduce tu nuevo usuario (NIF):")
        return UPDATING_ID

    async def handle_update_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new ID input when updating credentials"""
        user_id = update.message.text.upper()
        if not self.validate_nif(user_id):
            await update.message.reply_text("El NIF introducido no es válido. Por favor, introduce un NIF válido:")
            return UPDATING_ID

        context.user_data["new_user_id"] = user_id
        await update.message.reply_text("Por favor, introduce tu nueva contraseña:")
        return UPDATING_PASSWORD

    async def handle_update_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new password input when updating credentials"""
        new_password = update.message.text
        user_id = update.effective_user.id

        # Update credentials in database
        self.db.update_user_credentials(
            telegram_id=user_id, username=context.user_data["new_user_id"], password=new_password
        )

        await update.message.reply_text("✅ Tus credenciales han sido actualizadas correctamente.")
        return ConversationHandler.END

    def run(self):
        """Run the bot"""
        self.logger.info("Initializing bot")
        application = Application.builder().token(CONFIG["bot"].TOKEN).post_init(post_init).build()
        self.application = application

        # First, create the conversation handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("book", self.book)],
            states={
                SELECTING_SPORT: [CallbackQueryHandler(self.select_date, pattern=r"^sport_(tenis|padel)$")],
                SELECTING_DATE: [CallbackQueryHandler(self.select_time, pattern=r"^date_\d{4}-\d{2}-\d{2}$")],
                SELECTING_TIME: [CallbackQueryHandler(self.select_preference, pattern=r"^time_")],
                SELECTING_PREFERENCE: [CallbackQueryHandler(self.select_preference, pattern=r"^pref_")],
                ENTERING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_id)],
                ENTERING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_password)],
                ENTERING_PLAYER2: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_player2)],
                ENTERING_PLAYER3: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_player3)],
                ENTERING_PLAYER4: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_player4)],
                SELECTING_BOOKING_TYPE: [CallbackQueryHandler(self.process_booking_type)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel), CommandHandler("book", self.book)],
            name="booking_conversation",
            persistent=False,
        )

        # Register handlers in specific order
        handlers = [
            # First, add the conversation handler
            conv_handler,
            # Then add other command handlers
            CommandHandler("start", self.start),
            CommandHandler("help", self.help),
            CommandHandler("mybookings", self.mybookings),
            # Add callback query handlers
            CallbackQueryHandler(self.cancel_booking, pattern="^(cancel_|confirm_cancel_)"),
            CallbackQueryHandler(self.keep_booking, pattern="^keep_booking"),
            # Add the password update conversation handler
            ConversationHandler(
                entry_points=[CommandHandler("password", self.update_password)],
                states={
                    UPDATING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_update_id)],
                    UPDATING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_update_password)],
                },
                fallbacks=[CommandHandler("cancel", self.cancel)],
            ),
            # Add buy command handler
            CommandHandler("getcredits", self.buy_credits),
        ]

        # Register all handlers with error handling
        for handler in handlers:
            try:
                application.add_handler(handler)
                self.logger.info(f"Successfully added handler: {handler.__class__.__name__}")
            except Exception as e:
                self.logger.error(f"Failed to add handler {handler.__class__.__name__}: {e}")

        # Create message logging middleware class
        class MessageLoggingMiddleware:
            def __init__(self, bot_instance):
                self.bot = bot_instance

            async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
                """Log all messages before they are processed"""
                if update.message:
                    await self.bot.log_conversation(update.effective_user.id, "user_message", update.message.text)
                elif update.callback_query:
                    await self.bot.log_conversation(
                        update.effective_user.id, "user_callback", update.callback_query.data
                    )

                # If this is a bot response (check context.bot_data)
                if hasattr(update, "effective_message") and update.effective_message:
                    if getattr(context.bot_data, "is_bot_response", False):
                        await self.bot.log_conversation(
                            update.effective_chat.id, "bot_response", update.effective_message.text
                        )

        # Add middleware to log all messages
        application.add_handler(MessageHandler(filters.ALL, MessageLoggingMiddleware(self)), group=-1)

        # Start the bot
        self.logger.info("Starting polling...")
        application.run_polling()


async def post_init(application: Application) -> None:
    await application.bot.set_my_description(
        "¡Hola! Soy el bot de reservas del RCPolo. Pulsa 'Iniciar' para empezar. 🎾\n"
        'Este bot se "despierta" a las 7am para procesar las reservas de pistas. Si alguna vez te has visto en la'
        " situación de no tener pistas disponibles por haberte despertado tarde, esto puede ser tu solución.\n"
        "Usa el comando /book para empezar una reserva. Esta se guardará y se gestionará el día anterior a la "
        "reserva a las 7am\n"
        "Encontrarás más información con el comando /help"
    )

    await application.bot.set_my_short_description("Bot de reservas de pistas del RCPolo")

    # Change from default menu button (3 bars) to text "Menu"
    await application.bot.set_chat_menu_button(menu_button={"type": "commands", "text": "Menu"})

    # Set up commands that appear in the menu
    commands = [
        ("start", "Iniciar el bot"),
        ("book", "Reservar una pista"),
        ("mybookings", "Ver mis reservas"),
        ("getcredits", "Obtener reservas premium"),
        ("help", "Obtener ayuda"),
    ]

    await application.bot.set_my_commands(commands)


if __name__ == "__main__":
    # Enhanced logging configuration
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S"
    )
    # Set httpx logger to WARNING level to reduce HTTP request logs
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("Starting Tennis Booking Bot")
    bot = TenisBookingBot()
    bot.run()
