import argparse
import asyncio
import logging

from booking import handle_many_bookings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

if __name__ == "__main__":
    # Add argument parser
    parser = argparse.ArgumentParser(description="Run bookings processor")
    parser.add_argument(
        "--is_premium",
        type=str,
        required=True,
        choices=["true", "false"],
        help="Whether to process premium or free bookings",
    )

    args = parser.parse_args()
    is_premium = args.is_premium.lower() == "true"

    try:
        logging.info(f"Starting {'premium' if is_premium else 'free'} booking process...")
        asyncio.run(handle_many_bookings(test=False, is_premium=is_premium))
        logging.info("Booking process completed successfully")
    except Exception as e:
        logging.error(f"Booking failed with exception: {str(e)}", exc_info=True)
