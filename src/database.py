import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
import logging

class DatabaseManager:
    def __init__(self, db_path: str = "tennis_bookings.db"):
        self.db_path = db_path
        self.init_db()
        
    def get_connection(self):
        return sqlite3.connect(self.db_path)
        
    def init_db(self):
        """Initialize the database with schema"""
        try:
            with open('src/schema.sql', 'r') as f:
                sql_script = f.read()
                
            with self.get_connection() as conn:
                conn.executescript(sql_script)
                conn.commit()
        except Exception as e:
            logging.error(f"Database initialization failed: {e}")
            raise
    
    def add_user(self, telegram_id: int, username: str, first_name: str, last_name: str) -> bool:
        """Add a new user to the database"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO users (telegram_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                """, (telegram_id, username, first_name, last_name))
                conn.commit()
                return True
        except Exception as e:
            logging.error(f"Failed to add user: {e}")
            return False
            
    def create_booking(self, telegram_id: int, booking_date: str, booking_time: str) -> Optional[int]:
        """Create a new booking request"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO bookings (telegram_id, booking_date, booking_time)
                    VALUES (?, ?, ?)
                """, (telegram_id, booking_date, booking_time))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logging.error(f"Failed to create booking: {e}")
            return None
            
    def get_pending_bookings(self) -> List[Dict]:
        """Get all pending bookings for processing"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT b.*, u.subscription_status 
                    FROM bookings b
                    JOIN users u ON b.telegram_id = u.telegram_id
                    WHERE b.status = 'pending'
                    ORDER BY 
                        CASE u.subscription_status 
                            WHEN 'paid' THEN 1 
                            ELSE 2 
                        END,
                        b.created_at ASC
                """)
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Failed to get pending bookings: {e}")
            return [] 