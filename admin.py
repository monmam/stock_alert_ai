from werkzeug.security import generate_password_hash
import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()
new_hash = generate_password_hash('T0909760663', method='scrypt')
cursor.execute("UPDATE users SET password = ? WHERE email = ?", (new_hash, 'admin'))
conn.commit()
conn.close()
print("Reset password complete!")