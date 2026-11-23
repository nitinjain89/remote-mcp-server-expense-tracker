from fastmcp import FastMCP
import os
import sqlite3
import tempfile

# DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")
DB_PATH = os.path.join(tempfile.gettempdir(), "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

mcp = FastMCP("ExpenseTracker")

def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT DEFAULT '',
            note TEXT DEFAULT ''
            )
        """)

init_db()

@mcp.tool()
def add_expense(date: str, amount: float, category: str, subcategory: str="", note: str="") -> dict:
    '''Add a new expense entry to the database'''
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?, ?, ?, ?, ?)",
            (date, amount, category, subcategory, note)
        )
        return {"status": "ok", "id": cur.lastrowid}

@mcp.tool()
def list_expenses(start_date: str, end_date: str) -> list[dict]:
    '''List all expense entries from the database.'''
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(
            """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN ? and ?
            ORDER BY id ASC
            """,
            (start_date, end_date)
            )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
@mcp.tool()
def update_expense(
    expense_id: int,
    date: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    note: str | None = None
) -> dict:
    """Update one or more fields of an existing expense by its ID."""
    fields = []
    params = []

    if date is not None:
        fields.append("date = ?")
        params.append(date)
    if amount is not None:
        fields.append("amount = ?")
        params.append(amount)
    if category is not None:
        fields.append("category = ?")
        params.append(category)
    if subcategory is not None:
        fields.append("subcategory = ?")
        params.append(subcategory)
    if note is not None:
        fields.append("note = ?")
        params.append(note)

    if not fields:
        return {"status": "error", "message": "No fields provided to update."}

    params.append(expense_id)
    query = f"UPDATE expenses SET {', '.join(fields)} WHERE id = ?"

    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute(query, params)
        if cur.rowcount == 0:
            return {"status": "error", "message": f"Expense ID {expense_id} not found."}
        return {"status": "ok", "updated_id": expense_id}

@mcp.tool()
def delete_expense(expense_id: int) -> dict:
    """Delete an expense entry from the database by its ID."""
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        if cur.rowcount == 0:
            return {"status": "error", "message": f"Expense ID {expense_id} not found."}
        return {"status": "ok", "deleted_id": expense_id}
    
@mcp.tool()
def summarize(start_date: str, end_date: str, category: str | None = None) -> list[dict]:
    '''Summarizes expenses by category within an inclusive date range'''
    with sqlite3.connect(DB_PATH) as c:
        query = (
            """
            SELECT category, SUM(amount) AS total_amount
            FROM expenses
            WHERE date BETWEEN ? and ?
            """
        )
        params = [start_date, end_date]

        if category:
            query+= " AND category = ?"
            params.append(category)

        query+= " GROUP BY category ORDER BY category ASC"

        cur = c.execute(query, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

@mcp.resource("expense://categories", mime_type="application/json")
def categories() -> str:
    """Returns available expense categories."""
    if not os.path.exists(CATEGORIES_PATH):
        return '{"categories": ["Food", "Travel", "Bills", "Shopping", "Other"]}'
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return f.read()

@mcp.prompt()
def analyze_monthly_spending(month: str, budget_limit: float) -> str:
    """Generate a structured prompt to analyze monthly expenses against a budget."""
    return (
        f"Analyze my expenses for {month} (use start_date='{month}-01' and end_date='{month}-31'). "
        f"Call the `summarize` and `list_expenses` tools to inspect my spending. "
        f"Compare my total spending against my monthly budget of ₹{budget_limit:.2f}, "
        f"highlight the top spending categories, and give 3 actionable tips to save money next month."
    )

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)