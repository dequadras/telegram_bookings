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
ExecStart=/root/telegram_bookings/venv/bin/python /root/telegram_bookings/src/run_bookings.py
StandardOutput=append:/var/log/polo-bookings.log
StandardError=append:/var/log/polo-bookings.log

[Install]
WantedBy=multi-user.target
```

Restart
```
# Restart the Telegram bot service
sudo systemctl restart telegram_bookings_bot.service
sudo systemctl restart polo-bookings.timer
sudo systemctl restart polo-bookings.service

# Verify everything is running correctly
sudo systemctl status telegram_bookings_bot.service
sudo systemctl status polo-bookings.timer
sudo systemctl status polo-bookings.service
```
