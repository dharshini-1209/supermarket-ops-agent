import json
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from reportlab.pdfgen import canvas
from pptx import Presentation
from openai import OpenAI
from dotenv import load_dotenv
import os
current_bills = {}
load_dotenv()
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENAI_API_KEY")
)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# Create database
conn = sqlite3.connect("supermarket.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    quantity INTEGER,
    cost REAL,
    mrp REAL,
    gst REAL
)
""")
conn.commit()

# Add new columns safely
try:
    cursor.execute("ALTER TABLE products ADD COLUMN unit TEXT DEFAULT 'piece'")
except:
    pass

try:
    cursor.execute("ALTER TABLE products ADD COLUMN reorder_level INTEGER DEFAULT 10")
except:
    pass

try:
    cursor.execute("ALTER TABLE products ADD COLUMN hsn TEXT DEFAULT '0000'")
except:
    pass

conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS khata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer TEXT,
    balance REAL
)
""")

conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    total REAL,
    payment TEXT,
    date TEXT
)
""")

conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS preferences (
    user_id INTEGER,
    key TEXT,
    value TEXT,
    PRIMARY KEY (user_id, key)
)
""")

conn.commit()



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! 🛒 Supermarket Agent is ready!"
    )


async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) != 8:
        await update.message.reply_text(
            "Use: /add Name Quantity Cost MRP GST Unit ReorderLevel HSN"
        )
        return

    name = context.args[0]
    quantity = int(context.args[1])
    cost = float(context.args[2])
    mrp = float(context.args[3])
    gst = float(context.args[4])
    unit = context.args[5].lower()
    reorder_level = int(context.args[6])
    hsn = context.args[7]

    cursor.execute(
        """INSERT INTO products
        (name, quantity, cost, mrp, gst, unit, reorder_level, hsn)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, quantity, cost, mrp, gst, unit, reorder_level, hsn)
    )

    conn.commit()

    await update.message.reply_text(
        name + " added successfully ✅\n"
        + "Unit: " + unit + "\n"
        + "Reorder Level: " + str(reorder_level) + "\n"
        + "HSN: " + hsn
    )
async def stock(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) == 0:
        await update.message.reply_text("Use: /stock ProductName")
        return

    name = " ".join(context.args)

    cursor.execute(
        "SELECT name, quantity, cost, mrp, gst, unit FROM products WHERE name=?",
        (name,)
    )

    product = cursor.fetchone()

    if product is None:
        await update.message.reply_text("Product not found ❌")
        return

    message = (
        "📦 Product: " + product[0] + "\n"
        + "Quantity: " + str(product[1]) + " " + product[5] + "\n"
        + "Cost: ₹" + str(product[2]) + "\n"
        + "MRP: ₹" + str(product[3]) + "\n"
        + "GST: " + str(product[4]) + "%"
    )

    await update.message.reply_text(message)


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text.lower() == "hello":
        await update.message.reply_text("Hello! 😊")

    else:
        await update.message.reply_text(
            "I received: " + text
        )
async def receive_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) < 2:
        await update.message.reply_text(
            "Use: /receive ProductName Quantity"
        )
        return

    name = " ".join(context.args[:-1])
    quantity = int(context.args[-1])

    cursor.execute(
        "SELECT unit FROM products WHERE name=?",
        (name,)
    )

    product = cursor.fetchone()

    if product is None:
        await update.message.reply_text("Product not found ❌")
        return

    cursor.execute(
        "UPDATE products SET quantity = quantity + ? WHERE name=?",
        (quantity, name)
    )

    conn.commit()

    await update.message.reply_text(
        name + " stock received: "
        + str(quantity) + " "
        + product[0]
        + " ✅"
    )


async def natural_bill(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global current_bill

    text = update.message.text.lower()
    words = text.replace(",", "").split()

    if "want" not in text and "buy" not in text:
        return

    cursor.execute(
        "SELECT name, mrp, gst, unit, quantity FROM products"
    )

    products = cursor.fetchall()

    found = False

    for product in products:

        name = product[0].lower()

        if name not in words:
            continue

        quantity = 1

        for i in range(len(words)):

            if words[i] == name:

                # Example: 2 Rice
                if i >= 1:
                    try:
                        quantity = float(words[i - 1])
                    except:
                        quantity = 1

                # Example: 500 g Rice
                if i >= 2:
                    try:
                        if words[i - 1] in ["g", "gram", "grams"]:
                            quantity = float(words[i - 2]) / 1000
                    except:
                        pass

                # Example: 2 litre Milk
                if i >= 2:
                    try:
                        if words[i - 1] in ["litre", "litres", "l"]:
                            quantity = float(words[i - 2])
                    except:
                        pass

        if quantity > product[4]:
            await update.message.reply_text(
                "Not enough stock for " + product[0] + " ❌"
            )
            continue

        current_bill.append({
            "name": product[0],
            "quantity": quantity,
            "mrp": product[1],
            "gst": product[2],
            "unit": product[3]
        })

        await update.message.reply_text(
            product[0] + " × "
            + str(quantity) + " "
            + product[3]
            + " added to bill ✅"
        )

        found = True

    if not found:
        await update.message.reply_text(
            "Product not found ❌"
        )



async def bill(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) != 2:
        await update.message.reply_text(
            "Use: /bill ProductName Quantity"
        )
        return

    name = context.args[0]
    quantity = int(context.args[1])

    cursor.execute(
        "SELECT quantity, mrp, gst FROM products WHERE name=?",
        (name,)
    )

    product = cursor.fetchone()

    if product is None:
        await update.message.reply_text("Product not found ❌")
        return

    stock = product[0]
    mrp = product[1]
    gst = product[2]

    if quantity > stock:
        await update.message.reply_text(
            "Not enough stock ❌\n"
            "Available: " + str(stock)
        )
        return

    subtotal = quantity * mrp
    gst_amount = subtotal * gst / 100
    total = subtotal + gst_amount

    new_stock = stock - quantity

    cursor.execute(
        "UPDATE products SET quantity=? WHERE name=?",
        (new_stock, name)
    )

    conn.commit()

    await update.message.reply_text(
        "🧾 Bill Created!\n"
        "Product: " + name + "\n"
        "Quantity: " + str(quantity) + "\n"
        "Price: ₹" + str(mrp) + "\n"
        "Subtotal: ₹" + str(subtotal) + "\n"
        "GST (" + str(gst) + "%): ₹" + str(gst_amount) + "\n"
        "Total: ₹" + str(total) + "\n"
        "Remaining Stock: " + str(new_stock)
    )
async def new_bill(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    current_bills[user_id] = []

    await update.message.reply_text(
        "🧾 New bill started successfully!\n"
        "You can now add items."
    )
async def add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if len(context.args) != 2:
        await update.message.reply_text(
            "Use: /item ProductName Quantity"
        )
        return

    product_name = context.args[0]
    quantity = float(context.args[1])

    if user_id not in current_bills:
        current_bills[user_id] = []

    cursor.execute(
        """SELECT name, quantity, mrp, gst, unit, hsn
        FROM products
        WHERE lower(name)=?""",
        (product_name.lower(),)
    )

    product = cursor.fetchone()

    if product is None:
        await update.message.reply_text("Product not found ❌")
        return

    if quantity > product[1]:
        await update.message.reply_text("Not enough stock ❌")
        return

    current_bills[user_id].append({
        "name": product[0],
        "quantity": quantity,
        "mrp": product[2],
        "gst": product[3],
        "unit": product[4],
        "hsn": product[5]
    })

    await update.message.reply_text(
        product[0] + " × " + str(quantity) +
        " " + product[4] + " added to bill ✅"
    )
async def show_bill(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in current_bills or len(current_bills[user_id]) == 0:
        await update.message.reply_text("The bill is empty ❌")
        return

    message = "🧾 CURRENT BILL\n\n"
    subtotal = 0

    for item in current_bills[user_id]:

        amount = item["quantity"] * item["mrp"]
        subtotal += amount

        message += (
            item["name"] + " × " +
            str(item["quantity"]) + " " +
            item["unit"] +
            " = ₹" + str(round(amount, 2)) + "\n"
        )

    message += "\nSubtotal: ₹" + str(round(subtotal, 2))

    await update.message.reply_text(message)
def create_invoice(current_bill, subtotal, cgst, sgst, total, payment, invoice_number):

    filename = "invoice.pdf"

    pdf = canvas.Canvas(filename)

    # Shop details
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 800, "SUPERMARKET")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, 785, "GST INVOICE")
    pdf.drawString(50, 770, "Invoice No: INV" + str(invoice_number).zfill(3))
    pdf.drawString(50, 755, "Date: Today")

    y = 720

    # Items
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "Product")
    pdf.drawString(150, y, "HSN")
    pdf.drawString(220, y, "Qty")
    pdf.drawString(280, y, "GST")
    pdf.drawString(340, y, "Amount")

    y -= 20

    pdf.setFont("Helvetica", 10)

    for item in current_bill:

        amount = item["quantity"] * item["mrp"]

        pdf.drawString(50, y, item["name"])
        pdf.drawString(150, y, item["hsn"])
        pdf.drawString(220, y, str(item["quantity"]) + " " + item["unit"])
        pdf.drawString(280, y, str(item["gst"]) + "%")
        pdf.drawString(340, y, "Rs." + str(round(amount, 2)))

        y -= 20

    y -= 20

    pdf.drawString(50, y, "Subtotal:")
    pdf.drawString(340, y, "Rs." + str(round(subtotal, 2)))

    y -= 20

    pdf.drawString(50, y, "CGST:")
    pdf.drawString(340, y, "Rs." + str(round(cgst, 2)))

    y -= 20

    pdf.drawString(50, y, "SGST:")
    pdf.drawString(340, y, "Rs." + str(round(sgst, 2)))

    y -= 20

    pdf.drawString(50, y, "Total:")
    pdf.drawString(340, y, "Rs." + str(round(total, 2)))

    y -= 20

    pdf.drawString(50, y, "Payment:")
    pdf.drawString(340, y, payment.upper())

    y -= 40

    pdf.drawString(50, y, "Thank you for shopping with us!")

    pdf.save()

    return filename
def create_analysis():

    filename = "sales_analysis.pptx"

    prs = Presentation()

    # Slide 1
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "Supermarket Sales Analysis"
    slide.placeholders[1].text = "Daily Sales Report"

    # Get sales data
    cursor.execute("SELECT COUNT(*), SUM(total) FROM sales")
    result = cursor.fetchone()

    bills = result[0]
    total = result[1] or 0

    # Slide 2
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Sales Summary"

    slide.placeholders[1].text = (
        "Total Sales: ₹" + str(round(total, 2)) +
        "\nTotal Bills: " + str(bills)
    )

    # Payment summary
    cursor.execute(
        "SELECT payment, SUM(total) FROM sales GROUP BY payment"
    )

    rows = cursor.fetchall()

    text = ""

    for row in rows:
        text += row[0].upper() + ": ₹" + str(round(row[1], 2)) + "\n"

    # Slide 3
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Payment Analysis"
    slide.placeholders[1].text = text

    prs.save(filename)

    return filename


async def finalize_bill(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in current_bills or len(current_bills[user_id]) == 0:
        await update.message.reply_text("Bill is empty ❌")
        return

    bill = current_bills[user_id]

    if len(context.args) < 1 or len(context.args) > 2:
        await update.message.reply_text(
            "Use:\n"
            "/finalize Cash\n"
            "/finalize UPI TXN123\n"
            "/finalize Card CARD123\n"
            "/finalize Credit CustomerName"
        )
        return

    payment = context.args[0].lower()
    reference = ""

    if len(context.args) == 2:
        reference = context.args[1]

    customer = ""

    if payment == "credit":
        if len(context.args) != 2:
            await update.message.reply_text(
                "Use: /finalize Credit CustomerName"
            )
            return
        customer = context.args[1]

    if payment not in ["cash", "upi", "card", "credit"]:
        await update.message.reply_text(
            "Payment must be Cash, UPI, Card or Credit ❌"
        )
        return

    subtotal = 0
    gst_total = 0

    # Check stock
    for item in bill:

        cursor.execute(
            "SELECT quantity FROM products WHERE name=?",
            (item["name"],)
        )

        product = cursor.fetchone()

        if product is None or item["quantity"] > product[0]:
            await update.message.reply_text(
                "Not enough stock for " + item["name"] + " ❌"
            )
            return

    # Calculate bill
    for item in bill:

        amount = item["quantity"] * item["mrp"]
        gst = amount * item["gst"] / 100

        subtotal += amount
        gst_total += gst

    cgst = gst_total / 2
    sgst = gst_total / 2
    total = subtotal + gst_total

    # Reduce stock
    for item in bill:

        cursor.execute(
            "UPDATE products SET quantity = quantity - ? WHERE name=?",
            (item["quantity"], item["name"])
        )

    # Save sale
    cursor.execute(
        "INSERT INTO sales (total, payment, date) VALUES (?, ?, date('now'))",
        (total, payment)
    )

    invoice_number = cursor.lastrowid

    # Credit
    if payment == "credit":

        cursor.execute(
            "SELECT balance FROM khata WHERE customer=?",
            (customer,)
        )

        result = cursor.fetchone()

        if result is None:

            cursor.execute(
                "INSERT INTO khata (customer, balance) VALUES (?, ?)",
                (customer, total)
            )

        else:

            cursor.execute(
                "UPDATE khata SET balance = balance + ? WHERE customer=?",
                (total, customer)
            )

    # Create invoice
    filename = create_invoice(
        bill,
        subtotal,
        cgst,
        sgst,
        total,
        payment,
        invoice_number
    )

    conn.commit()

    message = (
        "🧾 BILL FINALIZED\n\n"
        "Subtotal: ₹" + str(round(subtotal, 2)) +
        "\nCGST: ₹" + str(round(cgst, 2)) +
        "\nSGST: ₹" + str(round(sgst, 2)) +
        "\nTotal: ₹" + str(round(total, 2)) +
        "\nPayment: " + payment.upper()
    )

    if payment == "credit":
        message += "\nCustomer: " + customer

    elif reference != "":
        message += "\nReference: " + reference

    await update.message.reply_text(message)

    with open(filename, "rb") as pdf:
        await update.message.reply_document(
            document=pdf,
            filename="invoice.pdf"
        )

    # Clear only this user's bill
    del current_bills[user_id]

async def add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) != 2:
        await update.message.reply_text(
            "Use: /credit CustomerName Amount"
        )
        return

    customer = context.args[0]
    amount = float(context.args[1])

    cursor.execute(
        "SELECT balance FROM khata WHERE customer=?",
        (customer,)
    )

    person = cursor.fetchone()

    if person:
        cursor.execute(
            "UPDATE khata SET balance = balance + ? WHERE customer=?",
            (amount, customer)
        )
    else:
        cursor.execute(
            "INSERT INTO khata (customer, balance) VALUES (?, ?)",
            (customer, amount)
        )

    conn.commit()

    await update.message.reply_text(
        "💰 Credit added!\n"
        "Customer: " + customer + "\n"
        "Amount: ₹" + str(amount)
    )
async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) != 1:
        await update.message.reply_text(
            "Use: /balance CustomerName"
        )
        return

    customer = context.args[0]

    cursor.execute(
        "SELECT balance FROM khata WHERE customer=?",
        (customer,)
    )

    person = cursor.fetchone()

    if person:
        await update.message.reply_text(
            "👤 Customer: " + customer + "\n"
            "Balance: ₹" + str(person[0])
        )
    else:
        await update.message.reply_text(
            "Customer not found ❌"
        )
async def khata_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) != 2:
        await update.message.reply_text(
            "Use: /payment CustomerName Amount"
        )
        return

    customer = context.args[0]
    amount = float(context.args[1])

    cursor.execute(
        "SELECT balance FROM khata WHERE customer=?",
        (customer,)
    )

    person = cursor.fetchone()

    if person is None:
        await update.message.reply_text(
            "Customer not found ❌"
        )
        return

    if amount > person[0]:
        await update.message.reply_text(
            "Payment is greater than balance ❌"
        )
        return

    cursor.execute(
        "UPDATE khata SET balance = balance - ? WHERE customer=?",
        (amount, customer)
    )

    conn.commit()

    await update.message.reply_text(
        "💵 Payment recorded!\n"
        "Customer: " + customer + "\n"
        "Paid: ₹" + str(amount) + "\n"
        "Remaining: ₹" + str(person[0] - amount)
    )
async def sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT SUM(total) FROM sales")
    result = cursor.fetchone()[0]

    if result is None:
        result = 0

    await update.message.reply_text(
        f"📊 Total Sales: ₹{result:.2f}"
    )
async def close_day(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cursor.execute(
        "SELECT COUNT(*), SUM(total) FROM sales WHERE date = date('now')"
    )

    result = cursor.fetchone()

    bills = result[0]
    total = result[1] or 0

    cursor.execute(
        "SELECT SUM(total) FROM sales WHERE date = date('now') AND payment='cash'"
    )
    cash = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(total) FROM sales WHERE date = date('now') AND payment='upi'"
    )
    upi = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(total) FROM sales WHERE date = date('now') AND payment='card'"
    )
    card = cursor.fetchone()[0] or 0

    message = (
        "📊 DAILY CLOSE\n\n"
        + "Total Sales: ₹" + str(round(total, 2)) + "\n"
        + "Cash: ₹" + str(round(cash, 2)) + "\n"
        + "UPI: ₹" + str(round(upi, 2)) + "\n"
        + "Card: ₹" + str(round(card, 2)) + "\n"
        + "Bills: " + str(bills)
        + "\n\n✅ Day Closed"
    )

    await update.message.reply_text(message)
async def analyse(update: Update, context: ContextTypes.DEFAULT_TYPE):

    filename = create_analysis()

    await update.message.reply_text(
        "📊 Sales analysis created!"
    )

    with open(filename, "rb") as ppt:
        await update.message.reply_document(
            document=ppt,
            filename="sales_analysis.pptx"
        )
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = """
🛒 SUPERMARKET AGENT

📦 INVENTORY
/add Name Quantity Cost MRP GST Unit
/stock ProductName
/receive ProductName Quantity
/lowstock

🧾 BILLING
/newbill
/item ProductName Quantity
/showbill
/change ProductName Quantity
/remove ProductName
/finalize Cash

💰 KHATA
/credit Customer Amount
/balance Customer
/payment Customer Amount

📊 REPORTS
/sales
/close
/analyse

💬 You can also ask:
"What is the stock of Rice?"
"Do we have Milk?"
"""

    await update.message.reply_text(message)
async def low_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cursor.execute(
        "SELECT name, quantity, reorder_level FROM products WHERE quantity <= reorder_level"
    )

    products = cursor.fetchall()

    if len(products) == 0:
        await update.message.reply_text("✅ All products have enough stock.")
        return

    message = "⚠️ LOW STOCK\n\n"

    for product in products:
        message += (
            product[0] + " → "
            + str(product[1])
            + " (Reorder at " + str(product[2]) + ")\n"
        )

    await update.message.reply_text(message)
async def remove_item(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global current_bill

    if len(context.args) != 1:
        await update.message.reply_text("Use: /remove ProductName")
        return

    name = " ".join(context.args)

    for item in current_bill:
        if item["name"].lower() == name.lower():
            current_bill.remove(item)
            await update.message.reply_text(
                name + " removed from bill ✅"
            )
            return

    await update.message.reply_text(
        name + " is not in the bill ❌"
    )
async def change_item(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global current_bill

    if len(context.args) != 2:
        await update.message.reply_text("Use: /change ProductName Quantity")
        return

    name = context.args[0]
    new_quantity = int(context.args[1])

    if new_quantity <= 0:
        await update.message.reply_text("Quantity must be greater than 0 ❌")
        return

    for item in current_bill:

        if item["name"].lower() == name.lower():

            if new_quantity > item["quantity"]:
                cursor.execute(
                    "SELECT quantity FROM products WHERE name=?",
                    (item["name"],)
                )

                product = cursor.fetchone()

                if product is None or new_quantity > product[0]:
                    await update.message.reply_text(
                        "Not enough stock ❌"
                    )
                    return

            item["quantity"] = new_quantity

            await update.message.reply_text(
                item["name"] + " quantity changed to "
                + str(new_quantity) + " ✅"
            )
            return

    await update.message.reply_text(
        name + " is not in the bill ❌"
    )

async def natural_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.lower()

    # Ignore buying messages
    if "want" in text or "buy" in text:
        return

    cursor.execute("SELECT name FROM products")
    products = cursor.fetchall()

    for product in products:

        name = product[0].lower()

        if name in text:

            cursor.execute(
                """SELECT name, quantity, unit, mrp, gst
                   FROM products
                   WHERE lower(name)=?""",
                (name,)
            )

            data = cursor.fetchone()

            message = (
                "📦 " + data[0] + "\n"
                + "Stock: " + str(data[1]) + " " + data[2] + "\n"
                + "MRP: ₹" + str(data[3]) + "\n"
                + "GST: " + str(data[4]) + "%"
            )

            await update.message.reply_text(message)
            return

    await update.message.reply_text(
        "Please mention a product name ❌"
    )

async def natural_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text.lower()

    if "want" in text or "buy" in text:
        await natural_bill(update, context)
    else:
        await natural_stock(update, context)

def get_stock_tool(product_name):

    cursor.execute(
        "SELECT name, quantity, unit, mrp, gst FROM products WHERE lower(name)=?",
        (product_name.lower(),)
    )

    product = cursor.fetchone()

    if product is None:
        return "Product not found"

    return (
        "Product: " + product[0] +
        ", Stock: " + str(product[1]) + " " + product[2] +
        ", MRP: ₹" + str(product[3]) +
        ", GST: " + str(product[4]) + "%"
    )
def add_item_tool(user_id, product_name, quantity):

    cursor.execute(
        """SELECT name, quantity, mrp, gst, unit, hsn
        FROM products
        WHERE lower(name)=?""",
        (product_name.lower(),)
    )

    product = cursor.fetchone()

    if product is None:
        return "Product not found"

    if quantity > product[1]:
        return "Not enough stock"

    if user_id not in current_bills:
        current_bills[user_id] = []

    current_bills[user_id].append({
        "name": product[0],
        "quantity": quantity,
        "mrp": product[2],
        "gst": product[3],
        "unit": product[4],
        "hsn": product[5]
    })

    return (
        product[0] + " × " + str(quantity) +
        " " + product[4] + " added to bill"
    )
def change_item_tool(user_id, product_name, quantity):

    if user_id not in current_bills:
        return "The bill is empty."

    for item in current_bills[user_id]:

        if item["name"].lower() == product_name.lower():

            if quantity <= 0:
                return "Quantity must be greater than 0"

            if quantity > item["quantity"]:
                cursor.execute(
                    "SELECT quantity FROM products WHERE lower(name)=?",
                    (product_name.lower(),)
                )

                product = cursor.fetchone()

                if product is None or quantity > product[0]:
                    return "Not enough stock"

            item["quantity"] = quantity

            return (
                product_name + " quantity changed to "
                + str(quantity) + " " + item["unit"]
            )

    return product_name + " is not in the bill"
def remove_item_tool(user_id, product_name):

    if user_id not in current_bills:
        return "The bill is empty."

    for item in current_bills[user_id]:

        if item["name"].lower() == product_name.lower():

            current_bills[user_id].remove(item)

            return product_name + " removed from bill"

    return product_name + " is not in the bill"
def show_bill_tool(user_id):

    if user_id not in current_bills or len(current_bills[user_id]) == 0:
        return "The bill is empty."

    message = "CURRENT BILL\n\n"
    subtotal = 0

    for item in current_bills[user_id]:

        amount = item["quantity"] * item["mrp"]
        subtotal += amount

        message += (
            item["name"] + " × " +
            str(item["quantity"]) + " " +
            item["unit"] +
            " = ₹" + str(round(amount, 2)) + "\n"
        )

    message += "\nSubtotal: ₹" + str(round(subtotal, 2))

    return message
def finalize_bill_tool(user_id, payment, reference="", customer=""):

    if user_id not in current_bills or len(current_bills[user_id]) == 0:
        return "Bill is empty."

    bill = current_bills[user_id]

    if payment == "credit" and customer == "":
        return "Customer name is required for credit."

    subtotal = 0
    gst_total = 0

    # Check stock
    for item in bill:

        cursor.execute(
            "SELECT quantity FROM products WHERE name=?",
            (item["name"],)
        )

        product = cursor.fetchone()

        if product is None:
            return "Product not found: " + item["name"]

        if item["quantity"] > product[0]:
            return "Not enough stock for " + item["name"]

    # Calculate bill
    for item in bill:

        amount = item["quantity"] * item["mrp"]
        gst = amount * item["gst"] / 100

        subtotal += amount
        gst_total += gst

    cgst = gst_total / 2
    sgst = gst_total / 2
    total = subtotal + gst_total

    # Reduce stock
    for item in bill:

        cursor.execute(
            "UPDATE products SET quantity = quantity - ? WHERE name=?",
            (item["quantity"], item["name"])
        )

    # Save sale
    cursor.execute(
        "INSERT INTO sales (total, payment, date) VALUES (?, ?, date('now'))",
        (total, payment)
    )

    invoice_number = cursor.lastrowid

    # Credit sale
    if payment == "credit":

        cursor.execute(
            "SELECT balance FROM khata WHERE customer=?",
            (customer,)
        )

        result = cursor.fetchone()

        if result is None:

            cursor.execute(
                "INSERT INTO khata (customer, balance) VALUES (?, ?)",
                (customer, total)
            )

        else:

            cursor.execute(
                "UPDATE khata SET balance = balance + ? WHERE customer=?",
                (total, customer)
            )

    # Create PDF
    filename = create_invoice(
        bill,
        subtotal,
        cgst,
        sgst,
        total,
        payment,
        invoice_number
    )

    conn.commit()

    result = (
        "Bill finalized successfully.\n\n"
        "Subtotal: ₹" + str(round(subtotal, 2)) +
        "\nCGST: ₹" + str(round(cgst, 2)) +
        "\nSGST: ₹" + str(round(sgst, 2)) +
        "\nTotal: ₹" + str(round(total, 2)) +
        "\nPayment: " + payment.upper()
    )

    if payment == "credit":
        result += "\nCustomer: " + customer

    elif reference != "":
        result += "\nReference: " + reference

    # Clear only this user's bill
    del current_bills[user_id]

    return result + "\nINVOICE_FILE:" + filename
def check_balance_tool(customer):

    cursor.execute(
        "SELECT balance FROM khata WHERE lower(customer)=?",
        (customer.lower(),)
    )

    result = cursor.fetchone()

    if result is None:
        return customer + " has no outstanding balance."

    return (
        "Customer: " + customer +
        "\nKhata Balance: ₹" + str(round(result[0], 2))
    )
def khata_payment_tool(customer, amount):

    cursor.execute(
        "SELECT balance FROM khata WHERE lower(customer)=?",
        (customer.lower(),)
    )

    result = cursor.fetchone()

    if result is None:
        return customer + " does not have a Khata account."

    balance = result[0]

    if amount <= 0:
        return "Payment amount must be greater than 0."

    if amount > balance:
        return (
            "Payment is greater than Ravi's balance.\n"
            "Current balance: ₹" + str(round(balance, 2))
        )

    new_balance = balance - amount

    cursor.execute(
        "UPDATE khata SET balance=? WHERE lower(customer)=?",
        (new_balance, customer.lower())
    )

    conn.commit()

    return (
        customer + " paid ₹" + str(round(amount, 2)) +
        " successfully ✅\n"
        "Remaining balance: ₹" + str(round(new_balance, 2))
    )
def receive_stock_tool(product_name, quantity):

    cursor.execute(
        "SELECT quantity FROM products WHERE lower(name)=?",
        (product_name.lower(),)
    )

    product = cursor.fetchone()

    if product is None:
        return product_name + " not found."

    new_quantity = product[0] + quantity

    cursor.execute(
        "UPDATE products SET quantity=? WHERE lower(name)=?",
        (new_quantity, product_name.lower())
    )

    conn.commit()

    return (
        product_name +
        " stock received successfully ✅\n"
        "New stock: " +
        str(new_quantity)
    )
def add_product_tool(name, quantity, cost, mrp, gst, unit, reorder_level, hsn):

    cursor.execute(
        "SELECT name FROM products WHERE lower(name)=?",
        (name.lower(),)
    )

    product = cursor.fetchone()

    if product is not None:
        return name + " already exists."

    cursor.execute(
        """INSERT INTO products
        (name, quantity, cost, mrp, gst, unit, reorder_level, hsn)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, quantity, cost, mrp, gst, unit, reorder_level, hsn)
    )

    conn.commit()

    return (
        name + " added successfully ✅\n"
        "Stock: " + str(quantity) + " " + unit +
        "\nCost: ₹" + str(cost) +
        "\nMRP: ₹" + str(mrp) +
        "\nGST: " + str(gst) + "%" +
        "\nReorder level: " + str(reorder_level) +
        "\nHSN: " + hsn
    )
