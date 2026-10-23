import pandas as pd

# Dataset load karna
df = pd.read_csv("data.csv")

# Dataset ki pehli 5 rows dekhna
print("\n--- ShopSense Dataset ---")
print(df.head())

# Total sales calculate karna
total_sales = df["Sales"].sum()
print("\nTotal Sales: ₹", total_sales)

# Total profit calculate karna
total_profit = df["Profit"].sum()
print("Total Profit: ₹", total_profit)

# Sabse zyada sales wala product
top_product = df.loc[df["Sales"].idxmax(), "Product"]
print("Top Product:", top_product)

# Category-wise sales analysis
category_sales = df.groupby("Category")["Sales"].sum()

print("\n--- Category-wise Sales ---")
print(category_sales)

# Sabse zyada sales wali category
best_category = category_sales.idxmax()

print("\nBest Selling Category:", best_category)

# Category-wise sales ka bar chart
import matplotlib.pyplot as plt

category_sales = df.groupby("Category")["Sales"].sum()
plt.figure(figsize=(8, 5))
category_sales.plot(kind="bar")
plt.title("ShopSense - Sales by Category")
plt.xlabel("Product Category")
plt.ylabel("Total Sales (₹)")
plt.xticks(rotation=0)
plt.tight_layout()
plt.show()

# Top 5 products by sales
print("\n--- Top Products by Sales ---")

top_products = df.sort_values(
    by="Sales", ascending=False
).head(5)

print(top_products[["Product", "Sales", "Profit"]])


# Category-wise profit
print("\n--- Category-wise Profit ---")

category_profit = df.groupby("Category")["Profit"].sum()
print(category_profit)

# 1. Average order sales
average_sales = df["Sales"].mean()
print("\nAverage Sales per Order: ₹", round(average_sales, 2))


# 2. Total number of orders
total_orders = df["OrderID"].nunique()
print("Total Orders:", total_orders)


# 3. Best category by profit
category_profit = df.groupby("Category")["Profit"].sum()
best_profit_category = category_profit.idxmax()

print("Most Profitable Category:", best_profit_category)


# 4. Profit margin
total_sales = df["Sales"].sum()
total_profit = df["Profit"].sum()

profit_margin = (total_profit / total_sales) * 100
print("Overall Profit Margin:", round(profit_margin, 2), "%")

# 1. Average order sales
average_sales = df["Sales"].mean()
print("\nAverage Sales per Order: ₹", round(average_sales, 2))


# 2. Total number of orders
total_orders = df["OrderID"].nunique()
print("Total Orders:", total_orders)


# 3. Best category by profit
category_profit = df.groupby("Category")["Profit"].sum()
best_profit_category = category_profit.idxmax()

print("Most Profitable Category:", best_profit_category)


# 4. Profit margin
total_sales = df["Sales"].sum()
total_profit = df["Profit"].sum()

profit_margin = (total_profit / total_sales) * 100
print("Overall Profit Margin:", round(profit_margin, 2), "%")

# -------- DATA CLEANING --------

df = df.drop_duplicates()

df = df.dropna(subset=["OrderID", "Product", "Sales", "Profit"])

df["Sales"] = pd.to_numeric(df["Sales"], errors="coerce")
df["Profit"] = pd.to_numeric(df["Profit"], errors="coerce")

df = df.dropna(subset=["Sales", "Profit"])

print("\n--- Cleaned Dataset ---")
print("Total Rows:", len(df))
print("Missing Values Remaining:")
print(df.isnull().sum())

# -------- DATA QUALITY CHECK -------- 
print("\n--- Dataset Information ---") 
df.info() 
print("\n--- Missing Values ---") 
print(df.isnull().sum()) 
print("\n--- Duplicate Rows ---") 
print(df.duplicated().sum())

# -------- DATA CLEANING --------

# Duplicate rows remove karna
df = df.drop_duplicates()

# Sales aur Profit ko numeric banana
df["Sales"] = pd.to_numeric(df["Sales"], errors="coerce")
df["Profit"] = pd.to_numeric(df["Profit"], errors="coerce")

# Important columns ki missing values remove karna
df = df.dropna(
    subset=["OrderID", "Product", "Category", "Sales", "Profit"]
)

# Cleaning ke baad result check karna
print("\n--- Cleaned Dataset ---")
print("Total Rows:", len(df))

print("\nMissing Values:")
print(df.isnull().sum())

print("\nDuplicate Rows:", df.duplicated().sum())

#Category-wise total sales

category_sales = df.groupby("Category")["Sales"].sum().sort_values(ascending=False)

print("\n--- Category-wise Sales ---")
print(category_sales)

# Category-wise total profit

category_profit = df.groupby("Category")["Profit"].sum().sort_values(ascending=False)

print("\n--- Category-wise Profit ---")
print(category_profit)

#Save results to CSV files

category_sales.to_csv("category_sales.csv")
category_profit.to_csv("category_profit.csv")

print("\nAnalysis files successfully saved!")

