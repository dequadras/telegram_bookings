import asyncio
import logging

from booking import handle_many_bookings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bookings.log"), logging.StreamHandler()],  # This will also print to console
)

if __name__ == "__main__":
    try:
        logging.info("Starting booking process...")
        asyncio.run(handle_many_bookings(test=False))
        logging.info("Booking process completed successfully")
    except Exception as e:
        logging.error(f"Booking failed with exception: {str(e)}", exc_info=True)
        raise e

# todo log with time and info