def get_stock_tool(product_name):

    cursor.execute(
        """SELECT name, quantity, unit, mrp, gst, hsn
        FROM products
        WHERE lower(name)=?""",
        (product_name.lower(),)
    )

    product = cursor.fetchone()

    if product is None:
        return "Product not found"

    return (
        "Product: " + product[0] +
        "\nStock: " + str(product[1]) + " " + product[2] +
        "\nMRP: ₹" + str(product[3]) +
        "\nGST: " + str(product[4]) + "%" +
        "\nHSN: " + product[5]
    )
def low_stock_tool():
    cursor.execute(
        "SELECT name, quantity, unit, reorder_level FROM products WHERE quantity <= reorder_level"
    )

    products = cursor.fetchall()

    if len(products) == 0:
        return "All products have enough stock."

    result = "LOW STOCK PRODUCTS\n\n"

    for product in products:
        result += (
            product[0] + " → " +
            str(product[1]) + " " +
            product[2] +
            " (Reorder at " +
            str(product[3]) + ")\n"
        )

    return result
def close_day_tool():

    cursor.execute(
        "SELECT COUNT(*), SUM(total) FROM sales WHERE date = date('now')"
    )

    result = cursor.fetchone()

    bills = result[0]
    total = result[1] or 0

    cursor.execute(
        "SELECT SUM(total) FROM sales WHERE date = date('now') AND payment='cash'"
    )
    cash = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(total) FROM sales WHERE date = date('now') AND payment='upi'"
    )
    upi = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(total) FROM sales WHERE date = date('now') AND payment='card'"
    )
    card = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(total) FROM sales WHERE date = date('now') AND payment='credit'"
    )
    credit = cursor.fetchone()[0] or 0

    return (
        "📊 DAILY CLOSE\n\n"
        "Total Sales: ₹" + str(round(total, 2)) +
        "\nCash: ₹" + str(round(cash, 2)) +
        "\nUPI: ₹" + str(round(upi, 2)) +
        "\nCard: ₹" + str(round(card, 2)) +
        "\nCredit: ₹" + str(round(credit, 2)) +
        "\nBills: " + str(bills) +
        "\n\n✅ Day Closed"
    )
