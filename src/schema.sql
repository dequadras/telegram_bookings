-- Users table
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    password TEXT,
    first_name TEXT,
    last_name TEXT,
    booking_credits INTEGER DEFAULT 5,  -- Start with 5 free bookings
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bookings table
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,
    booking_date DATE,
    booking_time TIME,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'cancelled')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP,
    sport TEXT,
    player_nifs TEXT,  -- Store as JSON array
    is_premium BOOLEAN NOT NULL,
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

-- Players table to store player information
CREATE TABLE IF NOT EXISTS players (
    nif TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    message_type TEXT NOT NULL,
    message_text TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
);

-- Create a trigger to update the updated_at timestamp
CREATE TRIGGER IF NOT EXISTS update_players_timestamp
AFTER UPDATE ON players
BEGIN
    UPDATE players SET updated_at = CURRENT_TIMESTAMP WHERE nif = NEW.nif;
END;

-- Create a view for booking counts between players
CREATE VIEW IF NOT EXISTS book_count AS
WITH RECURSIVE
-- First, split the JSON arrays into individual rows
split_players AS (
    SELECT
        b.telegram_id as booker_id,
        json_each.value as player_nif
    FROM bookings b
    CROSS JOIN json_each(b.player_nifs)
),
-- Then count the occurrences of each pair
player_pairs AS (
    SELECT
        u.username as booker_nif,
        sp.player_nif as partner_nif,
        COUNT(*) as booking_count
    FROM split_players sp
    JOIN users u ON sp.booker_id = u.telegram_id
    GROUP BY u.username, sp.player_nif
)
SELECT
    pp.booker_nif,
    p.name as partner_name,
    pp.partner_nif,
    pp.booking_count
FROM player_pairs pp
JOIN players p ON pp.partner_nif = p.nif
WHERE pp.booker_nif != pp.partner_nif
ORDER BY pp.booking_count DESC;

-- Missing indexes for frequently queried columns
CREATE INDEX IF NOT EXISTS idx_bookings_status_date ON bookings(status, booking_date);
CREATE INDEX IF NOT EXISTS idx_bookings_telegram_id ON bookings(telegram_id);

-- Missing indexes for new tables
CREATE INDEX IF NOT EXISTS idx_players_name ON players(name);
