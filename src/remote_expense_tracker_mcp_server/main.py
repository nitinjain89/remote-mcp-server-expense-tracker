from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
import os
import psycopg
from psycopg.rows import dict_row

# Environment variable se Supabase URL uthayega..
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set!")

CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

mcp = FastMCP("ExpenseTracker")

def get_db_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def get_authenticated_user() -> str:
    """Request ke Authorization header se API key nikal kar verified user_id return karta hai."""
    headers = get_http_headers()
    auth_header = headers.get("x-api-key", "")

    if not auth_header.startswith("Bearer "):
        raise ValueError(
            "Unauthorized: Missing X-API-Key header."
        " 'Bearer <API_KEY>'."
        )

    api_key = auth_header.replace("Bearer ", "").strip()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users WHERE api_key = %s", (api_key,))
            user = cur.fetchone()
            if not user:
                raise ValueError("Unauthorized: Invalid API Key.")
            return user["user_id"]

@mcp.tool()
def add_expense(
    date: str, amount: float, category: str, subcategory: str = "", note: str = ""
) -> dict:
  """Add a new expense entry to the database (date format: YYYY-MM-DD)."""
  user_id = get_authenticated_user()

  with get_db_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(
          """
                INSERT INTO expenses(user_id, date, amount, category, subcategory, note) 
                VALUES (%s, %s, %s, %s, %s, %s) 
                RETURNING id
                """,
          (user_id, date, amount, category, subcategory, note),
      )
      row = cur.fetchone()
      if not row:
        raise RuntimeError("Failed to retrieve inserted expense ID.")
      return {"status": "ok", "id": row["id"], "user": user_id}

@mcp.tool()
def list_expenses(start_date: str, end_date: str) -> list[dict]:
  """List all expense entries for the logged-in user within a date range. (Dates must be in YYYY-MM-DD format)."""
  user_id = get_authenticated_user()

  with get_db_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(
          """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE user_id = %s AND date BETWEEN %s AND %s
                ORDER BY date ASC, id ASC
                """,
          (user_id, start_date, end_date),
      )
      return cur.fetchall()


@mcp.tool()
def update_expense(
    expense_id: int,
    date: str | None = None,
    amount: float | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    note: str | None = None,
) -> dict:
  """Update one or more fields of an existing expense by its ID."""
  user_id = get_authenticated_user()

  fields = []
  params = []

  if date is not None:
    fields.append("date = %s")
    params.append(date)
  if amount is not None:
    fields.append("amount = %s")
    params.append(amount)
  if category is not None:
    fields.append("category = %s")
    params.append(category)
  if subcategory is not None:
    fields.append("subcategory = %s")
    params.append(subcategory)
  if note is not None:
    fields.append("note = %s")
    params.append(note)

  if not fields:
    return {"status": "error", "message": "No fields provided to update."}

  # Security: expense_id ke saath user_id match hona zaroori hai
  params.extend([expense_id, user_id])
  query = (
      f"UPDATE expenses SET {', '.join(fields)} WHERE id = %s AND user_id = %s"
  )

  with get_db_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(query, params)
      if cur.rowcount == 0:
        return {
            "status": "error",
            "message": f"Expense ID {expense_id} not found or access denied.",
        }
      return {"status": "ok", "updated_id": expense_id}


@mcp.tool()
def delete_expense(expense_id: int) -> dict:
  """Delete an expense entry from the database by its ID."""
  user_id = get_authenticated_user()

  with get_db_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(
          "DELETE FROM expenses WHERE id = %s AND user_id = %s",
          (expense_id, user_id),
      )
      if cur.rowcount == 0:
        return {
            "status": "error",
            "message": f"Expense ID {expense_id} not found or access denied.",
        }
      return {"status": "ok", "deleted_id": expense_id}


@mcp.tool()
def summarize(
    start_date: str, end_date: str, category: str | None = None
) -> list[dict]:
  """Summarizes expenses by category within an inclusive date range. (Dates must be in YYYY-MM-DD format)."""
  user_id = get_authenticated_user()

  query = """
        SELECT category, SUM(amount) AS total_amount
        FROM expenses
        WHERE user_id = %s AND date BETWEEN %s AND %s
    """
  params: list = [user_id, start_date, end_date]

  if category:
    query += " AND category = %s"
    params.append(category)

  query += " GROUP BY category ORDER BY category ASC"

  with get_db_connection() as conn:
    with conn.cursor() as cur:
      cur.execute(query, params)
      return cur.fetchall()


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
      f"Analyze my expenses for {month} (use start_date='{month}-01' and"
      f" end_date='{month}-31'). Call the `summarize` and `list_expenses` tools"
      " to inspect my spending. Compare my total spending against my monthly"
      f" budget of ₹{budget_limit:.2f}, highlight the top spending categories,"
      " and give 3 actionable tips to save money next month."
  )

if __name__ == "__main__":
  mcp.run(transport="http", host="0.0.0.0", port=8000)