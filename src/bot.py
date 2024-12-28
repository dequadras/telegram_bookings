from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)
import logging
from datetime import datetime, timedelta
from database import DatabaseManager
from config import CONFIG

# todo NIf and password should only be asked once
# todo players should be saved (e.g. next time have the option to click on a person's name instead of typing nif), maybe prompt for name or maybe get it from the web , show options by most used
# todo check credentials work right away
# todo cehck that the booking would work (without actually booking, eg try dummy booking)
# todo prompt if we want to book at a different time if the exact hour is not available
# States for conversation handler
SELECTING_SPORT, SELECTING_DATE, SELECTING_TIME, SELECTING_PREFERENCE, ENTERING_ID, ENTERING_PASSWORD, ENTERING_PLAYER2, ENTERING_PLAYER3, ENTERING_PLAYER4 = range(9)

class TennisBookingBot:
    def __init__(self):
        self.db = DatabaseManager()
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command"""
        user = update.effective_user
        self.db.add_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
        
        welcome_text = (
            f"Welcome {user.first_name}! 🎾\n\n"
            "I can help you book tennis courts. Here's what you can do:\n"
            "/book - Book a tennis court\n"
            "/mybookings - View your bookings\n"
            "/subscribe - Get unlimited bookings\n"
            "/help - Get help"
        )
        
        await update.message.reply_text(welcome_text)
        
    async def book(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the booking process by selecting sport"""
        keyboard = [
            [
                InlineKeyboardButton("Tennis 🎾", callback_data="sport_tennis"),
                InlineKeyboardButton("Padel 🏸", callback_data="sport_padel")
            ]
        ]
        
        await update.message.reply_text(
            "Please select a sport:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_SPORT

    async def select_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle sport selection and show date options"""
        query = update.callback_query
        await query.answer()
        
        # Store selected sport in context
        context.user_data['sport'] = query.data.split('_')[1]
        
        # Create date selection keyboard (same as before)
        dates = []
        for i in range(7):
            date = datetime.now() + timedelta(days=i)
            dates.append(date.strftime("%Y-%m-%d"))
            
        keyboard = [[InlineKeyboardButton(date, callback_data=f"date_{date}")] 
                   for date in dates]
        
        await query.edit_message_text(
            "Please select a date:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_DATE

    async def select_preference(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle time selection and ask for booking preference"""
        query = update.callback_query
        await query.answer()
        
        # Store selected time in context before moving to preference
        context.user_data['time'] = query.data.split('_')[1]
        
        # Store selected preference in context
        context.user_data['preference'] = query.data.split('_')[1]
        
        # Move to ID collection
        await query.edit_message_text(
            "Please enter your ID (NIF or RCPolo number):"
        )
        return ENTERING_ID

    async def collect_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle ID input and ask for password"""
        context.user_data['user_id'] = update.message.text
        
        await update.message.reply_text(
            "Please enter your password:"
        )
        return ENTERING_PASSWORD

    async def collect_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle password input and ask for second player"""
        context.user_data['password'] = update.message.text
        
        await update.message.reply_text(
            "Please enter the NIF of the second player:"
        )
        return ENTERING_PLAYER2

    async def collect_player2(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle second player input and either finish or ask for more players"""
        context.user_data['player2_nif'] = update.message.text
        
        if context.user_data['sport'] == 'padel':
            await update.message.reply_text(
                "Please enter the NIF of the third player:"
            )  # todo add nif validator
            return ENTERING_PLAYER3
        else:
            return await self.confirm_booking(update, context)

    async def collect_player3(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle third player input and ask for fourth player"""
        context.user_data['player3_nif'] = update.message.text
        
        await update.message.reply_text(
            "Please enter the NIF of the fourth player:"
        )
        return ENTERING_PLAYER4

    async def collect_player4(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle fourth player input and proceed to booking confirmation"""
        context.user_data['player4_nif'] = update.message.text
        return await self.confirm_booking(update, context)

    async def select_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle date selection and show time options"""
        query = update.callback_query
        await query.answer()
        
        # Store selected date in context
        context.user_data['date'] = query.data.split('_')[1]
        
        # Create time selection keyboard
        # Assuming available time slots from 9:00 to 21:00
        times = [f"{hour:02d}:00" for hour in range(9, 22)]
        
        keyboard = [[InlineKeyboardButton(time, callback_data=f"time_{time}")] 
                   for time in times]
        
        await query.edit_message_text(
            "Please select a time:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_TIME

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel and end the conversation."""
        await update.message.reply_text(
            'Booking process cancelled. You can start a new booking with /book'
        )
        return ConversationHandler.END

    async def confirm_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the final booking confirmation"""
        # Compile booking details
        booking_details = (
            f"Booking Summary:\n"
            f"Sport: {context.user_data['sport'].title()}\n"
            f"Date: {context.user_data['date']}\n"
            f"Time: {context.user_data['time']}\n"
            f"Player 1 (You): {context.user_data['user_id']}\n"
            f"Player 2: {context.user_data['player2_nif']}"
        )

        # Add padel-specific players if applicable
        if context.user_data['sport'] == 'padel':
            booking_details += f"\nPlayer 3: {context.user_data['player3_nif']}"
            booking_details += f"\nPlayer 4: {context.user_data['player4_nif']}"

        # Send confirmation message
        await update.message.reply_text(
            f"{booking_details}\n\nYour booking has been confirmed! ✅"  # todo mention it is schedule for booking and the hour
        )
        
        return ConversationHandler.END

    def run(self):
        """Run the bot"""
        application = Application.builder().token(CONFIG["bot"].TOKEN).build()
        
        # Update conversation handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("book", self.book)],
            states={
                SELECTING_SPORT: [
                    CallbackQueryHandler(self.select_date, pattern="^sport_")
                ],
                SELECTING_DATE: [
                    CallbackQueryHandler(self.select_time, pattern="^date_")
                ],
                SELECTING_TIME: [
                    CallbackQueryHandler(self.select_preference, pattern="^time_")
                ],
                SELECTING_PREFERENCE: [
                    CallbackQueryHandler(self.select_preference, pattern="^pref_")
                ],
                ENTERING_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_id)
                ],
                ENTERING_PASSWORD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_password)
                ],
                ENTERING_PLAYER2: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_player2)
                ],
                ENTERING_PLAYER3: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_player3)
                ],
                ENTERING_PLAYER4: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.collect_player4)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(conv_handler)
        
        # Start the bot
        application.run_polling()

if __name__ == "__main__":
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    bot = TennisBookingBot()
    bot.run() 