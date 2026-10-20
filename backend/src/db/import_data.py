r"""
清洗 Olist 巴西电商数据并导入 SQLite
- 表名/字段名保持英文（行业惯例）
- 数据内容中文化（品类、城市、州、支付方式、订单状态）
运行：cd D:\X\Y\Z-ChatBI\backend\src && python -m db.import_data
"""
import sqlite3
import os
import pandas as pd

# ==================== 路径配置 ====================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(CURRENT_DIR, "chatbi.db")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(CURRENT_DIR)))
RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw")


# ==================== 中文化映射表 ====================

CATEGORY_MAP = {
    "beleza_saude": "美妆健康",
    "health_beauty": "美妆健康",
    "esporte_lazer": "运动户外",
    "sports_leisure": "运动户外",
    "informatica_acessorios": "电脑配件",
    "computers_accessories": "电脑配件",
    "moveis_decoracao": "家具装饰",
    "furniture_decor": "家具装饰",
    "utilidades_domesticas": "家居日用",
    "housewares": "家居日用",
    "relogios_presentes": "手表礼品",
    "watches_gifts": "手表礼品",
    "telefonia": "手机通讯",
    "telephony": "手机通讯",
    "ferramentas_jardim": "工具园艺",
    "garden_tools": "工具园艺",
    "automotivo": "汽车用品",
    "auto": "汽车用品",
    "brinquedos": "玩具",
    "toys": "玩具",
    "cool_stuff": "潮玩",
    "perfumaria": "香水",
    "perfumery": "香水",
    "bebes": "母婴",
    "baby": "母婴",
    "eletronicos": "电子产品",
    "electronics": "电子产品",
    "papelaria": "文具",
    "stationery": "文具",
    "fashion_bolsas_e_acessorios": "时尚箱包",
    "fashion_bags_accessories": "时尚箱包",
    "fashion_calcados": "时尚鞋履",
    "fashion_shoes": "时尚鞋履",
    "fashion_roupa_masculina": "男装",
    "fashion_male_clothing": "男装",
    "fashion_roupa_feminina": "女装",
    "fashion_female_clothing": "女装",
    "fashion_underwear_e_moda_praia": "内衣泳装",
    "fashion_underwear_beach": "内衣泳装",
    "fashion_esporte": "运动服饰",
    "fashion_sport": "运动服饰",
    "pet_shop": "宠物用品",
    "livros_interesse_geral": "图书",
    "books_general_interest": "图书",
    "construcao_ferramentas_construcao": "建材工具",
    "construction_tools_construction": "建材工具",
    "malas_acessorios": "箱包配件",
    "luggage_accessories": "箱包配件",
    "casa_construcao": "家装",
    "home_construction": "家装",
    "market_place": "综合市场",
    "la_cuisine": "厨房用品",
    "kitchen_dining_laundry_garden_furniture": "厨卫家具",
    "audio": "音频设备",
    "dvds_blu_ray": "影音光盘",
    "cds_dvds_musicais": "音乐光盘",
    "artigos_de_festas": "派对用品",
    "party_supplies": "派对用品",
    "artes": "艺术品",
    "art": "艺术品",
    "artigos_de_natal": "圣诞用品",
    "christmas_supplies": "圣诞用品",
    "bebidas": "饮品",
    "drinks": "饮品",
    "alimentos": "食品",
    "food": "食品",
    "cama_mesa_banho": "床品浴品",
    "bed_bath_table": "床品浴品",
    "climatizacao": "空调制冷",
    "air_conditioning": "空调制冷",
    "consoles_games": "游戏主机",
    "console_games": "游戏主机",
    "industria_comercio_e_negocios": "工业商业",
    "industry_commerce_and_business": "工业商业",
    "instrumentos_musicais": "乐器",
    "musical_instruments": "乐器",
    "livros_importados": "进口图书",
    "imported_books": "进口图书",
    "moveis_escritorio": "办公家具",
    "office_furniture": "办公家具",
    "moveis_sala": "客厅家具",
    "living_room_furniture": "客厅家具",
    "moveis_quarto": "卧室家具",
    "bedroom_furniture": "卧室家具",
    "papelaria_importada": "进口文具",
    "imported_stationery": "进口文具",
    "portateis_casa_forno_e_cafe": "小家电",
    "small_appliances": "小家电",
    "portateis_cozinha_e_preparadores_de_alimentos": "厨房小电",
    "small_appliances_home_oven_and_coffee": "厨房小电",
    "seguros_e_servicos": "保险服务",
    "security_and_services": "保险服务",
    "sinalizacao_e_seguranca": "安防标识",
    "signaling_and_security": "安防标识",
    "tablets_impressao_imagem": "平板打印",
    "tablets_printing_image": "平板打印",
    "telefonia_fixa": "固话",
    "fixed_telephony": "固话",
    "fashion": "时尚",
    "eletrodomesticos": "家电",
    "eletrodomesticos_2": "家电",
    "eletroportateis": "小家电",
    "construcao_ferramentas_seguranca": "安防工具",
    "construcao_ferramentas_ferramentas": "五金工具",
    "construcao_ferramentas_iluminacao": "照明工具",
    "construcao_ferramentas_jardim": "园艺工具",
    "pcs": "台式电脑",
    "pc_gamer": "游戏电脑",
    "agro_industria_e_comercio": "农业工业",
    "moveis_cozinha_area_de_servico_jantar_e_jardim": "厨房家具",
    "livros_tecnicos": "技术图书",
    "casa_conforto": "家居舒适",
    "casa_conforto_2": "家居舒适",
    "alimentos_bebidas": "食品饮料",
    "musica": "音乐",
    "fashion_roupa_infanto_juvenil": "童装",
    "artes_e_artesanato": "手工艺品",
    "cine_foto": "影音摄影",
    "fraldas_higiene": "母婴卫生",
    "flores": "鲜花",
    "moveis_colchao_e_estofado": "床垫沙发",
    "unknown": "未知",
}

