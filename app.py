from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import sqlite3
from pathlib import Path
from datetime import date, datetime
import pandas as pd
import io

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "stockwise.db"
DB_PATH.parent.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-deployment"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            address TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sku TEXT NOT NULL UNIQUE,
            category TEXT DEFAULT '',
            supplier_id INTEGER,
            cost_price REAL NOT NULL DEFAULT 0 CHECK(cost_price >= 0),
            selling_price REAL NOT NULL DEFAULT 0 CHECK(selling_price >= 0),
            quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
            reorder_level INTEGER NOT NULL DEFAULT 5 CHECK(reorder_level >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL CHECK(movement_type IN ('IN','OUT')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price REAL NOT NULL DEFAULT 0,
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        );
        """)
        # Add initial opening stock to history for any products already in the database.
        db.commit()


@app.template_filter("money")
def money(value):
    return f"₹{float(value or 0):,.2f}"


@app.route("/")
def dashboard():
    with get_db() as db:
        totals = {
            "products": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "suppliers": db.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0],
            "low_stock": db.execute("SELECT COUNT(*) FROM products WHERE quantity <= reorder_level").fetchone()[0],
            "inventory_value": db.execute("SELECT COALESCE(SUM(quantity * cost_price),0) FROM products").fetchone()[0],
        }
        recent = db.execute("""
            SELECT m.*, p.name AS product_name, p.sku
            FROM stock_movements m JOIN products p ON p.id=m.product_id
            ORDER BY m.id DESC LIMIT 8
        """).fetchall()
        low_products = db.execute("""
            SELECT p.*, s.name AS supplier_name FROM products p
            LEFT JOIN suppliers s ON s.id=p.supplier_id
            WHERE p.quantity <= p.reorder_level ORDER BY p.quantity ASC LIMIT 8
        """).fetchall()
    return render_template("dashboard.html", totals=totals, recent=recent, low_products=low_products)


@app.route("/products")
def products():
    search = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    with get_db() as db:
        sql = """SELECT p.*, s.name AS supplier_name FROM products p
                 LEFT JOIN suppliers s ON s.id=p.supplier_id WHERE 1=1"""
        args = []
        if search:
            sql += " AND (p.name LIKE ? OR p.sku LIKE ? OR p.category LIKE ?)"
            args.extend([f"%{search}%"] * 3)
        if category:
            sql += " AND p.category = ?"
            args.append(category)
        sql += " ORDER BY p.name COLLATE NOCASE"
        items = db.execute(sql, args).fetchall()
        categories = [r["category"] for r in db.execute(
            "SELECT DISTINCT category FROM products WHERE category <> '' ORDER BY category"
        ).fetchall()]
    return render_template("products.html", products=items, q=search, category=category, categories=categories)


@app.route("/products/new", methods=["GET", "POST"])
def product_new():
    with get_db() as db:
        suppliers = db.execute("SELECT id, name FROM suppliers ORDER BY name").fetchall()
    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            sku = request.form["sku"].strip().upper()
            quantity = int(request.form.get("quantity", 0))
            reorder = int(request.form.get("reorder_level", 5))
            cost = float(request.form.get("cost_price", 0))
            selling = float(request.form.get("selling_price", 0))
            supplier_id = request.form.get("supplier_id") or None
            if not name or not sku:
                raise ValueError("Product name and SKU are required.")
            if min(quantity, reorder) < 0 or min(cost, selling) < 0:
                raise ValueError("Quantity, reorder level and prices cannot be negative.")
            with get_db() as db:
                cur = db.execute("""INSERT INTO products
                    (name, sku, category, supplier_id, cost_price, selling_price, quantity, reorder_level)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (name, sku, request.form.get("category", "").strip(), supplier_id, cost, selling, quantity, reorder))
                if quantity:
                    db.execute("""INSERT INTO stock_movements
                        (product_id, movement_type, quantity, unit_price, note)
                        VALUES (?, 'IN', ?, ?, 'Opening stock')""", (cur.lastrowid, quantity, cost))
            flash("Product added successfully.", "success")
            return redirect(url_for("products"))
        except sqlite3.IntegrityError:
            flash("That SKU already exists. Please use a unique SKU.", "error")
        except (ValueError, TypeError) as exc:
            flash(str(exc) or "Please check the values entered.", "error")
    return render_template("product_form.html", product=None, suppliers=suppliers)


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
def product_edit(product_id):
    with get_db() as db:
        product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        suppliers = db.execute("SELECT id, name FROM suppliers ORDER BY name").fetchall()
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))
    if request.method == "POST":
        try:
            values = (
                request.form["name"].strip(), request.form["sku"].strip().upper(),
                request.form.get("category", "").strip(), request.form.get("supplier_id") or None,
                float(request.form.get("cost_price", 0)), float(request.form.get("selling_price", 0)),
                int(request.form.get("reorder_level", 5)), product_id
            )
            if not values[0] or not values[1] or min(values[4], values[5], values[6]) < 0:
                raise ValueError("Please enter valid non-negative values.")
            with get_db() as db:
                db.execute("""UPDATE products SET name=?, sku=?, category=?, supplier_id=?,
                    cost_price=?, selling_price=?, reorder_level=? WHERE id=?""", values)
            flash("Product updated. Use Stock In/Out to change quantity so history stays accurate.", "success")
            return redirect(url_for("products"))
        except sqlite3.IntegrityError:
            flash("That SKU already exists.", "error")
        except (ValueError, TypeError) as exc:
            flash(str(exc) or "Please check the values entered.", "error")
    return render_template("product_form.html", product=product, suppliers=suppliers)


