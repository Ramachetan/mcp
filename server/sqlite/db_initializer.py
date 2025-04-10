import sqlite3
import os

DB_PATH = "server/company.db"

def init_db():
    """Initialize the database with schema and sample data."""
    if os.path.exists(DB_PATH):
        print(f"Database already exists at {DB_PATH}. Skipping initialization.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
    CREATE TABLE departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        location TEXT,
        budget REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        hire_date TEXT NOT NULL,
        department_id INTEGER NOT NULL,
        position TEXT NOT NULL,
        salary REAL NOT NULL,
        FOREIGN KEY (department_id) REFERENCES departments (id)
    )
    """)

    cursor.execute("""
    CREATE TABLE projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        start_date TEXT NOT NULL,
        end_date TEXT,
        budget REAL,
        department_id INTEGER NOT NULL,
        FOREIGN KEY (department_id) REFERENCES departments (id)
    )
    """)

    # Insert sample data
    cursor.executemany("""
    INSERT INTO departments (name, location, budget) VALUES (?, ?, ?)
    """, [
        ("HR", "New York", 75000),
        ("Engineering", "San Francisco", 300000),
        ("Sales", "Chicago", 150000),
        ("Marketing", "Los Angeles", 120000),
        ("Finance", "Boston", 200000)
    ])

    cursor.executemany("""
    INSERT INTO employees (first_name, last_name, email, hire_date, department_id, position, salary) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        ("John", "Doe", "john.doe@example.com", "2023-01-15", 1, "Manager", 80000),
        ("Jane", "Smith", "jane.smith@example.com", "2023-02-20", 2, "Senior Engineer", 150000),
        ("Alice", "Johnson", "alice.johnson@example.com", "2023-03-10", 3, "Sales Representative", 85000),
        ("Bob", "Brown", "bob.brown@example.com", "2023-04-05", 1, "HR Specialist", 60000),
        ("Charlie", "Davis", "charlie.davis@example.com", "2023-05-01", 2, "Software Engineer", 130000),
        ("Eve", "White", "eve.white@example.com", "2023-06-10", 3, "Sales Manager", 100000),
        ("Rajesh", "Kumar", "rajesh.kumar@example.com", "2023-07-15", 2, "Data Scientist", 140000),
        ("Sonali", "Patel", "sonali.patel@example.com", "2023-08-01", 1, "Recruiter", 75000),
        ("Ravi", "Sharma", "ravi.sharma@example.com", "2023-09-01", 2, "DevOps Engineer", 125000),
        ("Sofia", "Garcia", "sofia.garcia@example.com", "2023-09-15", 3, "Marketing Specialist", 80000),
        ("David", "Lee", "david.lee@example.com", "2023-10-01", 1, "HR Assistant", 55000),
        ("Michael", "Brown", "michael.brown@example.com", "2023-10-15", 2, "Product Manager", 140000),
        ("Emily", "Clark", "emily.clark@example.com", "2023-11-01", 4, "Marketing Coordinator", 70000),
        ("Liam", "Wilson", "liam.wilson@example.com", "2023-12-01", 5, "Financial Analyst", 90000),
        ("Olivia", "Martinez", "olivia.martinez@example.com", "2023-12-15", 5, "Financial Analyst", 95000),
    ])

    cursor.executemany("""
    INSERT INTO projects (name, description, start_date, end_date, budget, department_id) VALUES (?, ?, ?, ?, ?, ?)
    """, [
        ("Project Alpha", "Developing a new product.", "2023-04-01", "2023-12-31", 75000, 2),
        ("Project Beta", "Expanding market reach.", "2023-05-01", None, 50000, 3),
        ("Project Gamma", "Implementing new marketing strategies.", "2023-06-01", "2023-11-30", 60000, 4),
        ("Project Delta", "Financial system upgrade.", "2023-07-01", "2023-12-31", 80000, 5)
    ])

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}.")
    
    init_db()