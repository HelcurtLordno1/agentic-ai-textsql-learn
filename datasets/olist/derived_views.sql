CREATE VIEW geo_zip_centroids AS
SELECT
    geolocation_zip_code_prefix,
    AVG(geolocation_lat) AS latitude,
    AVG(geolocation_lng) AS longitude,
    MIN(geolocation_city) AS representative_city,
    MIN(geolocation_state) AS representative_state,
    COUNT(*) AS source_row_count
FROM olist_geolocation_dataset
WHERE geolocation_lat BETWEEN -34.0 AND 6.0
  AND geolocation_lng BETWEEN -74.0 AND -34.0
GROUP BY geolocation_zip_code_prefix;

CREATE VIEW order_item_totals AS
SELECT
    order_id,
    COUNT(*) AS item_count,
    SUM(price_cents) AS product_revenue_cents,
    SUM(freight_value_cents) AS freight_cents
FROM olist_order_items_dataset
GROUP BY order_id;

CREATE VIEW order_payment_totals AS
SELECT
    order_id,
    COUNT(*) AS payment_row_count,
    COUNT(DISTINCT payment_type) AS distinct_payment_type_count,
    SUM(payment_value_cents) AS paid_value_cents
FROM olist_order_payments_dataset
GROUP BY order_id;

CREATE VIEW order_review_summary AS
SELECT
    order_id,
    COUNT(*) AS review_row_count,
    AVG(review_score) AS average_review_score,
    MIN(review_score) AS minimum_review_score,
    MAX(review_score) AS maximum_review_score
FROM olist_order_reviews_dataset
GROUP BY order_id;

CREATE VIEW order_delivery_facts AS
SELECT
    order_id,
    customer_id,
    order_status,
    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    CASE
        WHEN order_delivered_customer_date IS NOT NULL
        THEN julianday(order_delivered_customer_date) - julianday(order_purchase_timestamp)
    END AS delivery_days,
    CASE
        WHEN order_delivered_customer_date IS NOT NULL
        THEN julianday(order_delivered_customer_date) - julianday(order_estimated_delivery_date)
    END AS delay_days,
    CASE
        WHEN order_delivered_customer_date IS NOT NULL
         AND order_delivered_customer_date > order_estimated_delivery_date THEN 1
        WHEN order_delivered_customer_date IS NOT NULL THEN 0
    END AS is_late_delivered
FROM olist_orders_dataset;

CREATE VIEW customer_order_facts AS
SELECT
    c.customer_unique_id,
    MIN(o.order_purchase_timestamp) AS first_order_timestamp,
    COUNT(DISTINCT o.order_id) AS order_count
FROM olist_customers_dataset AS c
JOIN olist_orders_dataset AS o ON o.customer_id = c.customer_id
GROUP BY c.customer_unique_id;

CREATE VIEW products_semantic AS
SELECT
    p.product_id,
    p.product_category_name,
    t.product_category_name_english,
    p.product_name_lenght AS product_name_length,
    p.product_description_lenght AS product_description_length,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm
FROM olist_products_dataset AS p
LEFT JOIN product_category_name_translation AS t
    ON t.product_category_name = p.product_category_name;
