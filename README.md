# Caroai Café Control App

A simple internal application for managing sales, inventory, and tables for a café.

## Features

- Table management (open, close, reset)
- Sales recording with multi-currency support (COP, Bolívares, USD, Binance, tarjeta)
- Automatic inventory deduction based on recipes
- Purchase recording for inventory
- Low stock alerts
- Reports (daily, weekly, monthly) - placeholder

## Setup

1. Install Python 3.11+.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up the database and seed initial data:
   ```bash
   python seed_data.py
   ```
4. Run the application:
   ```bash
   python run.py
   ```
5. Open your browser to `http://localhost:5000`.

## Project Structure

```
/app
   /models.py        # SQLAlchemy models
   /database.py      # Database initialization
   /schemas.py       # Validation schemas (placeholder)
   /routes/
       /tables.py    # Table management
       /sales.py     # Sales and pedidos
       /inventory.py # Inventory management
   /utils/
       /currency.py  # Currency conversion functions
       /excel_import.py # Excel parsing (to be completed)
   /templates/       # HTML templates (organized by route)
   /static/          # CSS, JS, images (Bootstrap via CDN)
seed_data.py        # Script to seed initial data
run.py              # Flask entry point
requirements.txt    # Python dependencies
```

## Notes

- The application uses SQLite by default (file `caroai.db` in the root).
- Fiscal invoicing (SENIAT/QUORiON) is out of scope.
- Designed for single-operator use; no authentication system.
- Exchange rates must be manually entered via the database (or modify the seed script).

## License

MIT