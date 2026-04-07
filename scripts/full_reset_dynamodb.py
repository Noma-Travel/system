#!/usr/bin/env python3
"""
Full reset of NOMA production DynamoDB data tables.
Clears: entities, rel, data, chat. Does NOT touch blueprints.
Uses AWS profile 'noma' and region us-east-1.

To sign up again with the same email, also delete the Cognito user:
  python scripts/delete_cognito_user_by_email.py you@example.com
"""
import boto3
import sys

REGION = "us-east-1"
PROFILE = "noma"

TABLES = [
    ("noma-prod_entities", "index", "_id"),
    ("noma-prod_rel", "index", "rel"),
    ("noma-prod_data", "portfolio_index", "doc_index"),
    ("noma-prod_chat", "index", "entity_index"),
]


def clear_table(dynamodb, table_name, pk_name, sk_name):
    table = dynamodb.Table(table_name)
    count = 0
    # Use placeholders for attribute names (e.g. _id is reserved)
    names = {"#pk": pk_name, "#sk": sk_name}
    scan_kw = {"ProjectionExpression": "#pk, #sk", "ExpressionAttributeNames": names}
    while True:
        response = table.scan(**scan_kw)
        items = response.get("Items", [])
        if not items:
            if "LastEvaluatedKey" not in response:
                break
            scan_kw["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            continue
        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={pk_name: item[pk_name], sk_name: item[sk_name]})
                count += 1
        if "LastEvaluatedKey" not in response:
            break
        scan_kw["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return count


def main():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    dynamodb = session.resource("dynamodb")
    for table_name, pk, sk in TABLES:
        try:
            n = clear_table(dynamodb, table_name, pk, sk)
            print(f"Cleared {table_name}: {n} items")
        except Exception as e:
            print(f"Error clearing {table_name}: {e}", file=sys.stderr)
            sys.exit(1)
    print("DynamoDB full reset done.")


if __name__ == "__main__":
    main()