@app.post("/products/<int:product_id>/delete")
def product_delete(product_id):
    with get_db() as db:
        db.execute("DELETE FROM products WHERE id=?", (product_id,))
    flash("Product deleted.", "success")
    return redirect(url_for("products"))


@app.route("/suppliers")
def suppliers():
    with get_db() as db:
        rows = db.execute("""SELECT s.*, COUNT(p.id) AS product_count
            FROM suppliers s LEFT JOIN products p ON p.supplier_id=s.id
            GROUP BY s.id ORDER BY s.name""").fetchall()
    return render_template("suppliers.html", suppliers=rows)


@app.route("/suppliers/new", methods=["GET", "POST"])
def supplier_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Supplier name is required.", "error")
        else:
            with get_db() as db:
                db.execute("INSERT INTO suppliers (name, phone, email, address) VALUES (?, ?, ?, ?)",
                    (name, request.form.get("phone", "").strip(), request.form.get("email", "").strip(),
                     request.form.get("address", "").strip()))
            flash("Supplier added.", "success")
            return redirect(url_for("suppliers"))
    return render_template("supplier_form.html")


@app.post("/suppliers/<int:supplier_id>/delete")
def supplier_delete(supplier_id):
    with get_db() as db:
        db.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
    flash("Supplier deleted. Products linked to it remain in your catalogue.", "success")
    return redirect(url_for("suppliers"))


@app.route("/stock", methods=["GET", "POST"])
def stock():
    if request.method == "POST":
        try:
            product_id = int(request.form["product_id"])
            quantity = int(request.form["quantity"])
            movement_type = request.form["movement_type"]
            unit_price = float(request.form.get("unit_price", 0) or 0)
            note = request.form.get("note", "").strip()
            if movement_type not in ("IN", "OUT") or quantity <= 0 or unit_price < 0:
                raise ValueError("Choose a movement type and enter a positive quantity and non-negative price.")
            with get_db() as db:
                product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
                if not product:
                    raise ValueError("Choose a valid product.")
                if movement_type == "OUT" and quantity > product["quantity"]:
                    raise ValueError(f"Not enough stock. Available quantity: {product['quantity']}.")
                delta = quantity if movement_type == "IN" else -quantity
                db.execute("UPDATE products SET quantity = quantity + ? WHERE id=?", (delta, product_id))
                price = unit_price if unit_price else (product["cost_price"] if movement_type == "IN" else product["selling_price"])
                db.execute("""INSERT INTO stock_movements
                    (product_id, movement_type, quantity, unit_price, note)
                    VALUES (?, ?, ?, ?, ?)""", (product_id, movement_type, quantity, price, note))
            flash(f"Stock {movement_type.lower()} recorded successfully.", "success")
            return redirect(url_for("stock"))
        except (ValueError, TypeError) as exc:
            flash(str(exc) or "Please check the values entered.", "error")
    with get_db() as db:
        products_list = db.execute("SELECT id, name, sku, quantity, cost_price, selling_price FROM products ORDER BY name").fetchall()
        history = db.execute("""SELECT m.*, p.name AS product_name, p.sku
            FROM stock_movements m JOIN products p ON p.id=m.product_id
            ORDER BY m.id DESC LIMIT 100""").fetchall()
    return render_template("stock.html", products=products_list, history=history)


@app.route("/reports")
def reports():
    with get_db() as db:
        stock_rows = db.execute("""SELECT p.name, p.sku, p.category, p.quantity, p.reorder_level,
            p.cost_price, p.selling_price, (p.quantity*p.cost_price) AS inventory_value,
            s.name AS supplier_name FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id
            ORDER BY p.name""").fetchall()
        sales_rows = db.execute("""SELECT date(m.created_at) AS day, p.name AS product_name,
            p.sku, SUM(m.quantity) AS units_sold, SUM(m.quantity*m.unit_price) AS sales_value
            FROM stock_movements m JOIN products p ON p.id=m.product_id
            WHERE m.movement_type='OUT' GROUP BY date(m.created_at), p.id
            ORDER BY day DESC, product_name""").fetchall()
        totals = {
            "inventory_value": sum(r["inventory_value"] or 0 for r in stock_rows),
            "units_in_stock": sum(r["quantity"] for r in stock_rows),
            "sales_value": sum(r["sales_value"] or 0 for r in sales_rows),
            "units_sold": sum(r["units_sold"] or 0 for r in sales_rows),
        }
    return render_template("reports.html", stock_rows=stock_rows, sales_rows=sales_rows, totals=totals)


@app.get("/reports/inventory.csv")
def inventory_csv():
    with get_db() as db:
        rows = db.execute("""SELECT p.name, p.sku, p.category, p.quantity, p.reorder_level,
            p.cost_price, p.selling_price, p.quantity*p.cost_price AS inventory_value,
            s.name AS supplier FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id
            ORDER BY p.name""").fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    return csv_download(df, "stockwise-inventory.csv")


@app.get("/reports/sales.csv")
def sales_csv():
    with get_db() as db:
        rows = db.execute("""SELECT date(m.created_at) AS date, p.name AS product,
            p.sku, SUM(m.quantity) AS units_sold, SUM(m.quantity*m.unit_price) AS sales_value
            FROM stock_movements m JOIN products p ON p.id=m.product_id
            WHERE m.movement_type='OUT' GROUP BY date(m.created_at), p.id
            ORDER BY date DESC, product""").fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    return csv_download(df, "stockwise-sales-report.csv")


def csv_download(df, filename):
    output = io.StringIO()
    df.to_csv(output, index=False)
    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(data, mimetype="text/csv", as_attachment=True, download_name=filename)


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


init_db()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
