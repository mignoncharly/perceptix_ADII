"""
Data Generator for Perceptix
Generates realistic e-commerce data for 'orders' and 'users' tables in SQLite.
"""
import sqlite3
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DataGenerator")

DB_PATH = Path("data/source.db")
USERS_COUNT = 45000
ORDERS_COUNT = 15420

def create_schema(conn):
    """Create the schema for users and orders."""
    conn.execute("DROP TABLE IF EXISTS users")
    conn.execute("DROP TABLE IF EXISTS orders")

    conn.execute("""
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            signup_date TEXT NOT NULL,
            segment TEXT,
            is_active BOOLEAN
        )
    """)
    
    conn.execute("""
        CREATE TABLE orders (
            order_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            total_amount REAL,
            attribution_source TEXT,
            status TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    """)
    
    conn.execute("""
        CREATE TABLE products (
            product_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            price REAL
        )
    """)

    conn.execute("""
        CREATE TABLE inventory (
            product_id TEXT PRIMARY KEY,
            quantity INTEGER,
            last_updated TEXT,
            FOREIGN KEY(product_id) REFERENCES products(product_id)
        )
    """)
    logger.info("Schema created.")

def generate_users(conn, count):
    """Generate realistic user data."""
    logger.info(f"Generating {count} users...")
    users = []
    base_date = datetime.now(timezone.utc) - timedelta(days=365*2)
    
    segments = ['consumer', 'business', 'enterprise']
    domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'company.com']
    
    for _ in range(count):
        user_id = str(uuid.uuid4())
        signup_date = base_date + timedelta(days=random.randint(0, 700))
        email = f"user_{user_id[:8]}@{random.choice(domains)}"
        
        users.append((
            user_id,
            email,
            signup_date.isoformat(),
            random.choice(segments),
            random.random() > 0.1  # 90% active
        ))
        
    conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", users)
    conn.commit()
    logger.info("Users generated.")
    return [u[0] for u in users]

def generate_orders(conn, count, user_ids):
    """Generate realistic order data."""
    logger.info(f"Generating {count} orders...")
    orders = []
    sources = ['google_ads', 'facebook', 'direct', 'email_campaign', 'referral', None] # None allows for some natural nulls
    statuses = ['completed', 'pending', 'cancelled', 'refunded']
    
    # 95% of orders are recent (last 30 days) to simulate active system
    recent_start = datetime.now(timezone.utc) - timedelta(days=30)
    
    for _ in range(count):
        order_id = str(uuid.uuid4())
        user_id = random.choice(user_ids)
        amount = round(random.uniform(10.0, 500.0), 2)
        
        # Weighted random for source (simulates healthy state usually < 5% null)
        # Weights: [0.3, 0.2, 0.2, 0.15, 0.1, 0.05] -> 5% null naturally
        source = random.choices(sources, weights=[30, 20, 20, 15, 10, 5])[0]
        
        status = random.choices(statuses, weights=[80, 5, 10, 5])[0]
        timestamp = recent_start + timedelta(minutes=random.randint(0, 30*24*60))
        
        orders.append((
            order_id,
            user_id,
            amount,
            source,
            status,
            timestamp.isoformat()
        ))
        
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", orders)
    conn.commit()
    logger.info("Orders generated.")

def generate_products(conn):
    """Generate realistic product data."""
    logger.info("Generating products...")
    products = []
    categories = ['Electronics', 'Home & Garden', 'Clothing', 'Books', 'Toys']
    
    # Generate 500 products
    for i in range(500):
        product_id = f"PROD-{i:04d}"
        category = random.choice(categories)
        price = round(random.uniform(10.0, 1000.0), 2)
        name = f"{category} Product {i}"
        
        products.append((
            product_id,
            name,
            category,
            price
        ))
        
    conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", products)
    conn.commit()
    logger.info("Products generated.")
    return [p[0] for p in products]

def generate_inventory(conn, product_ids):
    """Generate inventory levels."""
    logger.info("Generating inventory...")
    inventory = []
    timestamp = datetime.now(timezone.utc).isoformat()
    
    for product_id in product_ids:
        # 5% of products have low inventory
        if random.random() < 0.05:
            quantity = random.randint(0, 5)
        else:
            quantity = random.randint(10, 500)
            
        inventory.append((
            product_id,
            quantity,
            timestamp
        ))
        
    conn.executemany("INSERT INTO inventory VALUES (?, ?, ?)", inventory)
    conn.commit()
    logger.info("Inventory generated.")

def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(DB_PATH) as conn:
        create_schema(conn)
        user_ids = generate_users(conn, USERS_COUNT)
        generate_orders(conn, ORDERS_COUNT, user_ids)
        product_ids = generate_products(conn)
        generate_inventory(conn, product_ids)
        
    logger.info(f"Database successfully created at {DB_PATH}")

if __name__ == "__main__":
    main()
