import asyncio
from booking import handle_many_bookings

if __name__ == "__main__":
    asyncio.run(handle_many_bookings(test=True)) 

# todo log with time and info