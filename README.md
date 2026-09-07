# Supermarket Ops Agent

A Telegram-based AI assistant for managing daily operations of an Indian kirana/supermarket store.

## Features

* 🧾 Create and manage bills
* ➕ Add products to bills
* ✏️ Change item quantity
* ❌ Remove items
* 📦 Check and receive stock
* ⚠️ Low-stock alerts
* 💰 Cash, UPI and Card payments
* 📒 Khata/Credit management
* 🧮 GST calculation with CGST and SGST
* 📄 Generate GST invoice PDF
* 📊 Generate sales analysis PPTX
* 🧠 Save customer preferences
* 🔒 Prevent sales when stock is insufficient
* 💾 Persistent SQLite database

## Technologies

* Python
* Telegram Bot API
* OpenAI/OpenRouter
* SQLite
* ReportLab
* python-pptx
* python-dotenv

## Project Structure

```text
supermarket-agent/
│
├── bot.py
├── supermarket.db
├── requirements.txt
├── .env
├── .gitignore
└── README.md
```

## Installation

Install the required packages:

```bash
python -m pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file:

```text
OPENAI_API_KEY=your_api_key
TELEGRAM_BOT_TOKEN=your_bot_token
```

Do not upload `.env` to GitHub.

## Run the Bot

```bash
python bot.py
```

## Example Commands

Start a bill:

```text
/newbill
```

Add an item:

```text
/item Maggi 2
```

Show the bill:

```text
show my bill
```

Finalize:

```text
finalize with cash
```

Check stock:

```text
show stock of Maggi
```

Receive stock:

```text
Receive 10 Maggi
```

Check low stock:

```text
show low stock
```

Khata:

```text
check Ravi balance
```

Sales analysis:

```text
/analyse
```

## GST Invoice

The system calculates:

* Subtotal
* CGST
* SGST
* Total amount
* Payment method
* Product HSN
* Quantity and unit

A PDF GST invoice is generated after bill finalization.

## Database

SQLite is used for persistent storage of:

* Products
* Stock
* Sales
* Khata balances
* Customer preferences

## Safety

The system checks available stock before finalizing a sale and prevents selling more stock than is available.

## Demo Flow

```text
/newbill
/item Maggi 2
show my bill
finalize with cash
```

The bot generates the bill, calculates GST, updates stock and sends the invoice PDF.
