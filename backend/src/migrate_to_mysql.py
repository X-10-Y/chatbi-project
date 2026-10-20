import sqlite3
import pandas as pd
from sqlalchemy import create_engine

# 改成你自己的密码
MYSQL_URL = "mysql+pymysql://root:Xyj060315@localhost:3306/chatbi?charset=utf8mb4"

sqlite_conn = sqlite3.connect("db/chatbi.db")
mysql_engine = create_engine(MYSQL_URL)

tables = ["customers", "orders", "order_items", "products",
          "sellers", "reviews", "payments", "geolocation"]

for table in tables:
    try:
        df = pd.read_sql(f"SELECT * FROM {table}", sqlite_conn)
        df.to_sql(table, mysql_engine, if_exists="replace", index=False)
        print(f"✅ {table}: {len(df)} 行")
    except Exception as e:
        print(f"❌ {table}: {e}")