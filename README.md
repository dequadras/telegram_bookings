todo change schedule.json to include real hours

```bash
sudo nano /etc/systemd/system/polo-bookings.service
sudo nano /etc/systemd/system/polo-bookings.timer

# Reload systemd to recognize the new files
sudo systemctl daemon-reload

# Enable both the service and timer
sudo systemctl enable polo-bookings.service
sudo systemctl enable polo-bookings.timer

# Start the timer
sudo systemctl start polo-bookings.timer

# Verify it's working
sudo systemctl list-timers --all | grep polo

sudo systemctl status polo-bookings.timer

# view logs
sudo journalctl -u polo-bookings.service -f
sudo journalctl -u telegram_bookings_bot.service -f

```

/etc/systemd/system/telegram_bookings_bot.service
```
[Unit]
Description=Your Tennis Bot Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/telegram_bookings
Environment=PYTHONPATH=/root/telegram_bookings
ExecStart=/root/telegram_bookings/venv/bin/python3 src/bot.py
StandardOutput=append:/var/log/polo-bot.log
StandardError=append:/var/log/polo-bot.log
Restart=always

[Install]
WantedBy=multi-user.target
```

/etc/systemd/system/polo-bookings.service
```
[Unit]
Description=RC Polo Booking Service
After=network.target

[Service]
Type=oneshot
User=root
WorkingDirectory=/root/telegram_bookings
Environment=PYTHONPATH=/root/telegram_bookings
ExecStart=/root/telegram_bookings/venv/bin/python /root/telegram_bookings/src/run_bookings.py --is_premium true
StandardOutput=append:/var/log/polo-bookings.log
StandardError=append:/var/log/polo-bookings.log

[Install]
WantedBy=multi-user.target
```

/etc/systemd/system/polo-bookings.timer
````
[Unit]
Description=Run RC Polo bookings daily at 6.59am Madrid time

[Timer]
OnCalendar=*-*-* 06:59:00 Europe/Madrid
Persistent=true
AccuracySec=1s

[Install]
WantedBy=timers.target
```


/etc/systemd/system/polo-bookings-free.service
```
[Unit]
Description=RC Polo Booking Service
After=network.target

[Service]
Type=oneshot
User=root
WorkingDirectory=/root/telegram_bookings
Environment=PYTHONPATH=/root/telegram_bookings
ExecStart=/root/telegram_bookings/venv/bin/python /root/telegram_bookings/src/run_bookings.py --is_premium false
StandardOutput=append:/var/log/polo-bookings-free.log
StandardError=append:/var/log/polo-bookings-free.log

[Install]
WantedBy=multi-user.target
```

/etc/systemd/system/polo-bookings-free.timer
````
[Unit]
Description=Run RC Polo bookings daily at 8am Madrid time

[Timer]
OnCalendar=*-*-* 08:00:00 Europe/Madrid
Persistent=true
AccuracySec=1s

[Install]
WantedBy=timers.target
```

Restart
```
# Restart the Telegram bot service
sudo systemctl restart telegram_bookings_bot.service
sudo systemctl restart polo-bookings.timer
sudo systemctl restart polo-bookings.service
sudo systemctl restart polo-bookings-free.timer
sudo systemctl restart polo-bookings-free.service

# Verify everything is running correctly
sudo systemctl status telegram_bookings_bot.service
sudo systemctl status polo-bookings.timer
sudo systemctl status polo-bookings.service
sudo systemctl status polo-bookings-free.timer
sudo systemctl status polo-bookings-free.service
```


Test de carga
```sql
INSERT INTO users (telegram_id, username, password, first_name, booking_credits, created_at)
VALUES
    (10, '46152627E', 'Lucas1994', 'Ldq', 5, CURRENT_TIMESTAMP),
    (11, '21775603P', 'Roman2003', 'Rdq', 5, CURRENT_TIMESTAMP);

INSERT INTO bookings (telegram_id, booking_date, booking_time, status, sport, player_nifs, is_premium)
VALUES
    (10, '2025-01-18', '14:00', 'pending', 'padel', '["46151293E", "21775603P", "60432112A"]', 1),
    (11, '2025-01-18', '15:00', 'pending', 'padel', '["46151293E", "46152627E", "60432112A"]', 1),
    (249843154, '2025-01-18', '15:00', 'pending', 'padel', '["60432112A", "60105994W", "46152627E"]', 1),
    (10, '2025-01-18', '14:00', 'pending', 'padel', '["46151293E", "21775603P", "60432112A"]', 0),
    (11, '2025-01-18', '15:00', 'pending', 'padel', '["46151293E", "46152627E", "60432112A"]', 0),
    (249843154, '2025-01-18', '15:00', 'pending', 'padel', '["60432112A", "60105994W", "46152627E"]', 0);

DELETE FROM users WHERE telegram_id in (10, 11);
DELETE FROM bookings WHERE telegram_id in (10, 11);
```
