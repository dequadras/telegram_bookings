import logging
import sqlite3
from typing import Dict, List, Optional


class DatabaseManager:
    def __init__(self, db_path: str = "bookings.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """Initialize the database with schema"""
        try:
            with open("src/schema.sql", "r") as f:
                sql_script = f.read()

            with self.get_connection() as conn:
                conn.executescript(sql_script)
                conn.commit()
        except Exception as e:
            logging.error(f"Database initialization failed: {e}")
            raise

    def add_user(
        self, telegram_id: int, username: str, password: str = None, first_name: str = "", last_name: str = ""
    ) -> None:
        """
        Add or update a user in the database
        """
        query = """
            INSERT INTO users (telegram_id, username, password, first_name, last_name)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = COALESCE(NULLIF(?, ''), username),
                password = COALESCE(NULLIF(?, ''), password),
                first_name = COALESCE(NULLIF(?, ''), first_name),
                last_name = COALESCE(NULLIF(?, ''), last_name)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                query,
                (
                    telegram_id,
                    username,
                    password,
                    first_name,
                    last_name,
                    username,
                    password,
                    first_name,
                    last_name,  # Values for the UPDATE clause
                ),
            )
            conn.commit()

    def create_booking(self, telegram_id: int, booking_date: str, booking_time: str) -> Optional[int]:
        """Create a new booking request"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO bookings (telegram_id, booking_date, booking_time)
                    VALUES (?, ?, ?)
                """,
                    (telegram_id, booking_date, booking_time),
                )
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logging.error(f"Failed to create booking: {e}")
            return None

    def get_pending_bookings(self, is_premium_run: bool) -> List[Dict]:
        """Get pending bookings based on run type"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT b.*, u.subscription_status
                    FROM bookings b
                    JOIN users u ON b.telegram_id = u.telegram_id
                    WHERE b.status = 'pending'
                    AND b.is_premium = ?
                    ORDER BY b.created_at ASC
                    """,
                    (is_premium_run,),
                )
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Failed to get pending bookings: {e}")
            return []

    def add_booking(
        self, telegram_id: int, booking_date: str, booking_time: str, sport: str, player_nifs: str, is_premium: bool
    ) -> None:
        """Add a new booking to the database"""
        query = """
            INSERT INTO bookings (telegram_id, booking_date, booking_time, sport, player_nifs, status, is_premium)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (telegram_id, booking_date, booking_time, sport, player_nifs, is_premium))
            conn.commit()

    def get_user_credits(self, telegram_id: int) -> int:
        """Get available booking credits for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT booking_credits FROM users WHERE telegram_id = ?", (telegram_id,))
            result = cursor.fetchone()
            return result[0] if result else 0

    def deduct_booking_credit(self, telegram_id: int) -> bool:
        """Deduct one booking credit from user. Returns False if no credits available."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE users
                SET booking_credits = booking_credits - 1
                WHERE telegram_id = ? AND booking_credits > 0
                RETURNING booking_credits
                """,
                (telegram_id,),
            )
            result = cursor.fetchone()
            conn.commit()
            return result is not None

    def add_booking_credits(self, telegram_id: int, amount: int):
        """Add booking credits to a user's account"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE users
                SET booking_credits = booking_credits + ?
                WHERE telegram_id = ?
                """,
                (amount, telegram_id),
            )
            conn.commit()

    def refund_booking_credit(self, telegram_id: int):
        """Refund one booking credit to a user's account"""
        self.add_booking_credits(telegram_id, 1)

    def get_user_bookings(self, telegram_id: int) -> list:
        """Get all bookings for a user"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, sport, booking_date, booking_time, player_nifs, status
                FROM bookings
                WHERE telegram_id = ?
                ORDER BY booking_date DESC, booking_time DESC
                """,
                (telegram_id,),
            )
            bookings = cursor.fetchall()

        # Convert to list of dictionaries with named keys
        return [
            {
                "id": row[0],
                "sport": row[1],
                "booking_date": row[2],
                "booking_time": row[3],
                "player_nifs": row[4],
                "status": row[5],
            }
            for row in bookings
        ]

    def get_user_credentials(self, telegram_id: int) -> Optional[Dict]:
        """Get user's stored credentials"""
        query = """
            SELECT username, password
            FROM users
            WHERE telegram_id = ?
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (telegram_id,))
            result = cursor.fetchone()
            if result:
                return {"username": result[0], "password": result[1]}
            return None

    def add_player(self, nif: str, name: str) -> None:
        """
        Add or update a player in the database
        """
        query = """
            INSERT INTO players (nif, name)
            VALUES (?, ?)
            ON CONFLICT(nif) DO UPDATE SET
                name = EXCLUDED.name,
                updated_at = CURRENT_TIMESTAMP
        """
        if name:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (nif, name))
                conn.commit()
        else:
            logging.warning(f"No name provided for player {nif}")

    def get_frequent_partners(self, telegram_id: int, limit: int = 5) -> List[Dict]:
        """
        Get the most frequent playing partners for a user
        """
        query = """
            SELECT partner_name, partner_nif, booking_count
            FROM book_count
            WHERE booker_nif = (SELECT username FROM users WHERE telegram_id = ?)
            ORDER BY booking_count DESC
            LIMIT ?
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (telegram_id, limit))
            return [{"name": row[0], "nif": row[1], "count": row[2]} for row in cursor.fetchall()]

    def cancel_booking(self, booking_id: int, user_id: int) -> bool:
        """Cancel a booking and return True if successful"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Verify the booking belongs to the user and is pending
            cursor.execute(
                """
                UPDATE bookings
                SET status = 'cancelled'
                WHERE id = ? AND telegram_id = ? AND status = 'pending'
                """,
                (booking_id, user_id),
            )
            return cursor.rowcount > 0

    def add_booking_credit(self, telegram_id: int, credits: int) -> bool:
        """Add booking credits to a user's account"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET booking_credits = booking_credits + ? WHERE telegram_id = ?", (credits, telegram_id)
            )
            return True

    def update_user_credentials(self, telegram_id: int, username: str, password: str) -> bool:
        """Update user's credentials in the database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE users
                    SET username = ?, password = ?
                    WHERE telegram_id = ?
                    """,
                    (username, password, telegram_id),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Failed to update user credentials: {e}")
            return False

    def execute_query(self, query: str, params: tuple = None):
        """Execute a query with optional parameters"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor

    def get_conversation_history(self, telegram_id: int, limit: int = 100):
        """Retrieve conversation history for a user"""
        query = """
        SELECT message_type, message_text, timestamp
        FROM conversation_logs
        WHERE telegram_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (telegram_id, limit))
            return cursor.fetchall()

    def get_user(self, telegram_id: int) -> Optional[Dict]:
        """
        Retrieve a user's details from the database.

        Args:
            telegram_id (int): The Telegram ID of the user.

        Returns:
            Optional[Dict]: A dictionary with user details if found, else None.
        """
        query = """
            SELECT telegram_id, username, password, first_name, last_name, booking_credits
            FROM users
            WHERE telegram_id = ?
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (telegram_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "telegram_id": row[0],
                        "username": row[1],
                        "password": row[2],
                        "first_name": row[3],
                        "last_name": row[4],
                        "booking_credits": row[5],
                    }
                return None
        except Exception as e:
            logging.error(f"Failed to retrieve user {telegram_id}: {e}")
            return None
