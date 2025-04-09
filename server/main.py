# First, let's create the database schema and populate it with sample data
import sqlite3
from mcp.server.fastmcp import FastMCP
import os

# Initialize FastMCP server
mcp = FastMCP("company_directory")

# Database setup
DB_PATH = "server/company.db"

# Import the init_db function from the new file
from .db_initializer import init_db

# Initialize database
init_db()

# Helper function for database queries
def execute_query(query, params=()):
    """Execute a query and return the results."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    cursor = conn.cursor()
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return [dict(row) for row in results]

# MCP Tool implementations
@mcp.tool()
async def query_employees(search_term=None, department_id=None, position=None):
    """
    Search for employees based on various criteria.
    
    Args:
        search_term: Search in first_name or last_name (optional)
        department_id: Filter by department ID (optional)
        position: Filter by job position (optional)
    """
    conditions = []
    params = []
    
    if search_term:
        conditions.append("(first_name LIKE ? OR last_name LIKE ?)")
        params.extend([f"%{search_term}%", f"%{search_term}%"])
    
    if department_id:
        conditions.append("department_id = ?")
        params.append(department_id)
    
    if position:
        conditions.append("position LIKE ?")
        params.append(f"%{position}%")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    query = f"""
    SELECT e.id, e.first_name, e.last_name, e.email, e.position, 
           e.hire_date, e.salary, d.name as department_name
    FROM employees e
    JOIN departments d ON e.department_id = d.id
    WHERE {where_clause}
    """
    
    employees = execute_query(query, params)
    
    if not employees:
        return "No employees found matching the criteria."
    
    results = []
    for emp in employees:
        results.append(f"""
ID: {emp['id']}
Name: {emp['first_name']} {emp['last_name']}
Email: {emp['email']}
Position: {emp['position']}
Department: {emp['department_name']}
Hire Date: {emp['hire_date']}
Salary: ${emp['salary']:,.2f}
""")
    
    return "\n---\n".join(results)

@mcp.tool()
async def query_departments(department_id=None):
    """
    Get information about departments.
    
    Args:
        department_id: Specific department ID to query (optional)
    """
    if department_id:
        query = """
        SELECT d.*, COUNT(e.id) as employee_count
        FROM departments d
        LEFT JOIN employees e ON d.id = e.department_id
        WHERE d.id = ?
        GROUP BY d.id
        """
        departments = execute_query(query, (department_id,))
    else:
        query = """
        SELECT d.*, COUNT(e.id) as employee_count
        FROM departments d
        LEFT JOIN employees e ON d.id = e.department_id
        GROUP BY d.id
        """
        departments = execute_query(query)
    
    if not departments:
        return "No departments found."
    
    results = []
    for dept in departments:
        results.append(f"""
ID: {dept['id']}
Name: {dept['name']}
Location: {dept['location']}
Budget: ${dept['budget']:,.2f}
Number of Employees: {dept['employee_count']}
""")
    
    return "\n---\n".join(results)

@mcp.tool()
async def query_projects(department_id=None, active_only=False):
    """
    Get information about projects.
    
    Args:
        department_id: Filter by department ID (optional)
        active_only: If True, show only active projects (optional)
    """
    conditions = []
    params = []
    
    if department_id:
        conditions.append("p.department_id = ?")
        params.append(department_id)
    
    if active_only:
        conditions.append("(p.end_date >= date('now') OR p.end_date IS NULL)")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    query = f"""
    SELECT p.*, d.name as department_name
    FROM projects p
    JOIN departments d ON p.department_id = d.id
    WHERE {where_clause}
    """
    
    projects = execute_query(query, params)
    
    if not projects:
        return "No projects found matching the criteria."
    
    results = []
    for proj in projects:
        results.append(f"""
ID: {proj['id']}
Name: {proj['name']}
Description: {proj['description']}
Department: {proj['department_name']}
Timeline: {proj['start_date']} to {proj['end_date']}
Budget: ${proj['budget']:,.2f}
""")
    
    return "\n---\n".join(results)

@mcp.tool()
async def add_employee(first_name, last_name, email, department_id, position, salary, hire_date=None):
    """
    Add a new employee to the database.
    
    Args:
        first_name: Employee's first name
        last_name: Employee's last name
        email: Employee's email address
        department_id: Department ID (must exist in departments table)
        position: Job position/title
        salary: Annual salary
        hire_date: Date of hire (YYYY-MM-DD format), defaults to today if not provided
    """
    import datetime
    
    if hire_date is None:
        hire_date = datetime.date.today().isoformat()
    
    # Validate department exists
    departments = execute_query("SELECT id FROM departments WHERE id = ?", (department_id,))
    if not departments:
        return f"Error: Department ID {department_id} does not exist."
    
    # Check if email already exists
    existing = execute_query("SELECT id FROM employees WHERE email = ?", (email,))
    if existing:
        return f"Error: An employee with email {email} already exists."
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO employees (first_name, last_name, email, hire_date, department_id, position, salary)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (first_name, last_name, email, hire_date, department_id, position, salary))
        
        employee_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return f"Employee added successfully with ID: {employee_id}"
    except Exception as e:
        return f"Error adding employee: {str(e)}"

# Run the server
if __name__ == "__main__":
    mcp.run(transport='stdio')