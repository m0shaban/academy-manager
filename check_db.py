import sqlite3

conn = sqlite3.connect('saas.db')
cur = conn.cursor()

# Check tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print("📋 Tables:", tables)

# Check vouchers
cur.execute("SELECT * FROM vouchers LIMIT 5")
vouchers = cur.fetchall()
print("\n🎟️ Vouchers (first 5):", vouchers)

# Check users
cur.execute("SELECT * FROM users")
users = cur.fetchall()
print("\n👥 Users:", users)

conn.close()
