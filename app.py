import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import sqlite3

st.set_page_config(page_title="ShopSense | Analytics", page_icon="🛍️", layout="wide")

st.markdown("""
<style>
.stApp {background:#f4f6fb;}
[data-testid="stSidebar"] {background:#111827;}
[data-testid="stSidebar"] * {color:#e5e7eb;}
.brand {font-size:1.65rem;font-weight:800;color:white;margin-bottom:0;}
.muted {color:#64748b;font-size:.9rem;}
div[data-testid="stMetric"] {background:white;border:1px solid #e5eaf2;padding:1rem;border-radius:15px;box-shadow:0 3px 12px #0f172a08;}
div[data-testid="stVerticalBlockBorderWrapper"] {background:white;border:1px solid #e5eaf2;border-radius:15px;padding:1rem;}
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_data():
    connection = sqlite3.connect("shopsense.db")

    try:
        table_exists = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='orders'",
            connection
        )

        if table_exists.empty:
            df_source = pd.read_csv("shopsense_sample_ecommerce.csv")
            df_source.to_sql(
                "orders",
                connection,
                if_exists="replace",
                index=False
            )

        df = pd.read_sql_query("SELECT * FROM orders", connection)

    finally:
        connection.close()

    df["OrderDate"] = pd.to_datetime(df["OrderDate"], errors="coerce")

    for col in ["Quantity", "UnitPrice", "UnitCost", "Sales", "Profit"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(
        subset=[
            "OrderID", "OrderDate", "CustomerID", "Product",
            "Category", "Country", "Quantity", "Sales", "Profit"
        ]
    )

    df = df[(df["Quantity"] > 0) & (df["Sales"] >= 0)].copy()
    df["YearMonth"] = df["OrderDate"].dt.to_period("M").astype(str)

    return df








try:
    df = load_data()
except FileNotFoundError:
    st.error("Dataset not found. Keep shopsense_sample_ecommerce.csv in the same folder as app.py.")
    st.stop()
except Exception as exc:
    st.error(f"Could not load dataset: {exc}")
    st.stop()

with st.sidebar:
    st.markdown('<div class="brand">🛍️ ShopSense</div>', unsafe_allow_html=True)
    st.caption("E-COMMERCE INTELLIGENCE")
    st.markdown("---")
    page = st.radio(
    "Navigation",
    [
        "Overview",
        "Revenue Analytics",
        "Product Performance",
        "Customers & Orders",
        "Dataset",
        "SQL Business Insights",
        "Business Insights & Recommendations",
    ]
)
    st.markdown("---")
    st.subheader("Filters")
    cats = ["All categories"] + sorted(df["Category"].dropna().unique().tolist())
    countries = ["All countries"] + sorted(df["Country"].dropna().unique().tolist())
    channels = ["All channels"] + sorted(df["SalesChannel"].dropna().unique().tolist())
    cat = st.selectbox("Category", cats)
    country = st.selectbox("Country", countries)
    channel = st.selectbox("Sales channel", channels)
    start, end = df["OrderDate"].min().date(), df["OrderDate"].max().date()
    date_range = st.date_input("Order date range", value=(start, end), min_value=start, max_value=end)
    search = st.text_input("Search product", placeholder="Type a product name")
    st.markdown("---")
    st.caption("Synthetic demo dataset • 1,500 sample orders")

filtered = df.copy()
if cat != "All categories":
    filtered = filtered[filtered["Category"] == cat]
if country != "All countries":
    filtered = filtered[filtered["Country"] == country]
if channel != "All channels":
    filtered = filtered[filtered["SalesChannel"] == channel]
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    filtered = filtered[(filtered["OrderDate"].dt.date >= date_range[0]) & (filtered["OrderDate"].dt.date <= date_range[1])]
elif isinstance(date_range, (tuple, list)) and len(date_range) == 1:
    filtered = filtered[filtered["OrderDate"].dt.date == date_range[0]]
if search.strip():
    filtered = filtered[filtered["Product"].str.contains(search.strip(), case=False, na=False)]

st.markdown('<p style="color:#64748b;letter-spacing:2px;font-size:12px;font-weight:700;margin-bottom:0;">ANALYTICS WORKSPACE / E-COMMERCE</p>', unsafe_allow_html=True)
st.title("Business overview")
st.markdown('<p class="muted">Track revenue, product performance and customer activity in one place.</p>', unsafe_allow_html=True)
head1, head2 = st.columns([5,1])
head1.caption(f"Showing {len(filtered):,} of {len(df):,} rows after filters")
head2.download_button("⬇ Export data", filtered.to_csv(index=False).encode("utf-8"), "shopsense_filtered_orders.csv", "text/csv")

if filtered.empty:
    st.warning("No records match these filters. Clear a filter or widen the date range.")
    st.stop()

revenue = float(filtered["Sales"].sum())
profit = float(filtered["Profit"].sum())
orders = int(filtered["OrderID"].nunique())
customers = int(filtered["CustomerID"].nunique())
products = int(filtered["Product"].nunique())
aov = revenue / orders if orders else 0
margin = profit / revenue * 100 if revenue else 0

if page != "Dataset":
    a,b,c,d = st.columns(4)
    a.metric("Total revenue", f"{revenue:,.2f}")
    b.metric("Average order value", f"{aov:,.2f}")
    c.metric("Total customers", f"{customers:,}")
    d.metric("Active products", f"{products:,}")
    st.write("")

def chart_style(fig):
    fig.patch.set_facecolor("white")
    for ax in fig.axes:
        ax.set_facecolor("white")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", color="#e9edf5", linewidth=.7)
        ax.set_axisbelow(True)
        ax.tick_params(colors="#64748b", labelsize=8)
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

def heading(title, subtitle):
    st.markdown(f"### {title}")
    st.caption(subtitle)

if page == "Overview":
    left, right = st.columns([1.6,1], gap="large")
    with left:
        with st.container(border=True):
            heading("📈 Revenue trend", "Monthly revenue for the selected period")
            monthly = filtered.groupby("YearMonth", as_index=False)["Sales"].sum().sort_values("YearMonth")
            fig, ax = plt.subplots(figsize=(8,3.2))
            ax.plot(monthly["YearMonth"], monthly["Sales"], marker="o", linewidth=2.5)
            ax.fill_between(range(len(monthly)), monthly["Sales"].values, alpha=.08)
            ax.set_xticks(range(len(monthly)))
            ax.set_xticklabels(monthly["YearMonth"], rotation=35, ha="right")
            ax.set_ylabel("Revenue")
            chart_style(fig)
    with right:
        with st.container(border=True):
            heading("🌍 Revenue by country", "Top countries by revenue")
            country_sales = filtered.groupby("Country")["Sales"].sum().sort_values().tail(8)
            fig, ax = plt.subplots(figsize=(5,3.2))
            country_sales.plot(kind="barh", ax=ax)
            ax.set_xlabel("Revenue")
            ax.set_ylabel("")
            chart_style(fig)
    left, right = st.columns(2, gap="large")
    with left:
        with st.container(border=True):
            heading("📊 Category performance", "Revenue and profit by category")
            category = filtered.groupby("Category")[["Sales","Profit"]].sum().sort_values("Sales", ascending=False)
            fig, ax = plt.subplots(figsize=(6,3.2))
            category.plot(kind="bar", ax=ax)
            ax.set_ylabel("Amount")
            ax.tick_params(axis="x", rotation=20)
            ax.legend(["Revenue","Profit"], frameon=False)
            chart_style(fig)
    with right:
        with st.container(border=True):
            heading("🏆 Best-selling products", "Top 10 products ranked by revenue")
            best = filtered.groupby("Product", as_index=False).agg(Quantity_Sold=("Quantity","sum"), Revenue=("Sales","sum"), Profit=("Profit","sum")).sort_values("Revenue", ascending=False).head(10)
            best = best.rename(columns={"Quantity_Sold":"Quantity sold"})
            st.dataframe(best, use_container_width=True, hide_index=True)
    p1,p2,p3 = st.columns(3)
    p1.metric("Total profit", f"{profit:,.2f}")
    p2.metric("Profit margin", f"{margin:.1f}%")
    p3.metric("Distinct orders", f"{orders:,}")

elif page == "Revenue Analytics":
    left,right = st.columns(2, gap="large")
    with left:
        with st.container(border=True):
            heading("Monthly revenue", "Revenue by calendar month")
            monthly = filtered.groupby("YearMonth")["Sales"].sum().sort_index()
            fig,ax=plt.subplots(figsize=(7,3.5))
            monthly.plot(kind="line", marker="o", ax=ax)
            ax.set_ylabel("Revenue")
            ax.tick_params(axis="x", rotation=35)
            chart_style(fig)
    with right:
        with st.container(border=True):
            heading("Revenue by sales channel", "Compare sales channels")
            ch = filtered.groupby("SalesChannel")["Sales"].sum().sort_values(ascending=False)
            fig,ax=plt.subplots(figsize=(7,3.5))
            ch.plot(kind="bar", ax=ax)
            ax.set_ylabel("Revenue")
            ax.tick_params(axis="x", rotation=15)
            chart_style(fig)
    summary = filtered.groupby("Country").agg(Revenue=("Sales","sum"), Profit=("Profit","sum"), Orders=("OrderID","nunique"), Customers=("CustomerID","nunique")).sort_values("Revenue",ascending=False).reset_index()
    with st.container(border=True):
        heading("Country summary", "Revenue, profit, orders and customers by country")
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.download_button("⬇ Download country summary", summary.to_csv(index=False).encode("utf-8"), "shopsense_country_summary.csv", "text/csv")

elif page == "Product Performance":
    summary = filtered.groupby(["Product","Category"], as_index=False).agg(Quantity_Sold=("Quantity","sum"), Revenue=("Sales","sum"), Profit=("Profit","sum"), Orders=("OrderID","nunique")).sort_values("Revenue",ascending=False)
    left,right=st.columns(2,gap="large")
    with left:
        with st.container(border=True):
            heading("Top products by revenue", "Top 10 products in this selection")
            top=summary.head(10).sort_values("Revenue")
            fig,ax=plt.subplots(figsize=(7,4))
            ax.barh(top["Product"],top["Revenue"])
            ax.set_xlabel("Revenue")
            chart_style(fig)
    with right:
        with st.container(border=True):
            heading("Top products by profit", "Products ranked by profit")
            top=summary.sort_values("Profit").tail(10)
            fig,ax=plt.subplots(figsize=(7,4))
            ax.barh(top["Product"],top["Profit"])
            ax.set_xlabel("Profit")
            chart_style(fig)
    with st.container(border=True):
        heading("Product performance table", "Compare product-level results")
        st.dataframe(summary.rename(columns={"Quantity_Sold":"Quantity sold"}), use_container_width=True, hide_index=True)
        st.download_button("⬇ Download product report", summary.to_csv(index=False).encode("utf-8"), "shopsense_product_report.csv", "text/csv")

elif page == "Customers & Orders":
    left,right=st.columns(2,gap="large")
    with left:
        with st.container(border=True):
            heading("Orders by payment method", "Distinct order count")
            payment=filtered.groupby("PaymentMethod")["OrderID"].nunique().sort_values(ascending=False)
            fig,ax=plt.subplots(figsize=(7,3.5))
            payment.plot(kind="bar",ax=ax)
            ax.set_ylabel("Orders")
            ax.tick_params(axis="x",rotation=20)
            chart_style(fig)
    with right:
        with st.container(border=True):
            heading("Orders by sales channel", "Distinct orders by channel")
            channels=filtered.groupby("SalesChannel")["OrderID"].nunique().sort_values(ascending=False)
            fig,ax=plt.subplots(figsize=(7,3.5))
            channels.plot(kind="bar",ax=ax)
            ax.set_ylabel("Orders")
            ax.tick_params(axis="x",rotation=15)
            chart_style(fig)
    customer_summary=filtered.groupby("CustomerID",as_index=False).agg(Orders=("OrderID","nunique"),Revenue=("Sales","sum"),Profit=("Profit","sum"),Last_Order=("OrderDate","max")).sort_values("Revenue",ascending=False)
    with st.container(border=True):
        heading("Customer summary", "Customer-level order and revenue summary")
        st.dataframe(customer_summary,use_container_width=True,hide_index=True)
        st.download_button("⬇ Download customer report",customer_summary.to_csv(index=False).encode("utf-8"),"shopsense_customer_summary.csv","text/csv")

elif page == "Dataset":
    with st.container(border=True):
        heading("Filtered dataset", "Records matching the selected filters")
        st.dataframe(filtered,use_container_width=True,hide_index=True)
        st.caption(f"{len(filtered):,} rows • {len(filtered.columns)} columns")
        st.download_button("⬇ Download filtered dataset",filtered.to_csv(index=False).encode("utf-8"),"shopsense_filtered_orders.csv","text/csv")
    with st.container(border=True):
        heading("Data quality", "Basic checks after cleaning")
        q1,q2,q3=st.columns(3)
        q1.metric("Duplicate rows",int(filtered.duplicated().sum()))
        q2.metric("Missing cells",int(filtered.isna().sum().sum()))
        q3.metric("Columns",len(filtered.columns))

elif page == "SQL Business Insights":
    st.title("🧠 SQL Business Insights")
    st.write("Business data ko SQL queries se analyse karo.")

    connection = sqlite3.connect("shopsense.db")

    try:
        # 1. Total Revenue
        revenue = pd.read_sql_query("""
            SELECT ROUND(SUM(Sales), 2) AS Total_Revenue
            FROM orders
        """, connection)

        # 2. Total Orders
        orders = pd.read_sql_query("""
            SELECT COUNT(DISTINCT OrderID) AS Total_Orders
            FROM orders
        """, connection)

        # 3. Total Customers
        customers = pd.read_sql_query("""
            SELECT COUNT(DISTINCT CustomerID) AS Total_Customers
            FROM orders
        """, connection)

        # 4. Top 5 Products by Revenue
        top_products = pd.read_sql_query("""
            SELECT Product, ROUND(SUM(Sales), 2) AS Revenue
            FROM orders
            GROUP BY Product
            ORDER BY Revenue DESC
            LIMIT 5
        """, connection)

        # 5. Average Order Value
        aov = pd.read_sql_query("""
            SELECT ROUND(
                SUM(Sales) * 1.0 / NULLIF(COUNT(DISTINCT OrderID), 0), 2
            ) AS Average_Order_Value
            FROM orders
        """, connection)

    finally:
        connection.close()
elif page == "Business Insights & Recommendations":
 st.title("💡 Business Insights & Recommendations")
 st.write("Filtered sales data se business performance samjho aur actionable recommendations pao.")

 
if filtered.empty:
    st.warning("Selected filters ke liye koi data available nahi hai.")
else:
    # 1. Category performance
    category_summary = (
        filtered.groupby("Category", as_index=False)
        .agg(
            Revenue=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Quantity_Sold=("Quantity", "sum")
        )
        .sort_values("Revenue", ascending=False)
    )

    # 2. Country performance
    country_summary = (
        filtered.groupby("Country", as_index=False)
        .agg(
            Revenue=("Sales", "sum"),
            Profit=("Profit", "sum")
        )
        .sort_values("Revenue", ascending=False)
    )

    # 3. Product performance and profit margin
    product_summary = (
        filtered.groupby("Product", as_index=False)
        .agg(
            Revenue=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Quantity_Sold=("Quantity", "sum")
        )
    )

    product_summary["Profit_Margin_%"] = (
        product_summary["Profit"]
        .div(product_summary["Revenue"].replace(0, float("nan")))
        .mul(100)
        .round(2)
    )

    # 4. Monthly revenue
    monthly_revenue = (
        filtered.groupby("YearMonth", as_index=False)
        .agg(Revenue=("Sales", "sum"))
        .sort_values("YearMonth")
    )

    # KPI cards
    total_revenue = filtered["Sales"].sum()
    total_profit = filtered["Profit"].sum()
    profit_margin = (
        total_profit / total_revenue * 100
        if total_revenue != 0 else 0
    )

    c1, c2, c3 = st.columns(3)

    c1.metric("Total Revenue", f"₹{total_revenue:,.2f}")
    c2.metric("Total Profit", f"₹{total_profit:,.2f}")
    c3.metric("Profit Margin", f"{profit_margin:.2f}%")

    st.markdown("---")

    # Category insights
    st.subheader("📦 Category Performance")

    left, right = st.columns(2, gap="large")

    with left:
        st.write("**Revenue by Category**")
        st.bar_chart(category_summary.set_index("Category")["Revenue"])

    with right:
        st.write("**Profit by Category**")
        st.bar_chart(category_summary.set_index("Category")["Profit"])

    best_category = category_summary.iloc[0]

    st.info(
        f"Highest-revenue category: **{best_category['Category']}** "
        f"with revenue of ₹{best_category['Revenue']:,.2f}."
    )

    st.dataframe(
        category_summary,
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")

    # Country insights
    st.subheader("🌍 Country Performance")

    best_country = country_summary.iloc[0]

    st.success(
        f"Highest-revenue country: **{best_country['Country']}** "
        f"with revenue of ₹{best_country['Revenue']:,.2f}."
    )

    st.bar_chart(country_summary.set_index("Country")["Revenue"])

    st.dataframe(
        country_summary,
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")

    # Product insights
    st.subheader("🏆 Product Profitability")

    low_margin_products = (
        product_summary[
            (product_summary["Revenue"] > 0)
            & (product_summary["Profit_Margin_%"] < 10)
        ]
        .sort_values("Revenue", ascending=False)
    )

    if not low_margin_products.empty:
        st.warning(
            "These products have a profit margin below 10%. "
            "Review their costs, pricing and discounts."
        )

        st.dataframe(
            low_margin_products,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info(
            "No products with positive revenue and a profit margin "
            "below 10% were found in this selection."
        )

    st.markdown("---")

    # Monthly revenue trend
    st.subheader("📈 Monthly Revenue Trend")

    if not monthly_revenue.empty:
        st.line_chart(
            monthly_revenue.set_index("YearMonth")["Revenue"]
        )

        if len(monthly_revenue) >= 2:
            previous_revenue = monthly_revenue.iloc[-2]["Revenue"]
            latest_revenue = monthly_revenue.iloc[-1]["Revenue"]

            if previous_revenue != 0:
                change = (
                    (latest_revenue - previous_revenue)
                    / abs(previous_revenue)
                ) * 100

                if change > 0:
                    st.success(
                        f"Revenue increased by {change:.2f}% "
                        "compared with the previous available month."
                    )
                elif change < 0:
                    st.warning(
                        f"Revenue decreased by {abs(change):.2f}% "
                        "compared with the previous available month."
                    )
                else:
                    st.info(
                        "Revenue remained unchanged compared with "
                        "the previous available month."
                    )

    st.markdown("---")

    # Recommendations
    st.subheader("🎯 Business Recommendations")

    st.markdown(
        f"""
        1. **Focus on the leading category:** Review what's driving
           revenue in {best_category['Category']} and identify ways
           to sustain its performance.

        2. **Review country-level performance:** Investigate why
           {best_country['Country']} generates the highest revenue
           in the selected data.

        3. **Improve product profitability:** Review costs, pricing
           and discounting for products with low profit margins.

        4. **Monitor monthly trends:** Compare revenue across months
           to identify periods of growth and decline.

        5. **Use filters for comparisons:** Repeat the analysis by
           category, country and sales channel to identify
           differences in performance.
        """
    )

    # Download reports
    st.download_button(
        "⬇ Download Category Report",
        category_summary.to_csv(index=False).encode("utf-8"),
        "shopsense_category_insights.csv",
        "text/csv"
    )

    st.download_button(
        "⬇ Download Product Profitability Report",
        product_summary.to_csv(index=False).encode("utf-8"),
        "shopsense_product_profitability.csv",
        "text/csv"
    )


   # KPI cards
    
    c1, c2, c3, c4 = st.columns(4)

    revenue_value = float(revenue.iloc[0, 0]) if isinstance(revenue, pd.DataFrame) else float(revenue)
    orders_value = int(orders.iloc[0, 0]) if isinstance(orders, pd.DataFrame) else int(orders)
    customers_value = int(customers.iloc[0, 0]) if isinstance(customers, pd.DataFrame) else int(customers)
    aov_value = float(aov.iloc[0, 0]) if isinstance(aov, pd.DataFrame) else float(aov)

    c1.metric("Total Revenue", f"₹{revenue_value:,.2f}")
    c2.metric("Total Orders", f"{orders_value:,}")
    c3.metric("Total Customers", f"{customers_value:,}")
    c4.metric("Average Order Value", f"₹{aov_value:,.2f}")
    st.subheader("🏆 Top 5 Products by Revenue")
    top_products = pd.read_sql_query("""
    SELECT Product, ROUND(SUM(Sales), 2) AS Revenue
    FROM orders
    GROUP BY Product
    ORDER BY Revenue DESC
    LIMIT 5
""", sqlite3.connect("shopsense.db"))
    st.dataframe(top_products, hide_index=True, use_container_width=True)

    st.download_button(
        "⬇️ Download Top Products",
        top_products.to_csv(index=False).encode("utf-8"),
        "top_products.csv",
        "text/csv"
    )


st.markdown("""
<style>
.stApp {
    background-color: #f4f6fb;
    color: #1e293b;
}

[data-testid="stSidebar"] {
    background-color: #111827;
}

[data-testid="stSidebar"] * {
    color: #e5e7eb;
}

.stApp h1,
.stApp h2,
.stApp h3,
.stApp p,
.stApp label,
.stApp span,
.stApp div {
    color: #1e293b;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div {
    color: #e5e7eb;
}

[data-testid="stMetric"] {
    background-color: #ffffff;
    border: 1px solid #e5eaf2;
    padding: 1rem;
    border-radius: 15px;
}

[data-testid="stMetricLabel"] *,
[data-testid="stMetricValue"] *,
[data-testid="stMetricDelta"] * {
    color: #1e293b !important;
}

.stCaption,
small {
    color: #64748b !important;
}
/* Download button styling */
.stDownloadButton > button {
    background-color: #2563eb !important;
    color: #ffffff !important;
    border: 1px solid #2563eb !important;
    border-radius: 10px !important;
    padding: 0.65rem 1rem !important;
    font-weight: 600 !important;
}

.stDownloadButton > button:hover {
    background-color: #1d4ed8 !important;
    color: #ffffff !important;
    border-color: #1d4ed8 !important;
}

.stDownloadButton > button p,
.stDownloadButton > button span,
.stDownloadButton > button svg {
    color: #ffffff !important;
    fill: #ffffff !important;
}
</style>
""", unsafe_allow_html=True) 
