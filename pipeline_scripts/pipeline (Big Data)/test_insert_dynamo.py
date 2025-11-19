# diag_dynamo.py
import os, datetime
import boto3

REGION  = os.getenv("AWS_REGION", "ap-southeast-1")
PROFILE = os.getenv("AWS_PROFILE", "default")
TABLE   = os.getenv("DDB_TABLE", "stock_prices")

def creds_preview(session):
    c = session.get_credentials()
    if not c: return "NO CREDS"
    f = c.get_frozen_credentials()
    return {"access_key_prefix": (f.access_key[:4] + "..."), "has_secret": bool(f.secret_key), "has_token": bool(f.token)}

print("=== boto3 environment ===")
print("AWS_REGION   =", REGION)
print("AWS_PROFILE  =", PROFILE or "(none)")
for k in ("AWS_ACCESS_KEY_ID","AWS_SECRET_ACCESS_KEY","AWS_SESSION_TOKEN"):
    v = os.getenv(k)
    print(f"{k} =", (v[:4]+"..." if v else "(not set)"))

print("\n=== building session ===")
session = boto3.Session(profile_name=PROFILE, region_name=REGION)
print("session.profile_name =", session.profile_name)
print("session.region_name  =", session.region_name)
print("creds preview        =", creds_preview(session))

sts = session.client("sts")
print("\nSTS get_caller_identity =", sts.get_caller_identity())

ddb_client = session.client("dynamodb")
print("DynamoDB endpoint     =", ddb_client.meta.endpoint_url)

# Write a tiny test item
print("\nWriting one test item to", TABLE)
ddb = session.resource("dynamodb")
table = ddb.Table(TABLE)
table.put_item(Item={"ticker": "DIAG", "date": datetime.date.today().isoformat()})
print("put_item OK")
