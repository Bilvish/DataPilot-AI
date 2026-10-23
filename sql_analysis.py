import sqlite3
import pandas as pd

# Connect to the ShopSense database
connection = sqlite3.connect("shopsense.db")

# 1. Overall business summary
business_summary = pd.read_sql_query("""
    SELECT
        COUNT(DISTINCT OrderID) AS Total_Orders,
        COUNT(DISTINCT CustomerID) AS Total_Customers,
        ROUND(SUM(Sales), 2) AS Total_Revenue,
        ROUND(SUM(Profit), 2) AS Total_Profit,
        ROUND(AVG(Sales), 2) AS Average_Line_Sales
    FROM orders
    WHERE Quantity > 0
""", connection)

print("\n--- BUSINESS SUMMARY ---")
print(business_summary.to_string(index=False))


# 2. Top 10 products by revenue
top_products = pd.read_sql_query("""
    SELECT
        Product,
        SUM(Quantity) AS Units_Sold,
        ROUND(SUM(Sales), 2) AS Revenue,
        ROUND(SUM(Profit), 2) AS Profit
    FROM orders
    WHERE Quantity > 0
    GROUP BY Product
    ORDER BY Revenue DESC
    LIMIT 10
""", connection)

print("\n--- TOP 10 PRODUCTS ---")
print(top_products.to_string(index=False))


# 3. Country-wise performance
country_analysis = pd.read_sql_query("""
    SELECT
        Country,
        COUNT(DISTINCT OrderID) AS Total_Orders,
        ROUND(SUM(Sales), 2) AS Revenue,
        ROUND(SUM(Profit), 2) AS Profit
    FROM orders
    WHERE Quantity > 0
    GROUP BY Country
    ORDER BY Revenue DESC
""", connection)

print("\n--- COUNTRY ANALYSIS ---")
print(country_analysis.to_string(index=False))


# 4. Monthly revenue trend
monthly_revenue = pd.read_sql_query("""
    SELECT
        strftime('%Y-%m', OrderDate) AS Month,
        ROUND(SUM(Sales), 2) AS Revenue
    FROM orders
    WHERE Quantity > 0
    GROUP BY strftime('%Y-%m', OrderDate)
    ORDER BY Month
""", connection)

print("\n--- MONTHLY REVENUE ---")
print(monthly_revenue.to_string(index=False))

connection.close()