def save_preference_tool(user_id, key, value):

    key = key.lower().replace(" ", "_")

    cursor.execute("""
        INSERT OR REPLACE INTO preferences
        (user_id, key, value)
        VALUES (?, ?, ?)
    """, (user_id, key, value))

    conn.commit()

    return "Preference saved successfully ✅"
def get_preference_tool(user_id, key):

    key = key.lower().replace(" ", "_")

    cursor.execute(
        "SELECT value FROM preferences WHERE user_id=? AND key=?",
        (user_id, key)
    )

    result = cursor.fetchone()

    if result is None:
        return "No preference found."

    return key + ": " + result[0]
async def finalize_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    result = finalize_bill_tool(
        user_id,
        "cash",
        "",
        ""
    )

    if "INVOICE_FILE:" in result:

        parts = result.split("\nINVOICE_FILE:", 1)

        await update.message.reply_text(parts[0])

        filename = parts[1]

        with open(filename, "rb") as pdf:
            await update.message.reply_document(
                document=pdf,
                filename="invoice.pdf"
            )

    else:
        await update.message.reply_text(result)
async def ai_test(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    user_message = update.message.text

    system_prompt = """
You are a supermarket assistant for an Indian kirana store.

Help with:
- Inventory
- Billing
- Stock receiving
- Khata
- Payments
- Daily sales
- Low stock
- Customer preferences

Rules:
1. Always use tools when product, stock, bill, Khata or preference information is needed.
2. Never invent stock, prices, GST, HSN or customer balance.
3. For adding a product, ask for missing HSN if it is not provided.
4. Payment can be cash, UPI, card or credit.
5. For credit payment, customer name is required.
6. Keep responses short and clear.

IMPORTANT BILLING RULES:
7. If the user says "show my bill", call show_bill.
8. If the user says "finalize", "finalise", "complete the bill", or "finish the bill", call finalize_bill.
9. If the user says "finalize with cash", call finalize_bill with payment="cash".
10. If the user says "finalize with UPI", call finalize_bill with payment="upi".
11. If the user says "finalize with card", call finalize_bill with payment="card".
12. Never call show_bill when the user asks to finalize.
"""

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_stock",
                "description": "Check stock of a product",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_name": {"type": "string"}
                    },
                    "required": ["product_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "add_item",
                "description": "Add product to current bill",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_name": {"type": "string"},
                        "quantity": {"type": "number"}
                    },
                    "required": ["product_name", "quantity"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "change_item",
                "description": "Change quantity of an item in current bill",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_name": {"type": "string"},
                        "quantity": {"type": "number"}
                    },
                    "required": ["product_name", "quantity"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "remove_item",
                "description": "Remove an item from current bill",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_name": {"type": "string"}
                    },
                    "required": ["product_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "show_bill",
                "description": "Show current bill",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "finalize_bill",
                "description": "Finalize the current bill and create invoice PDF. MUST be used when user wants to finalize the bill.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "payment": {
                            "type": "string",
                            "enum": ["cash", "upi", "card", "credit"]
                        },
                        "reference": {
                            "type": "string"
                        },
                        "customer": {
                            "type": "string"
                        }
                    },
                    "required": ["payment"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_balance",
                "description": "Check customer Khata balance",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer": {"type": "string"}
                    },
                    "required": ["customer"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "khata_payment",
                "description": "Record payment against customer Khata",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "customer": {"type": "string"},
                        "amount": {"type": "number"}
                    },
                    "required": ["customer", "amount"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "receive_stock",
                "description": "Receive stock for an existing product",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_name": {"type": "string"},
                        "quantity": {"type": "number"}
                    },
                    "required": ["product_name", "quantity"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "add_product",
                "description": "Add a new product to inventory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "quantity": {"type": "number"},
                        "cost": {"type": "number"},
                        "mrp": {"type": "number"},
                        "gst": {"type": "number"},
                        "unit": {"type": "string"},
                        "reorder_level": {"type": "number"},
                        "hsn": {"type": "string"}
                    },
                    "required": [
                        "name",
                        "quantity",
                        "cost",
                        "mrp",
                        "gst",
                        "unit",
                        "reorder_level",
                        "hsn"
                    ]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "low_stock",
                "description": "Show products below reorder level",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "close_day",
                "description": "Close the day and show daily sales summary",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "save_preference",
                "description": "Save a user preference",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "value": {"type": "string"}
                    },
                    "required": ["key", "value"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_preference",
                "description": "Get a saved user preference",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"}
                    },
                    "required": ["key"]
                }
            }
        }
    ]

    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": user_message
        }
    ]

    try:

        response = client.chat.completions.create(
            model="openrouter/free",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=300
        )

        message = response.choices[0].message

        if not message.tool_calls:

            await update.message.reply_text(
                message.content or "I could not understand that."
            )
            return

        for tool_call in message.tool_calls:

            name = tool_call.function.name

            try:
                arguments = json.loads(
                    tool_call.function.arguments
                )
            except:
                arguments = {}

            if name == "get_stock":

                result = get_stock_tool(
                    arguments["product_name"]
                )

            elif name == "add_item":

                result = add_item_tool(
                    user_id,
                    arguments["product_name"],
                    arguments["quantity"]
                )

            elif name == "change_item":

                result = change_item_tool(
                    user_id,
                    arguments["product_name"],
                    arguments["quantity"]
                )

            elif name == "remove_item":

                result = remove_item_tool(
                    user_id,
                    arguments["product_name"]
                )

            elif name == "show_bill":

                result = show_bill_tool(user_id)

            elif name == "finalize_bill":

                result = finalize_bill_tool(
                    user_id,
                    arguments["payment"],
                    arguments.get("reference", ""),
                    arguments.get("customer", "")
                )

            elif name == "check_balance":

                result = check_balance_tool(
                    arguments["customer"]
                )

            elif name == "khata_payment":

                result = khata_payment_tool(
                    arguments["customer"],
                    arguments["amount"]
                )

            elif name == "receive_stock":

                result = receive_stock_tool(
                    arguments["product_name"],
                    arguments["quantity"]
                )

            elif name == "add_product":

                result = add_product_tool(
                    arguments["name"],
                    arguments["quantity"],
                    arguments["cost"],
                    arguments["mrp"],
                    arguments["gst"],
                    arguments["unit"],
                    arguments["reorder_level"],
                    arguments["hsn"]
                )

            elif name == "low_stock":

                result = low_stock_tool()

            elif name == "close_day":

                result = close_day_tool()

            elif name == "save_preference":

                result = save_preference_tool(
                    user_id,
                    arguments["key"],
                    arguments["value"]
                )

            elif name == "get_preference":

                result = get_preference_tool(
                    user_id,
                    arguments["key"]
                )

            else:

                result = "Unknown tool ❌"

            # Send invoice PDF after finalizing
            if name == "finalize_bill" and "INVOICE_FILE:" in result:

                parts = result.split(
                    "\nINVOICE_FILE:",
                    1
                )

                await update.message.reply_text(
                    parts[0]
                )

                filename = parts[1]

                try:

                    with open(filename, "rb") as pdf:

                        await update.message.reply_document(
                            document=pdf,
                            filename="invoice.pdf"
                        )

                except Exception as e:

                    await update.message.reply_text(
                        "Invoice created but could not send PDF ❌\n"
                        + str(e)
                    )

            else:

                await update.message.reply_text(
                    str(result)
                )

    except Exception as e:

        await update.message.reply_text(
            "Something went wrong ❌\n" + str(e)
        )