CITY_MAP = {
    "sao paulo": "上海",
    "rio de janeiro": "北京",
    "belo horizonte": "广州",
    "brasilia": "深圳",
    "curitiba": "杭州",
    "porto alegre": "成都",
    "recife": "武汉",
    "salvador": "南京",
    "fortaleza": "西安",
    "goiania": "重庆",
    "campinas": "苏州",
    "manaus": "天津",
    "natal": "长沙",
    "santo andre": "青岛",
    "guarulhos": "宁波",
    "niteroi": "厦门",
    "sao bernardo do campo": "合肥",
    "londrina": "福州",
    "duque de caxias": "济南",
    "nova iguacu": "大连",
    "sao jose dos pinhais": "无锡",
    "maua": "佛山",
    "osasco": "东莞",
    "ribeirao preto": "郑州",
    "sorocaba": "沈阳",
    "joinville": "昆明",
    "juiz de fora": "南昌",
    "uberlandia": "贵阳",
    "cuiaba": "南宁",
    "florianopolis": "珠海",
}

STATE_MAP = {
    "SP": "上海", "RJ": "北京", "MG": "广东", "DF": "广东",
    "PR": "浙江", "RS": "四川", "PE": "湖北", "BA": "江苏",
    "CE": "陕西", "GO": "重庆", "AM": "天津", "PA": "湖南",
    "SC": "山东", "ES": "福建", "MA": "安徽", "PB": "河南",
    "RN": "辽宁", "AL": "江西", "PI": "云南", "MT": "广西",
    "MS": "贵州", "SE": "山西", "TO": "河北", "RO": "吉林",
    "AC": "黑龙江", "AP": "内蒙古", "RR": "新疆",
}
PROVINCE_REGION_MAP = {
    # 华东
    "上海": "华东", "江苏": "华东", "浙江": "华东", "安徽": "华东",
    "福建": "华东", "江西": "华东", "山东": "华东",
    # 华北
    "北京": "华北", "天津": "华北", "河北": "华北", "山西": "华北", "内蒙古": "华北",
    # 华南
    "广东": "华南", "广西": "华南", "海南": "华南",
    # 华中
    "河南": "华中", "湖北": "华中", "湖南": "华中",
    # 西南
    "重庆": "西南", "四川": "西南", "贵州": "西南", "云南": "西南",
    # 西北
    "陕西": "西北", "甘肃": "西北", "青海": "西北", "宁夏": "西北", "新疆": "西北",
    # 东北
    "辽宁": "东北", "吉林": "东北", "黑龙江": "东北",
}
PAYMENT_MAP = {
    "credit_card": "信用卡",
    "boleto": "银行转账",
    "voucher": "代金券",
    "debit_card": "借记卡",
    "not_defined": "未定义",
}

