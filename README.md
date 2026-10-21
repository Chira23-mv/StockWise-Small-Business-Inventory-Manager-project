# StockWise — Small Business Inventory Manager

StockWise is a Flask + SQLite inventory manager for small shops. It tracks products and suppliers, records stock-in and stock-out movements, highlights low-stock items, and provides inventory/sales reports with CSV export powered by Pandas.

## Features
- Dashboard with product, supplier, low-stock and inventory-value summaries
- Product catalogue with SKU, category, supplier, cost/selling price and reorder level
- Supplier directory
- Stock-in and stock-out transactions with validation against negative stock
- Movement history for audit trail
- Low-stock alerts based on each product's reorder level
- Inventory and sales reports
- Download inventory and sales reports as CSV
- Responsive interface for laptop and mobile screens

## Run on macOS
1. Install Python 3 from https://www.python.org/downloads/ if needed.
2. Extract the ZIP and open the `stockwise` folder in VS Code.
3. In VS Code choose **Terminal → New Terminal**.
4. Run:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   python app.py
   ```

5. Open http://127.0.0.1:5000 in your browser.
6. Stop the server with `Control + C` in the terminal.

The SQLite database is created automatically at `data/stockwise.db`. This folder is ignored by Git so local shop data is not uploaded accidentally.

## Suggested demo workflow
1. Add a supplier under **Suppliers**.
2. Add a product under **Products** and set its opening quantity and reorder level.
3. Open **Stock In / Out** to receive more units or record units sold/removed.
4. Review the low-stock alert on the dashboard.
5. Open **Reports** and export inventory or sales CSV files.

## Notes
- The Sales report estimates sales value using the unit price stored on stock-out transactions. If no price is entered on a transaction, the product's selling price is used.
- Stock-out is treated as a sale for this starter project. For returns, discounts, tax, purchase orders, multi-user access, or accounting-grade reports, extend the data model before relying on it for business accounting.
- This is a local starter application, not a hardened public multi-user service. Before public deployment, add authentication, CSRF protection, secure secret configuration, backups, and production server configuration.
