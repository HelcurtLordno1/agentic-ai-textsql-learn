# Metric definitions

- Product revenue: sum `price_cents` at item grain; freight is excluded.
- Freight: sum `freight_value_cents` at item grain and report separately.
- Paid value: sum payments after pre-aggregation by order.
- Repeat customer: more than one distinct order by `customer_unique_id`, never `customer_id`.
- Multi-payment method: more than one distinct `payment_type`, not merely multiple payment rows.
- Late delivery: delivered timestamp after estimated delivery date; undelivered/null rows excluded.
- Cancellation rate: canceled orders over an explicitly stated population; never call it return rate.
- Review score: aggregate review rows to order grain before joins that can fan out.

The machine-readable source of truth is `datasets/olist/business_glossary.yaml`.