STATUS_MAP = {
    "delivered": "已完成",
    "shipped": "已发货",
    "canceled": "已取消",
    "unavailable": "无法送达",
    "invoiced": "已开票",
    "processing": "处理中",
    "created": "已创建",
    "approved": "已审批",
}


# ==================== 读取 CSV ====================
def load_csv(filename):
    path = os.path.join(RAW_DIR, filename)
    if not os.path.exists(path):
        print(f"   ⚠️ 文件不存在: {filename}")
        return None
    df = pd.read_csv(path)
    print(f"   ✅ {filename}: {len(df)} 行")
    return df


# ==================== 各表清洗 ====================
def clean_customers(df):
    df = df.copy()
    df = df.rename(columns={
        "customer_zip_code_prefix": "zip_code",
        "customer_city": "city",
        "customer_state": "state",
    })
    return df


def clean_orders(df):
    df = df.copy()
    date_cols = [
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df = df[df["order_purchase_timestamp"].dt.year == 2017]
    df["order_year_month"] = df["order_purchase_timestamp"].dt.strftime("%Y-%m")
    df["order_year"] = df["order_purchase_timestamp"].dt.year
    df["order_quarter"] = df["order_purchase_timestamp"].dt.quarter
    df["order_month"] = df["order_purchase_timestamp"].dt.month
    df["order_weekday"] = df["order_purchase_timestamp"].dt.weekday

    for col in date_cols:
        df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")

    return df


def clean_order_items(df):
    df = df.copy()
    df = df.rename(columns={
        "order_item_id": "item_seq",
        "shipping_limit_date": "shipping_limit",
    })
    df["shipping_limit"] = pd.to_datetime(df["shipping_limit"], errors="coerce")
    df["shipping_limit"] = df["shipping_limit"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def clean_products(df):
    df = df.copy()
    df = df.rename(columns={
        "product_name_lenght": "name_length",
        "product_description_lenght": "description_length",
        "product_photos_qty": "photos_qty",
        "product_weight_g": "weight_g",
        "product_length_cm": "length_cm",
        "product_height_cm": "height_cm",
        "product_width_cm": "width_cm",
    })
    df["product_category_name"] = df["product_category_name"].fillna("未知")
    return df


def clean_sellers(df):
    df = df.copy()
    df = df.rename(columns={
        "seller_zip_code_prefix": "zip_code",
        "seller_city": "city",
        "seller_state": "state",
    })
    return df


def clean_reviews(df):
    df = df.copy()
    date_cols = ["review_creation_date", "review_answer_timestamp"]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors="coerce")
        df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
    df = df.dropna(subset=["review_score"])
    df["review_score"] = df["review_score"].astype(int)
    return df


def clean_payments(df):
    return df.copy()


def clean_category(df):
    return df.copy()


def clean_geolocation(df):
    df = df.copy()
    df = df.groupby("geolocation_zip_code_prefix").agg({
        "geolocation_lat": "mean",
        "geolocation_lng": "mean",
        "geolocation_city": "first",
        "geolocation_state": "first",
    }).reset_index()
    df = df.rename(columns={
        "geolocation_zip_code_prefix": "zip_code",
        "geolocation_lat": "lat",
        "geolocation_lng": "lng",
        "geolocation_city": "city",
        "geolocation_state": "state",
    })
    df["lat"] = df["lat"].round(6)
    df["lng"] = df["lng"].round(6)
    return df


# ==================== 中文化处理 ====================
# ==================== 中国城市池 ====================
CN_CITIES = [
    # 一线
    "上海", "北京", "广州", "深圳",
    # 新一线
    "成都", "杭州", "重庆", "西安", "苏州", "武汉", "南京", "天津", "长沙", "郑州",
    "东莞", "青岛", "宁波", "佛山", "合肥",
    # 二线
    "厦门", "大连", "福州", "无锡", "沈阳", "昆明", "哈尔滨", "长春", "南昌", "济南",
    "贵阳", "南宁", "温州", "石家庄", "泉州", "珠海", "常州", "徐州", "烟台", "嘉兴",
    "南通", "金华", "绍兴", "台州", "中山", "惠州", "潍坊", "临沂", "洛阳", "扬州",
    "盐城", "泰州",
    # 三线
    "镇江", "淮安", "连云港", "宿迁", "芜湖", "蚌埠", "淮南", "马鞍山", "安庆", "黄山",
    "滁州", "阜阳", "宿州", "六安", "亳州", "池州", "宣城", "湖州", "衢州", "丽水",
    "舟山", "景德镇", "萍乡", "新余", "鹰潭", "赣州", "吉安", "宜春", "抚州", "上饶",
    "淄博", "枣庄", "东营", "济宁", "泰安", "威海", "日照", "莱芜", "德州", "聊城",
    "滨州", "菏泽", "开封", "平顶山", "安阳", "鹤壁", "新乡", "焦作", "濮阳", "许昌",
    "漯河", "三门峡", "南阳", "商丘", "信阳", "周口", "驻马店", "黄石", "十堰", "宜昌",
    "襄阳", "鄂州", "荆门", "孝感", "荆州", "黄冈", "咸宁", "随州", "株洲", "湘潭",
    "衡阳", "邵阳", "岳阳", "常德", "张家界", "益阳", "郴州", "永州", "怀化", "娄底",
    "韶关", "珠海", "汕头", "佛山", "江门", "湛江", "茂名", "肇庆", "惠州", "梅州",
    "汕尾", "河源", "阳江", "清远", "东莞", "中山", "潮州", "揭阳", "云浮",
]
def build_city_map(series):
    """
    根据城市数据量，动态生成巴西→中国城市映射
    数据量最大的巴西城市 → 一线城市
    数据量最小的巴西城市 → 三线城市
    """
    # 统计每个巴西城市的数据量，按从多到少排序
    city_counts = series.str.lower().value_counts()
    br_cities = city_counts.index.tolist()
    city_map = {}
    for i, br_city in enumerate(br_cities):
        if i < len(CN_CITIES):
            city_map[br_city] = CN_CITIES[i]
        else:
            # 城市池用完了，归为"其他城市"
            city_map[br_city] = "其他城市"
    return city_map
def translate_data(cleaned):
    """把巴西数据翻译成中文，表名字段名不动"""

    # ---------- customers ----------
    if "customers" in cleaned and cleaned["customers"] is not None:
        df = cleaned["customers"]
        city_map = build_city_map(df["city"])
        df["city"] = df["city"].str.lower().map(city_map).fillna("其他城市")
        df["province"] = df["state"].str.upper().map(STATE_MAP).fillna(df["state"])
        df["region"] = df["province"].map(PROVINCE_REGION_MAP).fillna("其他")
        # 不删 state，留着也不会报错

    # ---------- sellers ----------
    if "sellers" in cleaned and cleaned["sellers"] is not None:
        df = cleaned["sellers"]
        city_map = build_city_map(df["city"])
        df["city"] = df["city"].str.lower().map(city_map).fillna("其他城市")
        df["province"] = df["state"].str.upper().map(STATE_MAP).fillna(df["state"])
        df["region"] = df["province"].map(PROVINCE_REGION_MAP).fillna("其他")
        # 不删 state

    # ---------- products ----------
    if "products" in cleaned and cleaned["products"] is not None:
        df = cleaned["products"]
        df["product_category_name"] = (
            df["product_category_name"].map(CATEGORY_MAP).fillna(df["product_category_name"])
        )

    # ---------- payments ----------
    if "payments" in cleaned and cleaned["payments"] is not None:
        df = cleaned["payments"]
        df["payment_type"] = df["payment_type"].map(PAYMENT_MAP).fillna(df["payment_type"])

    # ---------- orders ----------
    if "orders" in cleaned and cleaned["orders"] is not None:
        df = cleaned["orders"]
        df["order_status"] = df["order_status"].map(STATUS_MAP).fillna(df["order_status"])

    # ---------- category_translation ----------
    if "category_translation" in cleaned and cleaned["category_translation"] is not None:
        df = cleaned["category_translation"]
        df["product_category_name"] = (
            df["product_category_name"].map(CATEGORY_MAP).fillna(df["product_category_name"])
        )
        df["product_category_name_english"] = (
            df["product_category_name_english"].map(CATEGORY_MAP).fillna(df["product_category_name_english"])
        )

    return cleaned


# ==================== 写入 SQLite ====================
def write_table(df, table_name, conn):
    if df is None or df.empty:
        print(f"   ⏭️ 跳过空表: {table_name}")
        return
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    print(f"   ✅ {table_name}: {len(df)} 行")


# ==================== 主流程 ====================
def main():
    if not os.path.exists(RAW_DIR):
        print(f"❌ 原始数据目录不存在: {RAW_DIR}")
        print("   请先运行 download_data.py")
        return

    print("🚀 开始清洗并导入数据")
    print("=" * 50)

    # ---------- 1. 读取 ----------
    print("\n📂 读取 CSV：")
    raw = {
        "customers": load_csv("olist_customers_dataset.csv"),
        "orders": load_csv("olist_orders_dataset.csv"),
        "order_items": load_csv("olist_order_items_dataset.csv"),
        "products": load_csv("olist_products_dataset.csv"),
        "sellers": load_csv("olist_sellers_dataset.csv"),
        "reviews": load_csv("olist_order_reviews_dataset.csv"),
        "payments": load_csv("olist_order_payments_dataset.csv"),
        "category": load_csv("product_category_name_translation.csv"),
        "geolocation": load_csv("olist_geolocation_dataset.csv"),
    }

    # ---------- 2. 清洗 ----------
    print("\n🧹 清洗数据：")
    cleaned = {
        "customers": clean_customers(raw["customers"]),
        "orders": clean_orders(raw["orders"]),
        "order_items": clean_order_items(raw["order_items"]),
        "products": clean_products(raw["products"]),
        "sellers": clean_sellers(raw["sellers"]),
        "reviews": clean_reviews(raw["reviews"]),
        "payments": clean_payments(raw["payments"]),
        "category_translation": clean_category(raw["category"]),
        "geolocation": clean_geolocation(raw["geolocation"]),
    }
    print("   ✅ 清洗完成")

    # ---------- 3. 中文化 ----------
    print("\n🌐 中文化数据：")
    cleaned = translate_data(cleaned)
    print("   ✅ 中文化完成")
    # ---------- 3.5 同步过滤关联表 ----------
    print("\n🔗 同步过滤关联表：")
    valid_order_ids = set(cleaned["orders"]["order_id"])
    for table in ["order_items", "payments", "reviews"]:
        if table in cleaned and cleaned[table] is not None:
            before = len(cleaned[table])
            cleaned[table] = cleaned[table][cleaned[table]["order_id"].isin(valid_order_ids)]
            after = len(cleaned[table])
            print(f"   ✅ {table}: {before} → {after} 行")
    # ---------- 4. 写入 SQLite ----------
    print("\n💾 写入 SQLite：")
    conn = sqlite3.connect(DB_PATH)
    for name, df in cleaned.items():
        if name == "category_translation":
            print(f"   ⏭️ 跳过: {name}")
            continue
        write_table(df, name, conn)
    conn.commit()
    # ---------- 5. 验证 ----------
    print("\n📊 验证数据：")
    cursor = conn.cursor()

    tables = ["customers", "orders", "order_items", "products",
              "sellers", "reviews", "payments", "geolocation"]
    for t in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"   {t}: {cursor.fetchone()[0]} 行")

    print("\n📈 按季度销售额（已完成订单）：")
    cursor.execute("""
        SELECT
            o.order_quarter as quarter,
            COUNT(DISTINCT o.order_id) as order_count,
            ROUND(SUM(oi.price), 2) as total_sales
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.order_status = '已完成'
        GROUP BY o.order_quarter
        ORDER BY o.order_quarter
    """)
    for row in cursor.fetchall():
        print(f"   Q{row[0]}: {row[1]} 订单, 销售额 {row[2]}")

    print("\n📈 各品类销售额 TOP 5：")
    cursor.execute("""
        SELECT
            p.product_category_name as category,
            ROUND(SUM(oi.price), 2) as total_sales
        FROM order_items oi
        JOIN products p ON oi.product_id = p.product_id
        GROUP BY p.product_category_name
        ORDER BY total_sales DESC
        LIMIT 5
    """)
    for row in cursor.fetchall():
        print(f"   {row[0]}: {row[1]}")

    print("\n📈 各城市客户数 TOP 5：")
    cursor.execute("""
        SELECT city, COUNT(*) as cnt
        FROM customers
        GROUP BY city
        ORDER BY cnt DESC
        LIMIT 5
    """)
    for row in cursor.fetchall():
        print(f"   {row[0]}: {row[1]}")

    conn.close()
    print("\n" + "=" * 50)
    print("✅ 数据导入完成！")
    print(f"📁 数据库位置: {DB_PATH}")


if __name__ == "__main__":
    main()