app = Application.builder().token(TOKEN).build()


app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("add", add_product))
app.add_handler(CommandHandler("stock", stock))
app.add_handler(CommandHandler("lowstock", low_stock))
app.add_handler(CommandHandler("receive", receive_stock))
#app.add_handler(CommandHandler("bill", bill))
app.add_handler(CommandHandler("newbill", new_bill))
app.add_handler(CommandHandler("item", add_item))
app.add_handler(CommandHandler("remove", remove_item))
app.add_handler(CommandHandler("change", change_item))
app.add_handler(CommandHandler("showbill", show_bill))
app.add_handler(CommandHandler("finalize", finalize_bill))

app.add_handler(CommandHandler("credit", add_credit))
app.add_handler(CommandHandler("balance", check_balance))
app.add_handler(CommandHandler("payment", khata_payment))
app.add_handler(CommandHandler("sales", sales))
app.add_handler(CommandHandler("close", close_day))
app.add_handler(CommandHandler("analyse", analyse))
#app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message))
#app.add_handler(
 #   MessageHandler(filters.TEXT & ~filters.COMMAND, natural_bill)
#)

#app.add_handler(
 #   MessageHandler(filters.TEXT & ~filters.COMMAND, natural_stock)
#)
#app.add_handler(
 #   MessageHandler(filters.TEXT & ~filters.COMMAND, natural_message)
#)
app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, ai_test)
)
app.add_handler(
    MessageHandler(
        filters.Regex("(?i)^finalize with cash$"),
        finalize_text
    )
)
print("Bot is running...")
app.run_polling()

