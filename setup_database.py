import pandas as pd
import sqlite3

# Step 1: Load the existing e-commerce dataset
df = pd.read_csv("shopsense_sample_ecommerce.csv")

# Step 2: Connect to SQLite database
connection = sqlite3.connect("shopsense.db")

# Step 3: Store dataset in a SQL table
df.to_sql(
    "orders",
    connection,
    if_exists="replace",
    index=False
)

# Step 4: Verify the database
result = pd.read_sql_query(
    "SELECT * FROM orders LIMIT 5",
    connection
)

print("Database created successfully!")
print("\nFirst 5 records:")
print(result)

# Step 5: Display total records
total_records = pd.read_sql_query(
    "SELECT COUNT(*) AS total_orders FROM orders",
    connection
)

print("\nTotal records:")
print(total_records)
# Step 6: Top 10 products by revenue
top_products = pd.read_sql_query("""
    SELECT
        Product,
        ROUND(SUM(Sales), 2) AS Total_Revenue
    FROM orders
    GROUP BY Product
    ORDER BY Total_Revenue DESC
    LIMIT 10
""", connection)

print("\nTop 10 Products by Revenue:")
print(top_products.to_string(index=False))


# Step 7: Country-wise revenue
country_revenue = pd.read_sql_query("""
    SELECT
        Country,
        ROUND(SUM(Sales), 2) AS Total_Revenue
    FROM orders
    GROUP BY Country
    ORDER BY Total_Revenue DESC
""", connection)

print("\nCountry-wise Revenue:")
print(country_revenue.to_string(index=False))


# Step 8: Monthly revenue
monthly_revenue = pd.read_sql_query("""
    SELECT
        SUBSTR(OrderDate, 1, 7) AS YearMonth,
        ROUND(SUM(Sales), 2) AS Total_Revenue
    FROM orders
    GROUP BY YearMonth
    ORDER BY YearMonth
""", connection)

print("\nMonthly Revenue:")
print(monthly_revenue.to_string(index=False))


# Step 9: Profit by category
category_profit = pd.read_sql_query("""
    SELECT
        Category,
        ROUND(SUM(Profit), 2) AS Total_Profit
    FROM orders
    GROUP BY Category
    ORDER BY Total_Profit DESC
""", connection)

print("\nProfit by Category:")
print(category_profit.to_string(index=False))
connection.close()