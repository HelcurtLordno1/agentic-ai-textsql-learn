PRAGMA foreign_keys = ON;

CREATE TABLE olist_customers_dataset (
    customer_id TEXT PRIMARY KEY,
    customer_unique_id TEXT NOT NULL,
    customer_zip_code_prefix INTEGER NOT NULL,
    customer_city TEXT NOT NULL,
    customer_state TEXT NOT NULL
);

CREATE TABLE olist_orders_dataset (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES olist_customers_dataset(customer_id),
    order_status TEXT NOT NULL,
    order_purchase_timestamp TEXT NOT NULL,
    order_approved_at TEXT,
    order_delivered_carrier_date TEXT,
    order_delivered_customer_date TEXT,
    order_estimated_delivery_date TEXT NOT NULL
);

CREATE TABLE olist_products_dataset (
    product_id TEXT PRIMARY KEY,
    product_category_name TEXT,
    product_name_lenght INTEGER,
    product_description_lenght INTEGER,
    product_photos_qty INTEGER,
    product_weight_g INTEGER,
    product_length_cm INTEGER,
    product_height_cm INTEGER,
    product_width_cm INTEGER
);

CREATE TABLE olist_sellers_dataset (
    seller_id TEXT PRIMARY KEY,
    seller_zip_code_prefix INTEGER NOT NULL,
    seller_city TEXT NOT NULL,
    seller_state TEXT NOT NULL
);

CREATE TABLE olist_order_items_dataset (
    order_id TEXT NOT NULL REFERENCES olist_orders_dataset(order_id),
    order_item_id INTEGER NOT NULL,
    product_id TEXT NOT NULL REFERENCES olist_products_dataset(product_id),
    seller_id TEXT NOT NULL REFERENCES olist_sellers_dataset(seller_id),
    shipping_limit_date TEXT NOT NULL,
    price TEXT NOT NULL,
    freight_value TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    freight_value_cents INTEGER NOT NULL CHECK (freight_value_cents >= 0),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE olist_order_payments_dataset (
    order_id TEXT NOT NULL REFERENCES olist_orders_dataset(order_id),
    payment_sequential INTEGER NOT NULL,
    payment_type TEXT NOT NULL,
    payment_installments INTEGER NOT NULL,
    payment_value TEXT NOT NULL,
    payment_value_cents INTEGER NOT NULL CHECK (payment_value_cents >= 0),
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE olist_order_reviews_dataset (
    review_row_id INTEGER PRIMARY KEY,
    review_id TEXT NOT NULL,
    order_id TEXT NOT NULL REFERENCES olist_orders_dataset(order_id),
    review_score INTEGER NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date TEXT NOT NULL,
    review_answer_timestamp TEXT NOT NULL
);

CREATE TABLE olist_geolocation_dataset (
    geolocation_row_id INTEGER PRIMARY KEY,
    geolocation_zip_code_prefix INTEGER NOT NULL,
    geolocation_lat REAL NOT NULL,
    geolocation_lng REAL NOT NULL,
    geolocation_city TEXT NOT NULL,
    geolocation_state TEXT NOT NULL
);

CREATE TABLE product_category_name_translation (
    product_category_name TEXT PRIMARY KEY,
    product_category_name_english TEXT NOT NULL
);

CREATE TABLE build_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
