-- Users table
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    password TEXT,
    first_name TEXT,
    last_name TEXT,
    subscription_status TEXT DEFAULT 'free' CHECK (subscription_status IN ('free', 'paid')),
    subscription_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bookings table
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,
    booking_date DATE,
    booking_time TIME,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP,
    sport TEXT,
    player_nifs TEXT,  -- Store as JSON array
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

-- Payments table
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,
    stripe_payment_id TEXT,
    amount DECIMAL(10,2),
    status TEXT,
    payment_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

-- Missing indexes for frequently queried columns
CREATE INDEX IF NOT EXISTS idx_bookings_status_date ON bookings(status, booking_date);
CREATE INDEX IF NOT EXISTS idx_bookings_telegram_id ON bookings(telegram_id);
