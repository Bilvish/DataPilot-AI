import sqlite3
import pandas as pd

# Connect to ShopSense database
connection = sqlite3.connect("shopsense.db")

# 1. Total revenue
revenue = pd.read_sql_query("""
    SELECT ROUND(SUM(Sales), 2) AS Total_Revenue
    FROM orders
""", connection)

# 2. Total unique orders
orders = pd.read_sql_query("""
    SELECT COUNT(DISTINCT OrderID) AS Total_Orders
    FROM orders
""", connection)

# 3. Total unique customers
customers = pd.read_sql_query("""
    SELECT COUNT(DISTINCT CustomerID) AS Total_Customers
    FROM orders
""", connection)

# 4. Top 5 products by revenue
top_products = pd.read_sql_query("""
    SELECT Product, ROUND(SUM(Sales), 2) AS Revenue
    FROM orders
    GROUP BY Product
    ORDER BY Revenue DESC
    LIMIT 5
""", connection)

connection.close()

print("TOTAL REVENUE")
print(revenue)

print("\nTOTAL ORDERS")
print(orders)

print("\nTOTAL CUSTOMERS")
print(customers)

print("\nTOP 5 PRODUCTS")
print(top_products)