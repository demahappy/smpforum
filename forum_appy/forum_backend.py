from flask import Flask, jsonify, request, render_template
from datetime import datetime
import sqlite3
import mariadb
import sys

app = Flask(__name__)

DB_CONFIG = {
    'mariadb': {
        'host': 'localhost',
        'port': 3306,
        'user': 'forum_user',
        'password': 'password',
        'database': 'simple_forum'
    },
    'sqlite': {
        'database': 'forum.db'
    }
}

in_memory_posts = []

class DBConnector:
    def __init__(self, db_type):
        self.db_type = db_type
    
    def connect(self):
        try:
            if self.db_type == 'mariadb':
                conn = mariadb.connect(**DB_CONFIG['mariadb'])
            elif self.db_type == 'sqlite':
                conn = sqlite3.connect(DB_CONFIG['sqlite']['database'])
            return conn
        except (mariadb.Error, sqlite3.Error) as e:
            print(f"Connection error: {e}")
            return None

def init_dbs():
    try:
        conn = mariadb.connect(
            host=DB_CONFIG['mariadb']['host'],
            port=DB_CONFIG['mariadb']['port'],
            user=DB_CONFIG['mariadb']['user'],
            password=DB_CONFIG['mariadb']['password']
        )
        conn.cursor().execute("CREATE DATABASE IF NOT EXISTS simple_forum")
        conn.close()
    except mariadb.Error as e:
        print(f"MariaDB init error: {e}")
        return False

    for db_type in ['mariadb', 'sqlite']:
        conn = DBConnector(db_type).connect()
        if not conn: continue
        
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    username VARCHAR(255) UNIQUE NOT NULL
                )
            ''') if db_type == 'mariadb' else cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTO_INCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''') if db_type == 'mariadb' else cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')
            conn.commit()
        except (mariadb.Error, sqlite3.Error) as e:
            print(f"Table creation error: {e}")
            return False
        finally:
            conn.close()
    return True

def sync_posts():
    global in_memory_posts
    for db_type in ['mariadb', 'sqlite']:
        conn = DBConnector(db_type).connect()
        if not conn: continue
        
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT p.id, u.username, p.content, p.created_at FROM posts p JOIN users u ON p.user_id = u.id")
            in_memory_posts = [{
                'id': row[0],
                'author': row[1],
                'content': row[2],
                'timestamp': row[3]
            } for row in cursor.fetchall()]
        finally:
            conn.close()

@app.route('/')
def index():
    return render_template('forum_frontend.html')

@app.route('/api/posts', methods=['GET', 'POST'])
def handle_posts():
    if request.method == 'GET':
        return jsonify({'posts': in_memory_posts})
    
    if request.method == 'POST':
        data = request.get_json()
        if not data.get('username') or not data.get('content'):
            return jsonify({'error': 'Missing data'}), 400
        
        user_id = None
        for db_type in ['mariadb', 'sqlite']:
            conn = DBConnector(db_type).connect()
            if not conn: continue
            
            try:
                cursor = conn.cursor()
                cursor.execute("INSERT IGNORE INTO users (username) VALUES (?)", (data['username'],))
                cursor.execute("SELECT id FROM users WHERE username = ?", (data['username'],))
                user_id = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO posts (user_id, content, created_at) VALUES (?, ?, ?)",
                    (user_id, data['content'][:500], datetime.now())
                )
                conn.commit()
            except (mariadb.Error, sqlite3.Error) as e:
                print(f"DB error: {e}")
                return jsonify({'error': 'Database operation failed'}), 500
            finally:
                conn.close()
        
        sync_posts()
        return jsonify({'status': 'success'})

@app.route('/api/posts/<int:post_id>', methods=['PUT', 'DELETE'])
def modify_post(post_id):
    if request.method == 'PUT':
        new_content = request.get_json().get('content')
        if not new_content:
            return jsonify({'error': 'Content required'}), 400
        
        success = False
        for db_type in ['mariadb', 'sqlite']:
            conn = DBConnector(db_type).connect()
            if not conn: continue
            
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE posts SET content = ? WHERE id = ?",
                    (new_content[:500], post_id))
                conn.commit()
                success = True
            except (mariadb.Error, sqlite3.Error):
                continue
            finally:
                conn.close()
        
        if success:
            sync_posts()
            return jsonify({'status': 'success'})
        return jsonify({'error': 'Update failed'}), 500
    
    if request.method == 'DELETE':
        success = False
        for db_type in ['mariadb', 'sqlite']:
            conn = DBConnector(db_type).connect()
            if not conn: continue
            
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))
                conn.commit()
                success = True
            except (mariadb.Error, sqlite3.Error):
                continue
            finally:
                conn.close()
        
        if success:
            sync_posts()
            return jsonify({'status': 'success'})
        return jsonify({'error': 'Deletion failed'}), 500

if __name__ == '__main__':
    if init_dbs():
        sync_posts()
        app.run(debug=False)
    else:
        sys.exit(1)