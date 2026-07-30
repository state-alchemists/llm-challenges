import re

ORDER_LINE = "2026-04-15T11:23:07Z INFO order placed  ORDER_ID=42-X9Q  customer=\"alice@example.com\"  amount=$1,283.45"

order_id_match = re.search(r"ORDER_ID=([A-Za-z0-9-]+)", ORDER_LINE)
customer_email_match = re.search(r"customer=\"([^\"]+)\"" , ORDER_LINE)

order_id = order_id_match.group(1) if order_id_match else "N/A"
customer_email = customer_email_match.group(1) if customer_email_match else "N/A"

with open("answer.txt", "w") as f:
    f.write(f"order_id={order_id}\n")
    f.write(f"customer={customer_email}\n")