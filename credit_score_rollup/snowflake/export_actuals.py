#!/usr/bin/env python3
"""Run actuals.sql against Snowflake and write actuals.csv for the heat map.

Connection comes from the environment, never from this file:

    SNOWFLAKE_ACCOUNT   SNOWFLAKE_USER      SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_DATABASE  SNOWFLAKE_SCHEMA    SNOWFLAKE_ROLE

and ONE of
    SNOWFLAKE_PASSWORD                     password
    SNOWFLAKE_PRIVATE_KEY_PATH             key pair (+ _PASSPHRASE if encrypted)
    SNOWFLAKE_AUTHENTICATOR=externalbrowser  SSO

    python export_actuals.py [-q actuals.sql] [-o actuals.csv]
"""
import argparse, csv, os, sys

REQUIRED = ["Vintage", "segment", "Branding", "Fee", "OriginalCreditLine", "mob",
            "CumUnitRate", "CumNetDollar", "CumulativeROA", "Boards",
            "Avg_InitialLinePerBooked", "CumPTI"]

def connect():
    try:
        import snowflake.connector
    except ImportError:
        sys.exit("snowflake-connector-python is not installed:\n"
                 "    pip install 'snowflake-connector-python'")
    need = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER"]
    missing = [v for v in need if not os.environ.get(v)]
    if missing:
        sys.exit(f"set these first: {', '.join(missing)}")
    kw = dict(account=os.environ["SNOWFLAKE_ACCOUNT"],
              user=os.environ["SNOWFLAKE_USER"])
    for var, key in (("SNOWFLAKE_WAREHOUSE", "warehouse"),
                     ("SNOWFLAKE_DATABASE", "database"),
                     ("SNOWFLAKE_SCHEMA", "schema"),
                     ("SNOWFLAKE_ROLE", "role")):
        if os.environ.get(var):
            kw[key] = os.environ[var]
    if os.environ.get("SNOWFLAKE_AUTHENTICATOR"):
        kw["authenticator"] = os.environ["SNOWFLAKE_AUTHENTICATOR"]
    elif os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        from cryptography.hazmat.primitives import serialization
        pw = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        with open(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"], "rb") as fh:
            key = serialization.load_pem_private_key(
                fh.read(), password=pw.encode() if pw else None)
        kw["private_key"] = key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption())
    elif os.environ.get("SNOWFLAKE_PASSWORD"):
        kw["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    else:
        sys.exit("no credential: set SNOWFLAKE_PASSWORD, "
                 "SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_AUTHENTICATOR")
    return snowflake.connector.connect(**kw)

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-q", "--query", default="actuals.sql")
    ap.add_argument("-o", "--out", default="actuals.csv")
    args = ap.parse_args()

    sql = open(args.query, encoding="utf-8").read()
    if "<YOUR" in sql:
        sys.exit(f"{args.query} still has <YOUR ...> placeholders in it - fill in "
                 f"the SOURCE table and name_map first")

    with connect() as cx:
        cur = cx.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

    missing = [c for c in REQUIRED if c not in cols]
    if missing:
        sys.exit(f"the query did not return: {missing}\nit returned: {cols}")

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerows(rows)
    print(f"{len(rows):,} rows -> {os.path.abspath(args.out)}")
    print("now run check_actuals.py to see which roll-up rows it will match")

if __name__ == "__main__":
    main()
